"""Fallback daily-close source: finance.yahoo.co.jp's history table.

Yahoo's US chart API is the primary source, but it rate-limits by IP and
GitHub's shared runner egress is throttled often enough to come back empty
for hours. Yahoo Japan serves the same listing from unrelated
infrastructure and renders its history table server-side, so it works when
the US endpoint won't (Stooq gates on JavaScript, kabutan returns a human
-verification page, minkabu 403s - none of them are usable).

The table is HTML, not an API, so the column order is not guaranteed. Rather
than trusting a fixed position, every row is parsed cell-by-cell and checked
against the one invariant an OHLC row must satisfy - low <= open, close <=
high - and a page that fails is rejected whole. A misparse then shows up as
"no data" instead of as plausible-looking wrong prices on the chart.

The close taken is the table's **adjusted** close (調整後終値), not the raw
one. Sumitomo split 4:1 on 2026-06-29, and a raw series draws that as a 76%
one-day collapse that never happened. Yahoo's adjusted column already carries
the split back through the history, which is also the basis the US chart
endpoint quotes - so the two providers agree and neither needs a
split-detection heuristic guessing at whether a big drop was a split or a
crash.
"""
import re
import time

import requests

HISTORY_URL = "https://finance.yahoo.co.jp/quote/{symbol}/history"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
ROWS_PER_PAGE = 20
MAX_PAGES = 400  # ~8000 trading days, far past any range this dashboard asks for

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
DATE_RE = re.compile(r"^(20\d{2})\D+(\d{1,2})\D+(\d{1,2})\D*$")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _number(cell: str):
    cell = cell.replace(",", "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)?", cell):
        return None
    return float(cell)


def parse_history_page(html: str) -> list[dict]:
    """Rows of {date, close, raw_close, adjusted} from one history page.

    Columns are 日付 / 始値 / 高値 / 安値 / 終値 / 出来高 / 調整後終値. `close`
    is the adjusted figure when the row carries one, since that is the series
    a price chart wants; `raw_close` keeps the as-traded number.

    Raises ValueError if a row looks like a price row but fails the OHLC
    invariant - that means the columns are not where we think they are, and
    guessing would put wrong numbers on the chart.
    """
    out = []
    for row_html in ROW_RE.findall(html):
        cells = [_text(c) for c in CELL_RE.findall(row_html)]
        if len(cells) < 5:
            continue
        m = DATE_RE.match(cells[0])
        if not m:
            continue
        numbers = [_number(c) for c in cells[1:]]
        if any(n is None for n in numbers[:4]):
            continue
        open_, high, low, close = numbers[:4]
        if not (low <= open_ <= high and low <= close <= high):
            raise ValueError(
                f"OHLC 정합성 실패 ({cells[0]}: 시가 {open_} 고가 {high} 저가 {low} 종가 {close}) "
                "- 표의 열 순서가 예상과 다릅니다."
            )
        # 출来高 다음 열이 조정 종가. 없으면 원 종가를 그대로 씁니다.
        adjusted = numbers[5] if len(numbers) > 5 and numbers[5] else None
        year, month, day = (int(g) for g in m.groups())
        out.append({
            "date": f"{year:04d}{month:02d}{day:02d}",
            "close": round(adjusted if adjusted else close, 2),
            "raw_close": round(close, 2),
            "adjusted": adjusted is not None,
        })
    return out


def fetch_daily_closes(symbol: str, start: str, end: str, *, session=None, pause: float = 0.4) -> list[dict]:
    """Walk the paginated history table from `end` back to `start` (YYYYMMDD).

    Pages run newest-first. The `from`/`to` parameters are the server's to
    honour or ignore, so the range is enforced here too: rows outside it are
    dropped, and the walk stops as soon as a page has run past `start` -
    otherwise an ignored `from` would page back through the stock's entire
    history to the MAX_PAGES cap.
    """
    http = session or requests.Session()
    collected: dict[str, dict] = {}
    pages_read = 0
    for page in range(1, MAX_PAGES + 1):
        resp = http.get(
            HISTORY_URL.format(symbol=symbol),
            params={"from": start, "to": end, "timeFrame": "d", "page": str(page)},
            headers=HEADERS,
            timeout=(10, 30),
        )
        resp.raise_for_status()
        rows = parse_history_page(resp.text)
        pages_read += 1
        in_range = [r for r in rows if start <= r["date"] <= end]
        fresh = [r for r in in_range if r["date"] not in collected]
        for r in fresh:
            collected[r["date"]] = r

        if not rows:
            break  # past the end of the table
        if any(r["date"] < start for r in rows):
            break  # this page crossed the start date; nothing older is wanted
        if not fresh:
            break  # a repeated page means paging has stopped advancing
        if len(rows) < ROWS_PER_PAGE:
            break  # a short page is the last one
        time.sleep(pause)
    print(f"    Yahoo Japan: {pages_read}페이지에서 {len(collected)}일치 파싱")
    return sorted(collected.values(), key=lambda r: r["date"])
