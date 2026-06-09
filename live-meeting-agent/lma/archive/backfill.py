"""Title every untitled past meeting in one pass.

  python -m lma.archive.backfill
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lma.archive import titler  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg_path = Path(__file__).resolve().parents[1] / "capture" / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    n = titler.backfill(cfg["output_dir"], cfg)
    print(f"titled {n} meeting(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
