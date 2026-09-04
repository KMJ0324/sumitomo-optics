"""Japan's monthly exports of optical products, by HS code and destination.

Source: UN Comtrade's public "preview" endpoint, which republishes the
reporter data Japan Customs (Ministry of Finance) files. It's the only
route to this data that needs no registration - the Ministry's own CSVs are
served through e-Stat, whose file listings are rendered client-side and
whose API requires an appId. Two consequences worth knowing when reading
the dashboard:

  - Values are FOB **US dollars**, not yen. The unit travels with the data
    (`value_unit`) so the dashboard labels its axes from the file rather
    than assuming.
  - Comtrade republishes on a lag; roughly the three most recent months are
    typically not yet available and simply come back empty.

The endpoint allows only one period per request, so a multi-year backfill
is spread across runs: each run refreshes the newest stored months (their
figures get revised) and then fills gaps newest-first until it runs out of
its request budget. Partner rows come back in the same response as the
world total, so one request covers both.
"""
import datetime
import sys
import time

import requests

from common import DATA_DIR, load_json, save_json, sync_to_docs
from jp_partner_names import partner_name

CATEGORIES_PATH = DATA_DIR / "jp_trade_categories.json"
EXPORTS_PATH = DATA_DIR / "jp_trade_exports.json"

PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
REPORTER_JAPAN = "392"
START_MONTH = "2021-01"

# Per-run request budget. Each request is one month; a full backfill from
# START_MONTH is a few dozen, so the default finishes in one run and steady
# state uses a handful.
DEFAULT_BUDGET = 90
# Comtrade revises recent months, so re-pull the newest stored ones.
REFRESH_TAIL = 4
# The preview endpoint truncates at 500 rows. Well under it we can take one
# request per month for every HS code at once; at the ceiling the response
# may be silently cut, so fall back to one request per code.
ROW_CEILING = 490

UA = {"User-Agent": "Mozilla/5.0 (compatible; dart-order-dashboard/1.0)"}


def month_range(start: str, end: str) -> list[str]:
    y, m = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


class Budget:
    """Counts requests so a run can't spin forever on a slow backfill."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def spend(self) -> bool:
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    @property
    def left(self) -> int:
        return max(0, self.limit - self.used)


def request_month(month: str, hs_codes: list[str], budget: Budget, retries: int = 4):
    """One month of Japanese exports for `hs_codes`, all destinations.

    Returns the raw row list, or None if the budget ran out or every attempt
    failed. An empty list is a real answer: Comtrade hasn't published that
    month yet.
    """
    period = month.replace("-", "")
    params = {
        "reporterCode": REPORTER_JAPAN,
        "period": period,
        "flowCode": "X",
        "cmdCode": ",".join(hs_codes),
        "partner2Code": "0",
        "customsCode": "C00",
        "motCode": "0",
    }
    for attempt in range(1, retries + 1):
        if not budget.spend():
            return None
        try:
            resp = requests.get(PREVIEW_URL, params=params, headers=UA, timeout=60)
            if resp.status_code == 429:
                # The throttle is short-lived and advertises its own wait.
                wait = float(resp.headers.get("Retry-After") or 2)
                time.sleep(min(wait + 1, 15))
                continue
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(payload["error"])
            return payload.get("data") or []
        except Exception as err:  # noqa: BLE001 - best effort against a public endpoint
            if attempt == retries:
                print(f"    WARN: {month} 수집 실패: {err}")
                return None
            time.sleep(1.5 * attempt)
    # Every attempt was throttled (or the budget ran out mid-retry). Say so
    # rather than returning None silently - a run that quietly collects
    # nothing looks identical to one where there was nothing to collect.
    print(f"    WARN: {month} 수집 포기 (재시도 {retries}회 모두 제한에 걸림)")
    return None


def collect_month(month: str, categories: list[dict], budget: Budget):
    """Rows for every enabled category's HS codes in `month`, split per code."""
    all_codes = sorted({code for cat in categories for code in cat["hs"]})
    rows = request_month(month, all_codes, budget)
    if rows is None:
        return None

    # A response at the row ceiling may have been truncated; re-ask one code
    # at a time so no destination is silently lost.
    if len(rows) >= ROW_CEILING:
        print(f"    {month}: {len(rows)}행 (상한 근접) - HS 코드별로 재요청")
        rows = []
        for code in all_codes:
            part = request_month(month, [code], budget)
            if part is None:
                return None
            rows.extend(part)
    return rows


def summarize(rows: list[dict], hs_codes: set[str]):
    """Fold one month's rows into a world total and a per-destination map.

    Weight is optional in Comtrade (some codes report none), and summing a
    partial weight against a full value would produce a nonsense average
    price - so a category keeps a weight only if every contributing row has
    one.
    """
    world = {"value": 0.0, "weight_kg": 0.0, "weight_complete": True, "rows": 0}
    partners: dict[int, dict] = {}

    for row in rows:
        if str(row.get("cmdCode")) not in hs_codes:
            continue
        value = row.get("fobvalue")
        if value is None:
            value = row.get("primaryValue")
        if value is None:
            continue
        weight = row.get("netWgt")
        try:
            code = int(row.get("partnerCode"))
        except (TypeError, ValueError):
            continue

        bucket = world if code == 0 else partners.setdefault(
            code, {"value": 0.0, "weight_kg": 0.0, "weight_complete": True, "rows": 0}
        )
        bucket["value"] += float(value)
        bucket["rows"] += 1
        if weight is None:
            bucket["weight_complete"] = False
        else:
            bucket["weight_kg"] += float(weight)

    return world, partners


def entry_from(bucket: dict) -> dict | None:
    if not bucket["rows"]:
        return None
    out = {"value": round(bucket["value"], 2)}
    if bucket["weight_complete"] and bucket["weight_kg"] > 0:
        out["weight_kg"] = round(bucket["weight_kg"], 2)
    return out


def prune_partners(category: dict, keep_months: int = 26, top_n: int = 20):
    """Keep the destination detail small: recent months, leading partners.

    The world totals are the long history; per-destination rows only back
    the "top destinations" table, which needs a year of context plus a year
    of prior-year comparisons.
    """
    monthly = category.get("monthly", [])
    recent = {row["month"] for row in monthly[-keep_months:]}
    partners = category.get("partners", {})

    totals: dict[str, float] = {}
    last_12 = {row["month"] for row in monthly[-12:]}
    for code, info in partners.items():
        totals[code] = sum(
            m["value"] for m in info.get("monthly", []) if m["month"] in last_12
        )
    keep = {code for code, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:top_n]}

    pruned = {}
    for code, info in partners.items():
        if code not in keep:
            continue
        months = [m for m in info.get("monthly", []) if m["month"] in recent]
        if months:
            # Re-derive the name every run rather than keeping what was stored:
            # a partner only appearing in older months would otherwise hold a
            # stale label forever after the lookup table is corrected.
            pruned[code] = {"name": partner_name(code), "monthly": months}
    category["partners"] = pruned


def main():
    budget = Budget(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BUDGET)

    config = load_json(CATEGORIES_PATH, {})
    categories = [c for c in config.get("categories", []) if c.get("enabled", True)]
    if not categories:
        print("ERROR: data/jp_trade_categories.json 에 활성화된 카테고리가 없습니다.", file=sys.stderr)
        sys.exit(1)

    data = load_json(EXPORTS_PATH, {})
    data.setdefault("categories", {})
    store = data["categories"]

    for cat in categories:
        node = store.setdefault(cat["id"], {})
        node["label"] = cat["label"]
        node["label_en"] = cat.get("label_en", "")
        node["group"] = cat.get("group", "")
        node["hs"] = cat["hs"]
        node["caveat"] = cat.get("caveat", "")
        node.setdefault("monthly", [])
        node.setdefault("partners", {})

    today = datetime.date.today()
    all_months = month_range(START_MONTH, f"{today.year:04d}-{today.month:02d}")

    have = {
        row["month"]
        for cat in categories
        for row in store[cat["id"]]["monthly"]
    }
    stored_sorted = sorted(have)
    refresh = stored_sorted[-REFRESH_TAIL:] if stored_sorted else []
    missing = [m for m in all_months if m not in have]

    # Newest first: a partial backfill should still leave the recent months
    # - the ones anyone actually looks at - complete.
    todo = list(dict.fromkeys(refresh + sorted(missing, reverse=True)))
    print(f"- 보유 {len(have)}개월, 갱신 대상 {len(refresh)}개월, 미수집 {len(missing)}개월")
    print(f"- 이번 실행 요청 예산: {budget.limit}건")

    fetched_months = 0
    empty_months = []
    for month in todo:
        if budget.left <= 0:
            print(f"- 예산 소진: {month} 이전 구간은 다음 실행에서 이어서 수집합니다.")
            break
        rows = collect_month(month, categories, budget)
        if rows is None:
            continue
        if not rows:
            empty_months.append(month)
            continue

        for cat in categories:
            node = store[cat["id"]]
            world, partners = summarize(rows, set(cat["hs"]))
            world_entry = entry_from(world)
            if world_entry is None:
                continue
            world_entry["month"] = month
            node["monthly"] = sorted(
                [r for r in node["monthly"] if r["month"] != month] + [world_entry],
                key=lambda r: r["month"],
            )
            for code, bucket in partners.items():
                pentry = entry_from(bucket)
                if pentry is None:
                    continue
                pentry["month"] = month
                key = str(code)
                pnode = node["partners"].setdefault(key, {"name": partner_name(code), "monthly": []})
                pnode["name"] = partner_name(code)
                pnode["monthly"] = sorted(
                    [r for r in pnode["monthly"] if r["month"] != month] + [pentry],
                    key=lambda r: r["month"],
                )
        fetched_months += 1
        time.sleep(0.6)

    for cat in categories:
        prune_partners(store[cat["id"]])

    covered = sorted({row["month"] for cat in categories for row in store[cat["id"]]["monthly"]})
    data["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    data["source"] = "UN Comtrade (일본 재무성 관세국 신고자료 재배포)"
    data["source_url"] = "https://comtradeapi.un.org"
    data["reporter"] = "Japan (392)"
    data["flow"] = "export"
    data["value_unit"] = "USD"
    data["value_unit_label"] = "USD"
    data["value_note"] = (
        "UN Comtrade가 재배포하는 일본 관세국(재무성) 신고 기준 수출액(FOB, 미 달러)입니다. "
        "엔화 원자료는 e-Stat API(appId 필요)에서만 제공되어 여기서는 달러 기준으로 표시합니다."
    )
    data["coverage"] = {"first_month": covered[0] if covered else None, "last_month": covered[-1] if covered else None}
    data["pending_months"] = len([m for m in all_months if m not in set(covered)])

    save_json(EXPORTS_PATH, data)
    sync_to_docs()

    print(f"- 이번 실행 수집 {fetched_months}개월 (요청 {budget.used}건)")
    if empty_months:
        print(f"- 아직 미공표 구간(정상): {', '.join(sorted(empty_months, reverse=True)[:6])}")
    print(f"- 누적 수집 구간: {covered[0] if covered else '없음'} ~ {covered[-1] if covered else '없음'} ({len(covered)}개월)")
    for cat in categories:
        node = store[cat["id"]]
        last = node["monthly"][-1] if node["monthly"] else None
        print(
            f"    {cat['label']}: {len(node['monthly'])}개월, 최신 {last['month'] if last else '-'} "
            f"value={last['value'] if last else '-'} 목적지 {len(node['partners'])}개"
        )
    print("Done.")


if __name__ == "__main__":
    main()
