#!/usr/bin/env python3
import json
from pathlib import Path

# --- Load manifest
manifest_path = Path("custom_components/intuis_connect/manifest.json")
data = json.loads(manifest_path.read_text())

# --- Parse & bump patch
major, minor, patch = data["version"].split(".")
new_patch = int(patch) + 1
new_version = f"{major}.{minor}.{new_patch}"

# --- Write back
data["version"] = new_version
manifest_path.write_text(json.dumps(data, indent=2) + "\n")

# --- Emit for GitHub Actions
print(f"::set-output name=new_version::{new_version}")
