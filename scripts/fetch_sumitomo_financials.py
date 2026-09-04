"""Annual results for Sumitomo Electric, from Yahoo Japan's 業績 table.

There is no free machine-readable source for the *quarterly* figures -
EDINET v2 needs a registered key, Yahoo's US financial endpoints are
crumb-gated, and Yahoo Japan's performance page carries only annual rows
(its ?styl= variants return the same table). So this collects what is
actually available - fiscal-year revenue, operating income and net income,
plus the company's own forecast for the year in progress - and
ensure_sumitomo_financials.py keeps the hand-entry quarterly rows alongside
for anyone who wants finer granularity.

The table is HTML, so columns are matched by their header text rather than
by position, and every row is checked against relations a P&L must satisfy
(revenue positive, operating income no larger than revenue). A row that
fails is dropped rather than guessed at, and the company forecast is kept
in its own field so it is never mistaken for a reported figure.
"""
import datetime
import re

import requests

from common import DATA_DIR, load_json, save_json, sync_to_docs

FINANCIALS_PATH = DATA_DIR / "sumitomo_financials.json"

URL = "https://finance.yahoo.co.jp/quote/5802.T/performance"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# 헤더 문구 -> 저장 필드. 표에 없으면 그 항목만 비고 나머지는 그대로 씁니다.
COLUMNS = {
    "売上高": "revenue",
    "営業利益": "operating_income",
    "経常利益": "ordinary_income",
    "純利益": "net_income",
}
PERIOD_RE = re.compile(r"(\d{4})年(\d{1,2})月期")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _cells(row_html: str) -> list[str]:
    return [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)]


def _number(cell: str):
    cell = cell.replace(",", "").replace("△", "-").replace("▲", "-").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", cell):
        return None
    return float(cell)


def parse_annual(html: str) -> list[dict]:
    """Fiscal-year rows from the 業績 table, newest first."""
    for table in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        if len(rows) < 2:
            continue
        header = _cells(rows[0])
        # 첫 칸은 결산기라 비어 있고, 나머지에서 항목명을 찾습니다.
        index = {}
        for i, cell in enumerate(header):
            for label, field in COLUMNS.items():
                # "売上高 （百万円）" 처럼 단위가 붙어 있고, 売上総利益 이
                # 売上高 를 포함하므로 앞부분이 정확히 일치할 때만 씁니다.
                if cell.split("（")[0].strip() == label and field not in index:
                    index[field] = i
        if "revenue" not in index or "operating_income" not in index:
            continue

        out = []
        for row_html in rows[1:]:
            cells = _cells(row_html)
            if len(cells) <= max(index.values()):
                continue
            m = PERIOD_RE.search(cells[0])
            if not m:
                continue
            year, month = int(m.group(1)), int(m.group(2))
            if year < 2000 or not 1 <= month <= 12:
                continue  # 표에 섞여 있는 "0000年0月期" 자리표시 행
            values = {f: _number(cells[i]) for f, i in index.items()}
            if not values.get("revenue") or values["revenue"] <= 0:
                continue
            op = values.get("operating_income")
            if op is not None and abs(op) > values["revenue"]:
                raise ValueError(
                    f"손익 관계 위반 ({cells[0]}: 매출 {values['revenue']} 영업이익 {op}) "
                    "- 표의 열 순서가 예상과 다릅니다."
                )
            out.append({
                "fiscal_year_end": f"{year:04d}-{month:02d}",
                "label": f"{year % 100:02d}/{month:02d}기",
                "forecast": "予想" in cells[0],
                **values,
            })
        if out:
            return out
    raise ValueError("業績 표를 찾지 못했습니다 - 페이지 구조가 바뀌었을 수 있습니다.")


def main():
    data = load_json(FINANCIALS_PATH, {})
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=(10, 30))
        resp.raise_for_status()
        rows = parse_annual(resp.text)
    except Exception as err:  # noqa: BLE001 - best effort; keep whatever a prior run stored
        print(f"- WARN: 연간 실적 수집 실패: {err}")
        print(f"        저장된 {len(data.get('annual', []))}개 연도를 그대로 둡니다.")
        save_json(FINANCIALS_PATH, data)
        sync_to_docs()
        return

    actual = [r for r in rows if not r["forecast"]]
    forecast = [r for r in rows if r["forecast"]]
    actual.sort(key=lambda r: r["fiscal_year_end"])

    data["annual"] = actual
    data["annual_forecast"] = forecast[0] if forecast else None
    data["annual_source"] = "Yahoo Japan 業績 (5802.T)"
    data["annual_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    save_json(FINANCIALS_PATH, data)
    sync_to_docs()

    print(f"- 연간 실적 {len(actual)}개 연도 수집 (단위: {data.get('unit_label', '백만 엔')})")
    for r in actual:
        print(f"    {r['fiscal_year_end']}  매출 {r['revenue']:>12,.0f}  영업이익 {r.get('operating_income') or 0:>10,.0f}")
    if data["annual_forecast"]:
        f = data["annual_forecast"]
        print(f"    {f['fiscal_year_end']}  매출 {f['revenue']:>12,.0f}  영업이익 {f.get('operating_income') or 0:>10,.0f}  (회사예상)")


if __name__ == "__main__":
    main()
