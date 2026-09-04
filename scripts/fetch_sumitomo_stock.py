"""Daily close prices for Sumitomo Electric Industries (5802.T).

The Korean names in this repo come from DART; Sumitomo Electric is a Tokyo
listing, so neither DART nor the Naver endpoint used by
fetch_stock_prices.py can serve it. Yahoo Finance's chart endpoint can, and
it returns split-adjusted closes, which is what a multi-year price line
wants.

Yahoo rate-limits that endpoint by IP, and GitHub's shared runner egress is
throttled often enough that it can come back empty for hours, so a second
provider backs it up: finance.yahoo.co.jp's server-rendered history table,
which sits on unrelated infrastructure (see jp_stock_history.py for why the
other candidates are unusable, and for the OHLC check that keeps a misparsed
table from reaching the chart).

Same best-effort contract as the other collectors: a failed or reshaped
response leaves whatever history a prior run already committed, and setting
`"source": "manual"` in data/sumitomo_stock.json turns automatic collection
off entirely so the `daily` array can be hand-maintained.
"""
import datetime
import sys
import time

import requests

from common import DATA_DIR, load_json, save_json, sync_to_docs
from jp_stock_history import fetch_daily_closes as fetch_from_yahoo_jp

STOCK_PATH = DATA_DIR / "sumitomo_stock.json"

SYMBOL = "5802.T"
# Yahoo serves the same chart data from two hosts and throttles them
# separately. Shared CI egress IPs get 429'd often enough that a single host
# with a short backoff fails outright, so alternate hosts across attempts.
CHART_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
CHART_URL = "https://{host}/v8/finance/chart/{symbol}"
# Yahoo caps a `1d` interval at 10y of history, which comfortably covers the
# monthly trade series this dashboard plots it against.
DEFAULT_RANGE = "10y"
# How far back the Yahoo Japan fallback walks. It pages 20 rows at a time, so
# unlike the US endpoint's single request the range has a real cost; this
# covers the monthly trade series with room to spare.
FALLBACK_START = "20210101"
# Backoff for a 429. Long by CLI standards, but this runs once a day in CI
# and a throttle that clears in a minute is worth waiting out.
BACKOFF_SECONDS = (5, 15, 30, 60, 90)
# Hard ceiling on the whole attempt loop. Waiting out a throttle is worth it;
# holding up the daily workflow indefinitely is not. The backoff schedule
# already bounds the normal case; this covers a response that arrives too
# slowly to trip the socket read timeout.
TOTAL_DEADLINE_SECONDS = 240
REQUEST_TIMEOUT = (10, 30)  # (connect, read)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_daily(symbol: str, range_: str) -> tuple[list[dict], dict]:
    """Return (daily closes, meta), retrying across hosts on a throttle."""
    payload = None
    last_err = None
    deadline = time.monotonic() + TOTAL_DEADLINE_SECONDS
    attempts = len(BACKOFF_SECONDS) + 1
    for attempt in range(attempts):
        host = CHART_HOSTS[attempt % len(CHART_HOSTS)]
        try:
            resp = requests.get(
                CHART_URL.format(host=host, symbol=symbol),
                params={"range": range_, "interval": "1d"},
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                raise RuntimeError(f"HTTP 429 from {host} (throttled)")
            resp.raise_for_status()
            payload = resp.json()
            break
        except Exception as err:  # noqa: BLE001 - retry loop for a flaky public endpoint
            last_err = err
            wait = BACKOFF_SECONDS[attempt] if attempt < len(BACKOFF_SECONDS) else 0
            remaining = deadline - time.monotonic()
            if attempt == attempts - 1 or remaining <= wait:
                raise RuntimeError(
                    f"chart fetch gave up after {attempt + 1} attempts "
                    f"({TOTAL_DEADLINE_SECONDS}초 예산 소진): {err}"
                ) from err
            print(f"    {err}; {wait}초 후 재시도")
            time.sleep(wait)

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        error = (payload.get("chart") or {}).get("error")
        raise RuntimeError(f"no chart result (error={error}, last_err={last_err})")

    res = result[0]
    meta = res.get("meta") or {}
    timestamps = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    # Daily bars are stamped at the session open in UTC epoch seconds, so the
    # exchange's own offset - not the runner's timezone - is what maps a bar
    # onto the Tokyo trading day it belongs to.
    offset = int(meta.get("gmtoffset") or 0)

    out = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue  # holidays and halted sessions come back as nulls
        date = datetime.datetime.fromtimestamp(ts + offset, tz=datetime.timezone.utc)
        out.append({"date": date.strftime("%Y%m%d"), "close": round(float(close), 2)})
    out.sort(key=lambda r: r["date"])
    return out, meta


# A corporate action the source hasn't adjusted for shows up as a one-day
# move no ordinary session produces. Sumitomo split 4:1 on 2026-06-29, and an
# unadjusted series draws that as a 76% collapse - so flag anything this size
# rather than let it reach the chart as if it were price action.
SPLIT_SUSPECT_MOVE = 0.35


def check_for_unadjusted_splits(daily: list[dict]) -> list[str]:
    warnings = []
    for prev, cur in zip(daily, daily[1:]):
        before, after = prev.get("close"), cur.get("close")
        if not before or after is None:
            continue
        if abs(after / before - 1) >= SPLIT_SUSPECT_MOVE:
            warnings.append(
                f"{prev['date']} {before} -> {cur['date']} {after} "
                f"({(after / before - 1) * 100:+.0f}%)"
            )
    return warnings


def merge_daily(existing: list[dict], fetched: list[dict], *, same_provider: bool) -> list[dict]:
    """Fold new closes into the stored history - but only within one provider.

    The two providers quote different things: Yahoo's chart endpoint returns
    split-adjusted closes (Sumitomo's 2021 prints come back near 380, a fifth
    of what the shares actually traded at), while Yahoo Japan's 終値 column is
    the unadjusted price. Splicing them would put a step change into the line
    at whatever date the provider happened to switch, so a change of provider
    replaces the series instead of merging into it.
    """
    if not same_provider:
        return sorted(fetched, key=lambda r: r["date"])
    by_date = {r["date"]: r for r in existing}
    for r in fetched:
        by_date[r["date"]] = r
    return sorted(by_date.values(), key=lambda r: r["date"])


def main():
    range_ = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RANGE
    entry = load_json(
        STOCK_PATH,
        {"symbol": SYMBOL, "name": "", "currency": "JPY", "source": "auto", "note": "", "daily": []},
    )

    if entry.get("source") == "manual":
        print(f"- {SYMBOL}: skipped (source=manual, hand-maintained)")
        save_json(STOCK_PATH, entry)
        sync_to_docs()
        return

    print(f"- {SYMBOL}: fetching daily closes (range={range_})")
    fetched, meta, provider = [], {}, None
    try:
        fetched, meta = fetch_daily(SYMBOL, range_)
        provider = "yahoo"
    except Exception as err:  # noqa: BLE001 - expected whenever the runner's IP is throttled
        print(f"    WARN: Yahoo(US) 실패: {err}")

    if not fetched:
        # Yahoo Japan serves the same listing from unrelated infrastructure,
        # so an IP throttle on the US endpoint says nothing about this one.
        print(f"    Yahoo Japan 히스토리 표로 재시도 ({FALLBACK_START}~)")
        try:
            fetched = fetch_from_yahoo_jp(
                SYMBOL, FALLBACK_START, datetime.date.today().strftime("%Y%m%d")
            )
            provider = "yahoo_jp"
        except Exception as err:  # noqa: BLE001 - best effort; keep prior history on failure
            print(f"    WARN: Yahoo Japan 실패: {err}")
            fetched = []

    if fetched:
        now_adjusted = all(r.get("adjusted", True) for r in fetched)
        # 기준가가 달라지면(수집원 교체, 무수정→수정주가) 이어붙이지 않고 대체합니다.
        same_basis = entry.get("provider") == provider and entry.get("adjusted", now_adjusted) == now_adjusted
        if entry.get("daily") and not same_basis:
            print(f"    NOTE: 기준가가 바뀌어(수집원 {entry.get('provider')} → {provider}, "
                  f"수정주가 {entry.get('adjusted')} → {now_adjusted}) 기존 시계열을 대체합니다.")
        entry["daily"] = merge_daily(entry.get("daily", []), fetched, same_provider=same_basis)
        entry["currency"] = meta.get("currency") or entry.get("currency") or "JPY"
        entry["name"] = meta.get("longName") or entry.get("name") or "Sumitomo Electric Industries, Ltd."
        entry["source"] = "auto"
        entry["provider"] = provider
        entry["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        entry["adjusted"] = now_adjusted
        print(f"    {provider}에서 {len(fetched)}일치 수신, 누적 {len(entry['daily'])}일 "
              f"({entry['daily'][0]['date']}~{entry['daily'][-1]['date']}), "
              f"{'수정주가' if entry['adjusted'] else '무수정 종가'}")
        suspect = check_for_unadjusted_splits(entry["daily"])
        if suspect:
            print(f"    WARN: 액면분할로 보이는 급변 {len(suspect)}건 - 조정되지 않은 계열일 수 있습니다:")
            for line in suspect[:5]:
                print(f"           {line}")
    else:
        print(f"    WARN: no price data returned for {SYMBOL}; keeping {len(entry.get('daily', []))} stored days")

    save_json(STOCK_PATH, entry)
    sync_to_docs()
    print("Done.")


if __name__ == "__main__":
    main()
