"""Throwaway probe: what does must-charts.pages.dev serve, and at what
granularity?

The anchors the user pointed at (#exp-854470100, #exp-854470910) are 9-digit
Japanese statistical codes - the sub-splits of HS 8544.70 that Japan Customs
actually reports. That is finer than the 6-digit HS this dashboard pulls from
Comtrade, and a source carrying them is likely working from MOF's own release
(and therefore in yen). Worth knowing exactly what is behind the page before
deciding whether to switch.
"""
import re

import requests

URLS = [
    "https://must-charts.pages.dev/japan-trade-standalone_1-92f1d9",
    "https://must-charts.pages.dev/",
]
BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def main():
    for url in URLS:
        print("=" * 74)
        print(f"[GET] {url}")
        try:
            r = requests.get(url, headers=BROWSER, timeout=45)
        except Exception as err:  # noqa: BLE001
            print(f"    EXC {err}")
            continue
        print(f"    HTTP {r.status_code}  {len(r.content)} bytes  ct={r.headers.get('content-type')}")
        if r.status_code != 200:
            continue
        text = r.text

        codes = sorted(set(re.findall(r"\b(\d{9})\b", text)))
        print(f"    9-digit codes: {len(codes)} -> {codes[:16]}")
        for term in ("円", "千円", "JPY", "USD", "kg", "数量", "金額", "value", "quantity", "月"):
            print(f"      {term!r}: {text.count(term)}")

        # 데이터가 페이지에 박혀 있는지, 아니면 별도 파일을 부르는지
        srcs = sorted(set(re.findall(r'(?:src|href)="([^"]+\.(?:js|json|csv))"', text)))
        print(f"    asset refs: {srcs[:10]}")
        for m in list(re.finditer(r'(?:fetch|import)\(["\']([^"\']+)["\']', text))[:8]:
            print(f"      fetches: {m.group(1)}")
        # 인라인 JSON 흔적
        for key in ('"data"', '"series"', '"months"', '"value"', '854470'):
            i = text.find(key)
            if i > 0:
                print(f"    ~{key}: {re.sub(r'\\s+', ' ', text[max(0,i-90):i+200])}")


if __name__ == "__main__":
    main()
