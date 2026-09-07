"""Japan's export statistics straight from e-Stat (財務省 貿易統計), in yen.

This is the source the dashboard wanted all along. Comtrade only publishes
6-digit HS in dollars, which buries the products this is about: 3818.00 is
every doped wafer Japan ships, and Shin-Etsu and SUMCO's silicon runs about
thirty times the size of everything else in it, so an InP move is invisible.
e-Stat carries the 9-digit codes, where -100 (けい素のもの) and -900
(その他のもの) are separate lines, and it carries a customs dimension, so
Yokohama - where Sumitomo Electric ships from - can be separated from the
national total.

Shape of the data, established by probing the API rather than the docs:
  cat01  9-digit statistical code
  cat02  41 slots; monthly value is 170 + (month-1)*30, monthly weight
         (KG, 数量2) is 160 + (month-1)*30
  area   country, 50103 = Korea etc. There is no world-total row, so the
         national figure is the sum across countries
  cat03  customs office on the 税関別 table only; 50200 = 横浜
  time   one entry per year; the tables are annual, months live in cat02

Values arrive in 千円 and are stored in yen. Tables are discovered from the
statistics list each run instead of being pinned, since MOF issues new
statsDataIds as years roll over.
"""
import datetime
import os
import re
import sys
import time

import requests

from common import DATA_DIR, load_json, save_json, sync_to_docs
from jp_country_names import to_korean

CATEGORIES_PATH = DATA_DIR / "jp_trade_categories.json"
OUT_PATH = DATA_DIR / "jp_trade_exports_estat.json"

BASE = "https://api.e-stat.go.jp/rest/3.0/app/json"
MOF_TRADE = "00350300"

MONTH_VALUE = {m: str(170 + (m - 1) * 30) for m in range(1, 13)}
MONTH_WEIGHT = {m: str(160 + (m - 1) * 30) for m in range(1, 13)}
VALUE_CODES = {v: m for m, v in MONTH_VALUE.items()}
WEIGHT_CODES = {v: m for m, v in MONTH_WEIGHT.items()}

TOP_PARTNERS = 10


class Estat:
    def __init__(self, app_id):
        self.app_id = app_id
        self.session = requests.Session()

    def call(self, path, **params):
        params["appId"] = self.app_id
        for attempt in range(1, 4):
            try:
                r = self.session.get(f"{BASE}/{path}", params=params, timeout=90)
                r.raise_for_status()
                return r.json()
            except Exception as err:  # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(2 * attempt)

    def tables(self):
        """(statsDataId, title) for every table in MOF trade statistics."""
        out, start = [], 1
        while True:
            res = self.call("getStatsList", statsCode=MOF_TRADE, limit="100", startPosition=str(start))
            root = res["GET_STATS_LIST"]
            if root["RESULT"]["STATUS"] != 0:
                raise RuntimeError(root["RESULT"].get("ERROR_MSG"))
            info = root.get("DATALIST_INF", {})
            items = info.get("TABLE_INF", [])
            items = items if isinstance(items, list) else [items]
            for t in items:
                title = t.get("TITLE")
                title = title.get("$") if isinstance(title, dict) else title
                out.append((t.get("@id"), title or ""))
            nxt = info.get("NEXT_KEY")
            if not nxt:
                return out
            start = int(nxt)

    def years_of(self, table):
        meta = self.call("getMetaInfo", statsDataId=table)
        objs = meta["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]["CLASS_OBJ"]
        objs = objs if isinstance(objs, list) else [objs]
        for c in objs:
            if c.get("@id") != "time":
                continue
            items = c.get("CLASS", [])
            items = items if isinstance(items, list) else [items]
            return {int(re.sub(r"\D", "", str(i.get("@name")))[:4]): str(i.get("@code")) for i in items}
        return {}

    def series(self, table, code, year_code, customs=None):
        """month -> {value(yen), weight_kg, partners{name: yen}} for one code."""
        params = {
            "statsDataId": table,
            "cdCat01": code,
            "cdCat02": ",".join(list(MONTH_VALUE.values()) + list(MONTH_WEIGHT.values())),
            "cdTime": year_code,
            "limit": "100000",
        }
        if customs:
            params["cdCat03"] = customs
        res = self.call("getStatsData", **params)
        root = res["GET_STATS_DATA"]
        if root["RESULT"]["STATUS"] != 0:
            raise RuntimeError(root["RESULT"].get("ERROR_MSG"))

        # area 코드를 이름으로 바꾸기 위한 사전
        names = {}
        cls = root.get("STATISTICAL_DATA", {}).get("CLASS_INF", {}).get("CLASS_OBJ", [])
        cls = cls if isinstance(cls, list) else [cls]
        for c in cls:
            if c.get("@id") != "area":
                continue
            items = c.get("CLASS", [])
            items = items if isinstance(items, list) else [items]
            for i in items:
                # "103_大韓民国" 형태에서 이름만 떼어 한국어로 옮깁니다.
                # 대응표에 없으면 일본어가 그대로 남아 눈에 띕니다.
                names[str(i.get("@code"))] = to_korean(str(i.get("@name", "")))

        rows = root.get("STATISTICAL_DATA", {}).get("DATA_INF", {}).get("VALUE", [])
        rows = rows if isinstance(rows, list) else [rows]

        months = {}
        for r in rows:
            cat02 = str(r.get("@cat02"))
            raw = str(r.get("$", "")).strip()
            if raw in ("", "-", "***", "X"):
                continue
            try:
                num = float(raw)
            except ValueError:
                continue
            area = str(r.get("@area"))
            if cat02 in VALUE_CODES:
                m = months.setdefault(VALUE_CODES[cat02], {"value": 0.0, "weight_kg": 0.0, "partners": {}})
                yen = num * 1000.0  # 千円 -> 엔
                m["value"] += yen
                if yen:
                    label = names.get(area, area)
                    m["partners"][label] = m["partners"].get(label, 0.0) + yen
            elif cat02 in WEIGHT_CODES:
                m = months.setdefault(WEIGHT_CODES[cat02], {"value": 0.0, "weight_kg": 0.0, "partners": {}})
                m["weight_kg"] += num
        return months


def pick_table(tables, keyword):
    """Newest table whose title matches, preferring 確報/確定 over 速報."""
    hits = [(tid, title) for tid, title in tables if keyword in title and "輸出" in title]
    return hits


def main():
    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        print("- ESTAT_APP_ID 가 없어 건너뜁니다 (다른 수집기가 대신합니다).")
        return

    cfg = load_json(CATEGORIES_PATH, {}).get("estat") or {}
    cats = cfg.get("categories") or []
    if not cats:
        print("ERROR: jp_trade_categories.json 의 estat.categories 가 비어 있습니다.", file=sys.stderr)
        sys.exit(1)
    first_year = int(cfg.get("first_year", 2019))
    office = cfg.get("customs_office") or {}
    this_year = datetime.date.today().year

    api = Estat(app_id)
    tables = api.tables()
    print(f"- 재무성 무역통계 표 {len(tables)}개")

    commodity = pick_table(tables, "品別国別表")
    commodity = [(t, n) for t, n in commodity if "税関別" not in n and "概況品" not in n
                 and "航空" not in n and "コンテナ" not in n]
    customs_tables = pick_table(tables, "税関別品別国別表")
    print(f"  품별국별표 {len(commodity)}개, 세관별 {len(customs_tables)}개")

    # 연도 -> 표 매핑 (뒤에 오는 표가 최신 개정판이므로 나중 것이 이깁니다)
    def year_map(table_list):
        out = {}
        for tid, _ in table_list:
            try:
                for yr, code in api.years_of(tid).items():
                    if yr >= first_year:
                        out[yr] = (tid, code)
            except Exception as err:  # noqa: BLE001
                print(f"    WARN: {tid} 메타 실패: {err}")
        return out

    nation_years = year_map(commodity)
    customs_years = year_map(customs_tables)
    print(f"  전국 연도: {sorted(nation_years)}")
    print(f"  세관별 연도: {sorted(customs_years)}")

    data = load_json(OUT_PATH, {})
    store = data.setdefault("categories", {})

    for cat in cats:
        code, cid = str(cat["code"]), cat["id"]
        monthly, partner_totals, customs_monthly = {}, {}, {}
        for yr in sorted(nation_years):
            tid, tcode = nation_years[yr]
            try:
                got = api.series(tid, code, tcode)
            except Exception as err:  # noqa: BLE001
                print(f"    WARN: {code} {yr}년 실패: {err}")
                continue
            for m, agg in got.items():
                if yr == this_year and not agg["value"]:
                    continue  # 아직 공표 전인 달
                key = f"{yr:04d}-{m:02d}"
                row = {"month": key, "value": round(agg["value"], 0)}
                if agg["weight_kg"]:
                    row["weight_kg"] = round(agg["weight_kg"], 1)
                monthly[key] = row
                for name, yen in agg["partners"].items():
                    partner_totals.setdefault(name, {})[key] = round(yen, 0)
            time.sleep(0.3)

        if office.get("code"):
            for yr in sorted(customs_years):
                tid, tcode = customs_years[yr]
                try:
                    got = api.series(tid, code, tcode, customs=office["code"])
                except Exception as err:  # noqa: BLE001
                    print(f"    WARN: {code} {yr}년 {office.get('name')} 실패: {err}")
                    continue
                for m, agg in got.items():
                    if yr == this_year and not agg["value"]:
                        continue
                    customs_monthly[f"{yr:04d}-{m:02d}"] = round(agg["value"], 0)
                time.sleep(0.3)

        if not monthly:
            print(f"    - {code} ({cat['label']}): 값 없음, 건너뜀")
            continue

        # 최근 12개월 기준 상위 목적지만 남깁니다
        recent = sorted(monthly)[-12:]
        ranked = sorted(partner_totals.items(),
                        key=lambda kv: -sum(v for m, v in kv[1].items() if m in recent))
        partners = {
            name: {"name": name,
                   "monthly": [{"month": m, "value": v} for m, v in sorted(series.items())]}
            for name, series in ranked[:TOP_PARTNERS]
        }

        store[cid] = {
            "label": cat["label"],
            "code": code,
            "hs": [code],
            "caveat": cat.get("caveat", ""),
            "reference_only": bool(cat.get("reference_only")),
            "monthly": [monthly[m] for m in sorted(monthly)],
            "partners": partners,
            "customs": ({"name": office.get("name"), "code": office.get("code"),
                         "monthly": [{"month": m, "value": customs_monthly[m]}
                                     for m in sorted(customs_monthly)]}
                        if customs_monthly else None),
        }
        last = store[cid]["monthly"][-1]
        cm = store[cid]["customs"]
        print(f"    {cat['label']}: {len(monthly)}개월, 최신 {last['month']} "
              f"{last['value'] / 1e9:,.2f}십억엔"
              + (f", {office.get('name')} {len(cm['monthly'])}개월" if cm else ""))

    covered = sorted({r["month"] for n in store.values() for r in n.get("monthly", [])})
    data.update({
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": "e-Stat 재무성 무역통계 품별국별표(9단위 통계품목번호)",
        "source_url": "https://www.e-stat.go.jp/",
        "value_unit": "JPY",
        "value_unit_label": "엔",
        "customs_office": office,
        "value_note": (
            "일본 재무성 무역통계의 9단위 통계품목번호 기준 수출액(엔)입니다. "
            "HS 6단위와 달리 3818.00이 실리콘(-100)과 그 외(-900)로 갈라져, "
            "신에쓰·SUMCO의 실리콘 웨이퍼를 뺀 화합물 기판만 따로 볼 수 있습니다."
        ),
        "coverage": {"first_month": covered[0] if covered else None,
                     "last_month": covered[-1] if covered else None},
    })
    save_json(OUT_PATH, data)
    sync_to_docs()
    print(f"- 구간 {data['coverage']['first_month']} ~ {data['coverage']['last_month']}")


if __name__ == "__main__":
    main()
