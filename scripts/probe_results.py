"""Throwaway probe: the must-charts catalog and one data file.

The page embeds a catalog of 9-digit Japanese statistical codes with
per-code JSON files (data/exp-*.json). Confirm the catalog is fetchable on
its own, what optical codes it carries, what `value_bn` is denominated in,
and - the question that decides how far this can go - whether anything in
it breaks out 税関 (customs office), since Sumitomo ships through Yokohama.
"""
import json
import re

import requests

BASE = "https://must-charts.pages.dev/japan-trade-standalone_1-92f1d9"
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}


def get(url):
    r = requests.get(url, headers=BROWSER, timeout=45)
    print(f"[{r.status_code}] {len(r.content):>9} B  {url}")
    return r


def main():
    for path in ("/catalog.json", "/data/exp-854470100.json"):
        try:
            get(BASE + path)
        except Exception as err:  # noqa: BLE001
            print(f"    EXC {err}")

    r = get(BASE + "/catalog.json")
    if r.status_code == 200:
        try:
            cat = r.json()
            items = cat if isinstance(cat, list) else cat.get("items") or cat.get("charts") or []
            print(f"\ncatalog entries: {len(items)}")
            for it in items:
                if not isinstance(it, dict):
                    continue
                code = str(it.get("code", ""))
                if code.startswith(("8544", "9001", "8536", "8541", "3818")):
                    print(f"  {it.get('id')}  {code}  {it.get('name')}  "
                          f"dir={it.get('direction')} latest={it.get('latest_ym')} months={it.get('months')} "
                          f"file={it.get('file')} tags={[t.get('label') for t in it.get('tags', [])]}")
            print("\n  (전체 코드 목록)")
            print("   ", [str(i.get("code")) for i in items if isinstance(i, dict)][:40])
        except Exception as err:  # noqa: BLE001
            print(f"  catalog parse: {err}: {r.text[:200]}")

    d = get(BASE + "/data/exp-854470100.json")
    if d.status_code == 200:
        j = d.json()
        print("\ntop-level keys:", list(j.keys()))
        for k in ("code", "name", "unit", "unit_label", "value_unit", "direction", "latest_ym", "months", "source", "note", "updated_at"):
            if k in j:
                print(f"  {k}: {j[k]}")
        rows = j.get("data", [])
        print(f"  data rows: {len(rows)}; first={rows[0] if rows else None}")
        print(f"  last 3: {rows[-3:]}")
        g = j.get("groups", {})
        print(f"  groups keys: {list(g.keys())[:6]}; order={g.get('order')}")
        # 세관 관련 필드가 있는지
        flat = json.dumps(j, ensure_ascii=False)
        for term in ("税関", "세관", "customs", "yokohama", "横浜", "요코하마", "port"):
            print(f"  {term!r}: {flat.count(term)}")


if __name__ == "__main__":
    main()
