"""Discovery probe for the e-Stat trade-statistics API.

Two things this dashboard wants that no keyless source provides: the
9-digit code 381800900 (compound substrates with silicon excluded) and a
税関 breakdown so Sumitomo's Yokohama shipments can be separated from
Japan-wide totals. e-Stat has both, but its trade tables are split by year,
month and table type, and the dimension names are not documented per table
- so ask the API what exists rather than guessing statsDataIds.

Reads ESTAT_APP_ID from the environment; never takes the key as an argument
so it cannot end up in a shell history or a workflow log.
"""
import json
import os
import sys

import requests

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
MOF_TRADE = "00350300"  # 財務省 貿易統計


def call(path, **params):
    params["appId"] = os.environ["ESTAT_APP_ID"]
    r = requests.get(f"{BASE}/{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    if not os.environ.get("ESTAT_APP_ID"):
        print("ERROR: ESTAT_APP_ID 가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    print("=== 1. 재무성 무역통계 표 목록 ===")
    res = call("getStatsList", statsCode=MOF_TRADE, limit="100")
    root = res.get("GET_STATS_LIST", {})
    status = root.get("RESULT", {})
    print(f"  RESULT: {status.get('STATUS')} {status.get('ERROR_MSG', '')}")
    tables = root.get("DATALIST_INF", {}).get("TABLE_INF", [])
    if isinstance(tables, dict):
        tables = [tables]
    print(f"  표 {len(tables)}개")

    interesting = []
    for t in tables:
        tid = t.get("@id")
        title = t.get("TITLE")
        title = title.get("$") if isinstance(title, dict) else title
        stat_name = t.get("STAT_NAME", {})
        stat_name = stat_name.get("$") if isinstance(stat_name, dict) else stat_name
        cycle = t.get("CYCLE")
        survey = t.get("SURVEY_DATE")
        print(f"    {tid} | {cycle} | {survey} | {stat_name} | {title}")
        blob = f"{title} {stat_name}"
        if any(k in blob for k in ("品別", "税関", "統計品", "国別")):
            interesting.append((tid, blob))

    print(f"\n=== 2. 관심 표 {len(interesting)}개의 차원 구성 ===")
    for tid, blob in interesting[:4]:
        print(f"\n--- {tid}  {blob}")
        try:
            meta = call("getMetaInfo", statsDataId=tid)
        except Exception as err:  # noqa: BLE001
            print(f"    getMetaInfo 실패: {err}")
            continue
        cls_obj = meta.get("GET_META_INFO", {}).get("METADATA_INF", {}).get("CLASS_INF", {})
        classes = cls_obj.get("CLASS_OBJ", [])
        if isinstance(classes, dict):
            classes = [classes]
        for c in classes:
            items = c.get("CLASS", [])
            if isinstance(items, dict):
                items = [items]
            names = [str(i.get("@name", ""))[:22] for i in items[:5]]
            print(f"    @id={c.get('@id')} @name={c.get('@name')} ({len(items)}개) 예: {names}")
            # 9단위 코드나 세관 이름이 보이는지
            codes = [str(i.get("@code", "")) for i in items[:400]]
            nine = [c2 for c2 in codes if len(c2) == 9 and c2.isdigit()]
            if nine:
                print(f"      9자리 코드 {len(nine)}개 예: {nine[:6]}")
            if any("税関" in str(i.get("@name", "")) or "横浜" in str(i.get("@name", "")) for i in items[:400]):
                hits = [i.get("@name") for i in items if "横浜" in str(i.get("@name", ""))][:3]
                print(f"      *** 税関 차원으로 보입니다. 横浜: {hits}")


if __name__ == "__main__":
    main()
