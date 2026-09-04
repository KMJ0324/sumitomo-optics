"""Throwaway probe: does Japan split HS 3818.00 at nine digits?

The user wants silicon wafers out of the substrate line. That is only
possible if Japan's export statistical schedule breaks 3818.00 into
sub-codes (e.g. silicon vs other). The schedule itself is published on
customs.go.jp, so ask it directly rather than guessing. Chapter 38 for a
few recent years, since the schedule is reissued annually.
"""
import re

import requests

BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}
CANDIDATES = [
    "https://www.customs.go.jp/yusyutu/2026_1/data/j_38.htm",
    "https://www.customs.go.jp/yusyutu/2025_4/data/j_38.htm",
    "https://www.customs.go.jp/yusyutu/2025_1/data/j_38.htm",
    "https://www.customs.go.jp/yusyutu/index.htm",
]


def main():
    for url in CANDIDATES:
        print("=" * 74)
        print(f"[GET] {url}")
        try:
            r = requests.get(url, headers=BROWSER, timeout=45)
        except Exception as err:  # noqa: BLE001
            print(f"    EXC {err}")
            continue
        r.encoding = r.apparent_encoding or "utf-8"
        print(f"    HTTP {r.status_code} {len(r.content)}B enc={r.encoding}")
        if r.status_code != 200:
            continue
        text = r.text
        if "index.htm" in url:
            links = sorted(set(re.findall(r'href="([^"]*yusyutu[^"]*)"', text)))[:12]
            print(f"    yusyutu 링크: {links}")
            continue

        i = text.find("3818")
        print(f"    '3818' 등장: {text.count('3818')}회")
        if i > 0:
            flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text[max(0, i - 1200):i + 2500]))
            print("    --- 3818 주변 ---")
            print("    " + flat[:1800])


if __name__ == "__main__":
    main()
