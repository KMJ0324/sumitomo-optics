"""Discovery probe, round 3 - the last unknowns before writing the collector.

Known: cat01 is the 9-digit code (381800100 silicon / 381800900 the rest),
cat02 carries the months (170 = January value, +30 per month), cat03 on the
customs table is 税関 with 50200 = 横浜.

Left to pin down: which `area` code is the world total, and what the actual
monthly figures look like - both for the substrate line and for Yokohama's
share of the optical cable line, so the numbers can be sanity-checked
against what is already on the dashboard before anything is built on them.
"""
import os
import sys

import requests

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
COMMODITY = "0004049306"   # 品別国別表 輸出 2026
CUSTOMS = "0004002162"     # 税関別品別国別表 輸出 2023-2026
MONTH_VALUE = {m: 170 + (m - 1) * 30 for m in range(1, 13)}   # m月_金額
MONTH_QTY2 = {m: 160 + (m - 1) * 30 for m in range(1, 13)}    # m月_数量2 (KG)


def call(path, **params):
    params["appId"] = os.environ["ESTAT_APP_ID"]
    r = requests.get(f"{BASE}/{path}", params=params, timeout=90)
    r.raise_for_status()
    return r.json()


def values(res):
    root = res["GET_STATS_DATA"]
    st = root["RESULT"]
    if st["STATUS"] != 0:
        print(f"    ERROR {st['STATUS']} {st.get('ERROR_MSG')}")
        return []
    v = root.get("STATISTICAL_DATA", {}).get("DATA_INF", {}).get("VALUE", [])
    return v if isinstance(v, list) else [v]


def main():
    if not os.environ.get("ESTAT_APP_ID"):
        print("ERROR: ESTAT_APP_ID 미설정", file=sys.stderr); sys.exit(1)

    print("=== area 차원 (国) 앞부분 ===")
    meta = call("getMetaInfo", statsDataId=COMMODITY)
    for c in meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]:
        if c.get("@id") != "area":
            continue
        items = c["CLASS"]
        items = items if isinstance(items, list) else [items]
        for i in items[:14]:
            print(f"    {i.get('@code')} = {i.get('@name')}")
        tot = [i for i in items if "総" in str(i.get("@name", "")) or "計" in str(i.get("@name", ""))]
        print(f"    합계로 보이는 항목: {[(i.get('@code'), i.get('@name')) for i in tot[:5]]}")

    codes = ",".join(str(MONTH_VALUE[m]) for m in range(1, 8))
    print(f"\n=== 381800900 (실리콘 제외) 2026년 1~7월 금액, area별 상위 ===")
    rows = values(call("getStatsData", statsDataId=COMMODITY,
                       cdCat01="381800900", cdCat02=codes, limit="500"))
    print(f"  {len(rows)}행")
    for r in rows[:12]:
        print(f"    area={r.get('@area')} cat02={r.get('@cat02')} = {r.get('$')} {r.get('@unit','')}")

    print(f"\n=== 381800100 (실리콘) 비교용 ===")
    rows2 = values(call("getStatsData", statsDataId=COMMODITY,
                        cdCat01="381800100", cdCat02=str(MONTH_VALUE[7]), limit="20"))
    for r in rows2[:6]:
        print(f"    area={r.get('@area')} = {r.get('$')} {r.get('@unit','')}")

    print(f"\n=== 横浜(50200) 세관, 854470100 완성 광케이블 2026 ===")
    rows3 = values(call("getStatsData", statsDataId=CUSTOMS,
                        cdCat01="854470100", cdCat03="50200",
                        cdCat02=codes, cdTime="2026000000", limit="300"))
    print(f"  {len(rows3)}행")
    for r in rows3[:12]:
        print(f"    area={r.get('@area')} cat02={r.get('@cat02')} = {r.get('$')} {r.get('@unit','')}")


if __name__ == "__main__":
    main()
