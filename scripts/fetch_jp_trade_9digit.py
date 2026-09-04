"""Japan's optical exports at 9-digit statistical-code granularity, in yen.

Comtrade gave 6-digit HS in US dollars on a three-month lag. Japan Customs
actually reports at nine digits, and at that level the optical lines separate
cleanly - raw fibre, finished cable, connectorised cable - and are the lines
Sumitomo Electric and Fujikura dominate. must-charts publishes those series,
already parsed out of the MOF release, in billions of yen with weight and a
destination split, back to 2017 and roughly a month fresher than Comtrade.

Two things make the feed durable rather than a hardcoded scrape:
  - the page's filename carries a content hash, so it is rediscovered from
    the site index each run instead of being pinned;
  - every page is scanned and merged, since the codes are split across
    several standalone builds.

Values are checked against the weight column on arrival: a series whose
implied unit price leaves a plausible band is rejected rather than charted,
which is what would catch the source silently changing denomination.
"""
import datetime
import json
import re
import sys

import requests

from common import DATA_DIR, load_json, save_json, sync_to_docs

CATEGORIES_PATH = DATA_DIR / "jp_trade_categories.json"
EXPORTS_PATH = DATA_DIR / "jp_trade_exports_jpy.json"

SITE = "https://must-charts.pages.dev/"
PAGE_RE = re.compile(r'"(/japan-trade[^"]*?\.html)"')
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}

# value_bn 은 십억 엔. kg 로 나눈 단가가 이 범위를 벗어나면 단위가 바뀐 것으로
# 보고 그 계열을 버립니다 (광섬유류는 대략 수천~수십만 엔/kg).
MIN_YEN_PER_KG = 200.0
MAX_YEN_PER_KG = 5_000_000.0


def discover_pages(session) -> list[str]:
    resp = session.get(SITE, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    paths = sorted(set(PAGE_RE.findall(resp.text)))
    if not paths:
        raise RuntimeError("사이트 색인에서 japan-trade 페이지를 찾지 못했습니다")
    return [SITE.rstrip("/") + p for p in paths]


def extract_embedded(text: str) -> dict:
    """Pull the inlined `const EMBEDDED = {...}` object out of a page."""
    i = text.find("const EMBEDDED")
    if i < 0:
        return {}
    start = text.index("{", i)
    depth, in_str, esc = 0, False, False
    for j in range(start, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:j + 1])
    return {}


def collect_blocks(session, urls) -> dict:
    """code -> block, merged across every standalone build that has one."""
    blocks = {}
    for url in urls:
        try:
            resp = session.get(url, headers=HEADERS, timeout=90)
            resp.raise_for_status()
            embedded = extract_embedded(resp.text)
        except Exception as err:  # noqa: BLE001 - one bad page shouldn't sink the run
            print(f"    WARN: {url} 읽기 실패: {err}")
            continue
        added = 0
        for key, blob in embedded.items():
            if not key.startswith("data/exp-") or not isinstance(blob, dict):
                continue
            code = str(blob.get("code") or "")
            if code and code not in blocks:
                blocks[code] = blob
                added += 1
        print(f"    {url.rsplit('/', 1)[-1]}: {added}개 코드")
    return blocks


def to_month(ym: str) -> str:
    return ym.replace("/", "-")


def convert(blob: dict) -> dict:
    """One code's block -> the dashboard's monthly/partners shape, in yen."""
    monthly = []
    for row in blob.get("data", []):
        value_bn, kg = row.get("value_bn"), row.get("kg")
        if value_bn is None:
            continue
        entry = {"month": to_month(row["ym"]), "value": round(float(value_bn) * 1e9, 2)}
        if kg:
            entry["weight_kg"] = float(kg)
        monthly.append(entry)
    monthly.sort(key=lambda r: r["month"])

    # 단가 sanity check - 단위가 바뀌면 여기서 걸립니다.
    priced = [(r["value"] / r["weight_kg"]) for r in monthly if r.get("weight_kg")]
    if priced:
        typical = sorted(priced)[len(priced) // 2]
        if not MIN_YEN_PER_KG <= typical <= MAX_YEN_PER_KG:
            raise ValueError(
                f"단가 {typical:,.0f} 엔/kg 이 예상 범위를 벗어납니다 - 원본 단위가 바뀌었을 수 있습니다"
            )

    partners = {}
    groups = blob.get("groups") or {}
    for name, rows in (groups.get("series") or {}).items():
        months = [
            {"month": to_month(r["ym"]), "value": round(float(r["value_bn"]) * 1e9, 2)}
            for r in rows
            if r.get("value_bn") is not None
        ]
        if months:
            partners[name] = {"name": name, "monthly": sorted(months, key=lambda r: r["month"])}

    return {"monthly": monthly, "partners": partners, "source_name": blob.get("name", "")}


def main():
    config = load_json(CATEGORIES_PATH, {})
    wanted = [c for c in config.get("categories_9digit", []) if c.get("enabled", True)]
    if not wanted:
        print("ERROR: jp_trade_categories.json 에 categories_9digit 정의가 없습니다.", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    urls = discover_pages(session)
    print(f"- 색인에서 {len(urls)}개 페이지 발견")
    blocks = collect_blocks(session, urls)
    print(f"- 코드 {len(blocks)}개 수집: {sorted(blocks)}")

    data = load_json(EXPORTS_PATH, {})
    store = data.setdefault("categories", {})
    kept = 0
    for cat in wanted:
        code = str(cat["code"])
        blob = blocks.get(code)
        if not blob:
            print(f"    - {code} ({cat['label']}): 소스에 없음, 건너뜀")
            continue
        try:
            converted = convert(blob)
        except ValueError as err:
            print(f"    WARN: {code} ({cat['label']}) 버림: {err}")
            continue
        node = store.setdefault(cat["id"], {})
        node.update({
            "label": cat["label"],
            "code": code,
            "hs": [code],
            "caveat": cat.get("caveat", ""),
            "source_name": converted["source_name"],
            "monthly": converted["monthly"],
            "partners": converted["partners"],
        })
        kept += 1

    covered = sorted({r["month"] for n in store.values() for r in n.get("monthly", [])})
    data.update({
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "source": "must-charts (일본 재무성 관세국 9단위 통계품목 기준)",
        "source_url": SITE,
        "reporter": "Japan",
        "flow": "export",
        "value_unit": "JPY",
        "value_unit_label": "엔",
        "value_note": (
            "일본 재무성 관세국의 9단위 통계품목번호 기준 수출액(엔)입니다. "
            "HS 6단위보다 세분화돼 있어 광섬유·광케이블 품목이 분리되며, "
            "이 세 품목은 스미토모전기와 후지쿠라가 사실상 과점하는 라인입니다."
        ),
        "coverage": {"first_month": covered[0] if covered else None,
                     "last_month": covered[-1] if covered else None},
    })
    save_json(EXPORTS_PATH, data)
    sync_to_docs()

    print(f"- 반영 {kept}개 품목, 구간 {data['coverage']['first_month']} ~ {data['coverage']['last_month']}")
    for cid, node in store.items():
        last = node["monthly"][-1] if node.get("monthly") else None
        if last:
            print(f"    {node['label']}: {len(node['monthly'])}개월, 최신 {last['month']} "
                  f"{last['value'] / 1e9:,.2f}십억엔, 목적지 {len(node.get('partners', {}))}")


if __name__ == "__main__":
    main()
