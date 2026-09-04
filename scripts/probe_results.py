"""Throwaway probe (round 2): is quarterly results data reachable anywhere?

Yahoo Japan's performance page carries only four annual rows. Comparing
monthly exports against an annual step line is coarse, so check whether the
quarterly figures live behind a query param, or whether Sumitomo's own IR
site publishes a machine-readable file.
"""
import re

import requests

BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

URLS = [
    ("yahoo-perf-q", "https://finance.yahoo.co.jp/quote/5802.T/performance?styl=quarter"),
    ("yahoo-perf-qb", "https://finance.yahoo.co.jp/quote/5802.T/performance?styl=qb"),
    ("ir-en", "https://sumitomoelectric.com/ir/library/results"),
    ("ir-en2", "https://sumitomoelectric.com/ir/financial-data"),
    ("ir-jp", "https://sumitomoelectric.com/jp/ir/library/results"),
]


def dump_tables(text, label):
    found = 0
    for table in re.findall(r"<table[^>]*>(.*?)</table>", text, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        parsed = []
        for row in rows[:8]:
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
            if cells:
                parsed.append(cells)
        joined = " ".join(" ".join(p) for p in parsed)
        # 분기 표시가 들어 있는 표만
        if not re.search(r"(第[1-4一二三四]四半期|1Q|2Q|3Q|Q1|Q2|四半期)", joined):
            continue
        found += 1
        print(f"  --- {label} quarterly-ish table")
        for p in parsed:
            print("     ", " | ".join(p)[:190])
        if found >= 2:
            break
    if not found:
        print(f"  ({label}: 분기 표 없음)")


def main():
    for name, url in URLS:
        print("=" * 72)
        print(f"[{name}] {url}")
        try:
            r = requests.get(url, headers=BROWSER, timeout=40, allow_redirects=True)
        except Exception as err:  # noqa: BLE001
            print(f"    EXC {err}")
            continue
        print(f"    HTTP {r.status_code} {len(r.content)}B final={r.url}")
        if r.status_code != 200:
            continue
        dump_tables(r.text, name)
        # IR 페이지라면 데이터 파일 링크가 있는지
        links = re.findall(r'href="([^"]+\.(?:xlsx?|csv|pdf))"', r.text, re.I)
        if links:
            print(f"    data-ish links ({len(links)}): {links[:6]}")


if __name__ == "__main__":
    main()
