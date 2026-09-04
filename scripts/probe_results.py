"""Throwaway probe: pull the embedded structure out of the standalone page.

catalog.json / data/exp-*.json 404 - the standalone build inlines everything
into the 563 KB HTML. Find where a given 9-digit code's block starts and dump
enough around it to write a parser: what the value field is denominated in,
whether weight and destinations ride along, and whether anything carries 税関.
"""
import json
import re

import requests

URL = "https://must-charts.pages.dev/japan-trade-standalone_1-92f1d9"
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}


def main():
    r = requests.get(URL, headers=BROWSER, timeout=60)
    text = r.text
    print(f"HTTP {r.status_code} {len(text)} chars")

    # 인라인 JSON 덩어리를 찾습니다: <script> 안의 큰 객체/배열
    for m in list(re.finditer(r"(?:const|let|var|window\.)\s*([A-Za-z_$][\w$]*)\s*=\s*(\[|\{)", text))[:40]:
        name = m.group(1)
        if len(name) < 3:
            continue
        print(f"  var {name} at {m.start()}  -> {text[m.start():m.start()+90]!r}")

    print("\n=== 코드별 블록 위치 ===")
    for code in ("854470100", "854470910", "900110100"):
        idx = [m.start() for m in re.finditer(f'"{code}"', text)]
        print(f"  {code}: {len(idx)} hits at {idx[:6]}")

    # 카탈로그 항목 전체를 뽑아봅니다
    print("\n=== 카탈로그 항목 ===")
    for m in re.finditer(r'\{"id":"(?:exp|imp)-\d{9}".{0,400}?\}\]?\}', text):
        chunk = m.group(0)
        try:
            name = re.search(r'"name":"([^"]*)"', chunk).group(1)
            code = re.search(r'"code":"(\d{9})"', chunk).group(1)
            direction = re.search(r'"direction":"([^"]*)"', chunk)
            latest = re.search(r'"latest_ym":"([^"]*)"', chunk)
            months = re.search(r'"months":(\d+)', chunk)
            tags = re.findall(r'"label":"([^"]*)"', chunk)
            print(f"  {code} | {name} | {direction.group(1) if direction else '?'} | "
                  f"latest {latest.group(1) if latest else '?'} | {months.group(1) if months else '?'}개월 | tags={tags}")
        except AttributeError:
            continue

    print("\n=== 854470100 주변 원문 ===")
    i = text.find('"code":"854470100"')
    if i > 0:
        print(text[max(0, i - 1500):i + 900])

    print("\n=== 세관 관련 표기 ===")
    for term in ("税関", "세관", "customs", "横浜", "요코하마", "Yokohama"):
        print(f"  {term!r}: {text.count(term)}")


if __name__ == "__main__":
    main()
