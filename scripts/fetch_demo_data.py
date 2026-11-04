#!/usr/bin/env python3
"""Fetch the three-field demonstration's 32 pinned assets into data/ (96 MB total)."""
import json
import sys
import urllib.request
from pathlib import Path

from fetch_data import BASE, main as fetch_base, sha256


def main():
    root = Path(__file__).resolve().parent.parent
    fixture = root / "fixture" / "three-fields"
    manifest = json.loads((fixture / "manifest.json").read_text())
    for item in manifest["csv_files"]:
        if sha256(fixture / item["path"]) != item["sha256"]:
            sys.exit(f"fixture hash mismatch: {item['path']}")
    fetch_base()
    for item in manifest["additional_files"]:
        dest = root / "data" / item["path"].rsplit("/", 1)[1]
        if dest.exists() and dest.stat().st_size == item["bytes"] and sha256(dest) == item["sha256"]:
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        print(f"fetching {dest.name} ({item['bytes'] / 1e6:.1f} MB)", flush=True)
        urllib.request.urlretrieve(BASE + item["path"], tmp)
        if tmp.stat().st_size != item["bytes"] or sha256(tmp) != item["sha256"]:
            sys.exit(f"size or sha256 mismatch for {dest.name}; refusing to use it ({tmp} kept)")
        tmp.rename(dest)
    print(f"three-field data ok: {manifest['unique_assets']} files, {manifest['total_asset_bytes']} bytes")


if __name__ == "__main__":
    main()
