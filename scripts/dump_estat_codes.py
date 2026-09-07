"""Dump the 9-digit export codes e-Stat actually carries, by HS prefix.

Every question of the form "can this product be split out of the figure?"
is really a question about the 輸出統計品目表: a category only exists in
the statistics if MOF gave it its own 統計品目番号. This writes that answer
down once - `data/estat_code_index.json` - so the next such question is a
grep instead of another API round trip.

Run it from the Lookup export codes workflow, which holds the appId.
"""
import os
import sys

from common import DATA_DIR, save_json
from fetch_estat_trade import Estat, pick_table

OUT_PATH = DATA_DIR / "estat_code_index.json"

# 대시보드가 다루는 품목의 HS 앞자리들. 인자로 다른 값을 줄 수 있습니다.
DEFAULT_PREFIXES = ("2853", "3818", "8541", "8544", "9001", "9013")


def main():
    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        print("- ESTAT_APP_ID 가 없습니다.")
        return 1

    prefixes = tuple(a for a in sys.argv[1:] if a.strip()) or DEFAULT_PREFIXES
    api = Estat(app_id)

    hits = pick_table(api.tables(), "品別国別")
    if not hits:
        print("- 品別国別 테이블을 찾지 못했습니다.")
        return 1
    table, title = hits[-1]
    print(f"table {table}  {title}")

    meta = api.call("getMetaInfo", statsDataId=table)
    objs = meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
    objs = objs if isinstance(objs, list) else [objs]

    codes = []
    for c in objs:
        if c.get("@id") != "cat01":
            continue
        items = c.get("CLASS", [])
        items = items if isinstance(items, list) else [items]
        for i in items:
            code = str(i.get("@code", ""))
            if code.startswith(prefixes):
                codes.append({"code": code, "name": str(i.get("@name", ""))})

    codes.sort(key=lambda d: d["code"])
    save_json(OUT_PATH, {"table": table, "title": title, "prefixes": list(prefixes), "codes": codes})
    for c in codes:
        print(f"  {c['code']}  {c['name']}")
    print(f"{len(codes)} codes -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
