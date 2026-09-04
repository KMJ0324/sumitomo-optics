"""Throwaway probe: the right Chart.js URL, and the shape of Yahoo Japan's
quarterly results table.

The cdnjs path this project shipped 404s, so nothing charts. jsDelivr is the
host the sibling dashboard already uses successfully - confirm it, and ask
cdnjs's API what it actually calls the file, so the choice is informed.

Then dump the performance page's 業績 tables so the results parser can be
written against real markup rather than a guess.
"""
import re

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

CANDIDATES = [
    "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.js",
    "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.min.js",
]


def main():
    for url in CANDIDATES:
        try:
            r = requests.get(url, timeout=40)
            print(f"[{r.status_code}] {len(r.content):>8} B  {url}")
        except Exception as err:  # noqa: BLE001
            print(f"[EXC] {url}: {err}")

    try:
        j = requests.get("https://api.cdnjs.com/libraries/Chart.js?fields=version,files", timeout=40).json()
        files = [f for f in j.get("files", []) if f.endswith(".js") and "umd" in f or f in ("chart.min.js",)]
        print(f"\ncdnjs latest={j.get('version')} umd-ish files={files[:8]}")
    except Exception as err:  # noqa: BLE001
        print(f"cdnjs API: {err}")

    print("\n" + "=" * 72)
    r = requests.get("https://finance.yahoo.co.jp/quote/5802.T/performance", headers=BROWSER, timeout=40)
    print(f"performance HTTP {r.status_code} {len(r.content)}B")
    text = r.text

    # 표를 통째로 뜯어 헤더와 앞쪽 행들을 보여줍니다.
    for ti, table in enumerate(re.findall(r"<table[^>]*>(.*?)</table>", text, re.S | re.I)):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        if len(rows) < 2:
            continue
        parsed = []
        for row in rows[:9]:
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
            if cells:
                parsed.append(cells)
        if not parsed or not any("期" in " ".join(p) for p in parsed):
            continue
        print(f"\n--- table #{ti} ({len(rows)} rows)")
        for p in parsed:
            print("   ", " | ".join(p)[:200])


if __name__ == "__main__":
    main()
