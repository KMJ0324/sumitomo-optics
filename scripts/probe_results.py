"""Throwaway probe: (a) is the Chart.js CDN tag the page ships actually valid,
and (b) is there a scrapeable source for Sumitomo's quarterly results?

The dev sandbox can reach neither cdnjs nor finance.yahoo.co.jp, so both
questions get answered on a runner. (a) matters because if that tag 404s, no
chart on the page renders at all. (b) is the missing third series - the
results file has been all-nulls since day one because EDINET v2 needs a key
and Yahoo's US financial endpoints are crumb-gated, but Yahoo Japan's pages
are server-rendered and its price table already proved scrapeable.
"""
import re

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

CDN = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"
PAGES = [
    ("performance", "https://finance.yahoo.co.jp/quote/5802.T/performance"),
    ("financials", "https://finance.yahoo.co.jp/quote/5802.T/financials"),
    ("profile", "https://finance.yahoo.co.jp/quote/5802.T/profile"),
]


def main():
    print("=" * 72)
    print(f"[cdnjs] {CDN}")
    try:
        r = requests.get(CDN, timeout=40)
        head = r.text[:80].replace("\n", " ")
        print(f"    HTTP {r.status_code}  {len(r.content)} bytes  ct={r.headers.get('content-type')}")
        print(f"    head: {head}")
        print(f"    looks like Chart.js: {'Chart' in r.text[:4000]}")
    except Exception as err:  # noqa: BLE001
        print(f"    EXC {err}")

    for name, url in PAGES:
        print("=" * 72)
        print(f"[{name}] {url}")
        try:
            r = requests.get(url, headers=BROWSER, timeout=40)
        except Exception as err:  # noqa: BLE001
            print(f"    EXC {err}")
            continue
        print(f"    HTTP {r.status_code}  {len(r.content)} bytes")
        if r.status_code != 200:
            continue
        text = r.text
        # 売上高 / 営業利益 같은 항목명이 실제로 페이지에 있는지
        for term in ("売上高", "営業利益", "経常利益", "当期利益", "決算期", "四半期", "通期"):
            print(f"    {term}: {text.count(term)}회")
        flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
        for term in ("売上高", "営業利益"):
            for m in list(re.finditer(term, flat))[:2]:
                print(f"    ~ {flat[m.start():m.start() + 220]}")


if __name__ == "__main__":
    main()
