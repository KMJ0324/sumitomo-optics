"""Shared file plumbing for the collectors.

`data/` is the record of what has been collected - hand-editable, committed
to git - and `docs/data/` is the deploy copy the static page fetches
same-origin from GitHub Pages. Every collector writes the former and then
mirrors to the latter, so the two never drift.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DATA_DIR = ROOT / "docs" / "data"

SYNCED_FILES = (
    "jp_trade_categories.json",
    "jp_trade_exports.json",
    "jp_trade_exports_jpy.json",
    "jp_trade_exports_estat.json",
    "sumitomo_stock.json",
    "sumitomo_financials.json",
)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sync_to_docs():
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in SYNCED_FILES:
        src = DATA_DIR / name
        if src.exists():
            save_json(DOCS_DATA_DIR / name, load_json(src, {}))
