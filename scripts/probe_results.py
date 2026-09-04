"""Throwaway probe: find chapter 38 of Japan's export statistical schedule.

Whether silicon can be separated from InP comes down to one fact: does
Japan assign more than one 9-digit code under 3818.00? The schedule says so
directly, so locate its chapter-38 page from the index instead of guessing
URLs.
"""
import re

import requests

BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}
INDEX = "https://www.customs.go.jp/yusyutu/index.htm"


def main():
    r = requests.get(INDEX, headers=BROWSER, timeout=45)
    r.encoding = "shift_jis"
    print(f"index HTTP {r.status_code} {len(r.content)}B")
    hrefs = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
    print(f"  {len(hrefs)} links:")
    for h in hrefs[:50]:
        print(f"    {h}")

    # 챕터 목록 페이지로 보이는 링크를 따라가 38류를 찾습니다
    for h in hrefs:
        if not re.search(r"(20\d\d|data|index)", h):
            continue
        url = requests.compat.urljoin(INDEX, h)
        try:
            p = requests.get(url, headers=BROWSER, timeout=30)
        except Exception:  # noqa: BLE001
            continue
        p.encoding = "shift_jis"
        if p.status_code != 200:
            continue
        ch38 = re.findall(r'href="([^"]*(?:_38|38_|j_38)[^"]*)"', p.text)
        if ch38:
            print(f"\n  38류 링크 발견 @ {url}: {ch38[:5]}")
            target = requests.compat.urljoin(url, ch38[0])
            t = requests.get(target, headers=BROWSER, timeout=45)
            t.encoding = "shift_jis"
            print(f"  [GET] {target} -> HTTP {t.status_code} {len(t.content)}B")
            txt = t.text
            print(f"  '3818' {txt.count('3818')}회")
            i = txt.find("3818")
            if i > 0:
                flat = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt[max(0, i - 800):i + 2200]))
                print("  --- 3818 주변 ---")
                print("  " + flat[:1600])
            return
    print("\n  38류 페이지를 찾지 못했습니다")


if __name__ == "__main__":
    main()
