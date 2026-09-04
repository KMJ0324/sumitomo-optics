"""Discovery probe, round 2: the month dimension, the customs dimension,
and a real data pull for 381800900.

Round 1 found the two tables that matter:
  0004049306  品別国別表 輸出 2026        (9-digit commodity x country)
  0004002162  税関別品別国別表 輸出 2023-2026 (adds the customs office)
Both are annual tables, so the months must live inside cat02 - confirm
that, find Yokohama's code in the customs dimension, and prove a real
getStatsData call returns the silicon-excluded substrate series.
"""
import os
import sys

import requests

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
COMMODITY_2026 = "0004049306"
CUSTOMS_TABLE = "0004002162"
SUBSTRATE = "381800900"


def call(path, **params):
    params["appId"] = os.environ["ESTAT_APP_ID"]
    r = requests.get(f"{BASE}/{path}", params=params, timeout=90)
    r.raise_for_status()
    return r.json()


def classes_of(table):
    meta = call("getMetaInfo", statsDataId=table)
    obj = meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    return obj if isinstance(obj, list) else [obj]


def main():
    if not os.environ.get("ESTAT_APP_ID"):
        print("ERROR: ESTAT_APP_ID 미설정", file=sys.stderr)
        sys.exit(1)

    print(f"=== {COMMODITY_2026} 品別国別表 輸出 2026 ===")
    for c in classes_of(COMMODITY_2026):
        items = c.get("CLASS", [])
        items = items if isinstance(items, list) else [items]
        print(f"\n  @id={c.get('@id')} @name={c.get('@name')} ({len(items)}개)")
        if c.get("@id") in ("cat02", "time"):
            for i in items:
                print(f"      {i.get('@code')} = {i.get('@name')}")
        if c.get("@id") == "cat01":
            hit = [i for i in items if str(i.get("@code")).startswith("3818")]
            print(f"      3818 계열: {[(i.get('@code'), i.get('@name')) for i in hit]}")

    print(f"\n=== {CUSTOMS_TABLE} 税関別品別国別表 輸出 ===")
    for c in classes_of(CUSTOMS_TABLE):
        items = c.get("CLASS", [])
        items = items if isinstance(items, list) else [items]
        print(f"  @id={c.get('@id')} @name={c.get('@name')} ({len(items)}개)")
        names = " ".join(str(i.get("@name", "")) for i in items[:80])
        if "税関" in names or "横浜" in names:
            print(f"    *** 세관 차원. 전체: {[(i.get('@code'), i.get('@name')) for i in items[:30]]}")
        if c.get("@id") == "time":
            print(f"    시간: {[i.get('@name') for i in items[:8]]}")

    print(f"\n=== 실제 데이터: {SUBSTRATE} (실리콘 제외 화합물 기판), 전세계 ===")
    res = call("getStatsData", statsDataId=COMMODITY_2026, cdCat01=SUBSTRATE, limit="200")
    root = res["GET_STATS_DATA"]
    print(f"  RESULT {root['RESULT']['STATUS']} {root['RESULT'].get('ERROR_MSG','')}")
    inf = root.get("STATISTICAL_DATA", {}).get("RESULT_INF", {})
    print(f"  TOTAL_NUMBER={inf.get('TOTAL_NUMBER')}")
    values = root.get("STATISTICAL_DATA", {}).get("DATA_INF", {}).get("VALUE", [])
    values = values if isinstance(values, list) else [values]
    for v in values[:25]:
        print(f"    cat01={v.get('@cat01')} cat02={v.get('@cat02')} area={v.get('@area')} time={v.get('@time')} = {v.get('$')} {v.get('@unit','')}")


if __name__ == "__main__":
    main()
