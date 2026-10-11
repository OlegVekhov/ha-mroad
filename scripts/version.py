"""Set manifest version: python scripts/version.py 0.1.1."""
import json
import re
import sys
from pathlib import Path

version = sys.argv[1] if len(sys.argv) == 2 else ""
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit("Usage: python scripts/version.py X.Y.Z")
path = Path(__file__).resolve().parents[1] / "custom_components/mroad/manifest.json"
data = json.loads(path.read_text())
data["version"] = version
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print(f"Version set to {version}")
