"""Throwaway probe: the full code list across every standalone build.

3818.00 lumps all doped wafers together - silicon dominates it, so an InP
surge is invisible inside it. If the source carries a finer sub-code (or any
compound-semiconductor line), that is the fix; if not, the honest answer is
that this series cannot show InP and should say so or go.
"""
import sys

sys.path.insert(0, "scripts")
import requests

from fetch_jp_trade_9digit import collect_blocks, discover_pages

session = requests.Session()
urls = discover_pages(session)
print(f"페이지 {len(urls)}개: {[u.rsplit('/', 1)[-1] for u in urls]}\n")
blocks = collect_blocks(session, urls)
print(f"\n총 {len(blocks)}개 코드:\n")
for code in sorted(blocks):
    b = blocks[code]
    rows = b.get("data", [])
    last = rows[-1] if rows else {}
    print(f"  {code}  {b.get('name','')[:52]:54s} {b.get('latest_ym')} "
          f"{len(rows):3d}개월 최신 {last.get('value_bn', 0):8.3f}십억엔")

print("\n=== 화합물 반도체/기판 관련 코드 탐색 ===")
for code, b in sorted(blocks.items()):
    name = b.get("name", "")
    if code.startswith("3818") or any(k in name for k in ("기판", "웨이퍼", "InP", "인듐", "화합물", "반도체")):
        print(f"  후보: {code} {name}")
else:
    print("  (3818 계열 없음)" if not any(c.startswith("3818") for c in blocks) else "")
