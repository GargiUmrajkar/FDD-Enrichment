"""
Run the enrichment pipeline.

Usage:
    python scripts/enrich_franchise.py --input path/to/input.xlsx --output out.xlsx
"""
import sys, pathlib

# add repo/src to sys.path so "import enrichment" works
repo_root = pathlib.Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root / "src"))

import enrichment   # ← loads src/enrichment/__init__.py

if __name__ == "__main__":
    enrichment.main()