"""Throwaway probe: units, row schema, and a stable way to find the page.

The standalone page inlines everything in `const EMBEDDED = {...}`. Two
things left to settle before building on it: what `value_bn` is denominated
in (checkable against the Comtrade figures this dashboard already holds),
and whether the page URL - which carries a content hash - can be rediscovered
from the site index so a regenerated build doesn't silently break the feed.
"""
import json
import re

import requests

SITE = "https://must-charts.pages.dev/"
PAGE = "https://must-charts.pages.dev/japan-trade-standalone_1-92f1d9"
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}
CODES = ("900110100", "854470100", "854470910")


def extract_embedded(text):
    i = text.index("const EMBEDDED = ")
    start = text.index("{", i)
    depth, in_str, esc = 0, False, False
    for j in range(start, len(text)):
        c = text[j]
        if in_str:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
            continue
        if c == '"': in_str = True
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:j + 1])
    raise ValueError("EMBEDDED 객체를 닫지 못했습니다")


def main():
    print("=== 사이트 인덱스에서 페이지 찾기 ===")
    try:
        idx = requests.get(SITE, headers=BROWSER, timeout=60).text
        hits = sorted(set(re.findall(r'"(/japan-trade[^"]*?)"', idx)))
        print(f"  japan-trade 링크: {hits}")
    except Exception as err:  # noqa: BLE001
        print(f"  EXC {err}")

    text = requests.get(PAGE, headers=BROWSER, timeout=60).text
    emb = extract_embedded(text)
    print(f"\nEMBEDDED keys: {len(emb)} -> {list(emb)[:12]}")

    for code in CODES:
        key = next((k for k in emb if code in k), None)
        if not key:
            print(f"\n{code}: 블록 없음")
            continue
        blob = emb[key]
        print(f"\n=== {code}  ({key}) ===")
        print(f"  top keys: {list(blob)}")
        for k in ("name", "code", "unit", "unit_label", "value_unit", "latest_ym", "months", "source", "note"):
            if k in blob:
                print(f"    {k}: {blob[k]}")
        rows = blob.get("data", [])
        print(f"  rows={len(rows)}  first={rows[0]}")
        print(f"  last 2 = {rows[-2:]}")
        # 2026-06 값으로 단위를 역산합니다 (Comtrade 대비)
        for r in rows:
            if r.get("ym") in ("2026/06", "2026/07"):
                v, kg = r.get("value_bn"), r.get("kg")
                print(f"    {r['ym']}: value_bn={v} kg={kg} -> value_bn/kg={v / kg * 1e9 if kg else None:.1f} (엔 가정 시 엔/kg)")
        g = blob.get("groups", {})
        print(f"  groups.order={g.get('order')}")
        ser = g.get("series", {})
        if ser:
            k0 = list(ser)[0]
            print(f"  groups.series['{k0}'][-1] = {ser[k0][-1]}")


if __name__ == "__main__":
    main()
