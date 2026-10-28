"""Offline metadata and local file consistency audit; does not validate clinical content."""
import json
from pathlib import Path
from datetime import date
import re

base = Path(__file__).resolve().parent
manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
issues = []
seen = set()
for index, entry in enumerate(manifest.get("documents", []), 1):
    name = entry.get("filename", "")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.txt", name):
        issues.append(f"Entry {index}: unsafe filename")
        continue
    if name in seen:
        issues.append(f"Entry {index}: duplicate filename {name}")
    seen.add(name)
    if not (base / name).is_file():
        issues.append(f"Entry {index}: missing local document {name}")
    for key in ("title", "publisher", "source_url", "reviewer", "reviewed_on"):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            issues.append(f"Entry {index}: missing {key}")
    if entry.get("approved") is not True:
        issues.append(f"Entry {index}: not approved")
    if isinstance(entry.get("source_url"), str) and not entry["source_url"].startswith("https://"):
        issues.append(f"Entry {index}: source_url should be HTTPS")
    try:
        if date.fromisoformat(entry["reviewed_on"]) > date.today():
            issues.append(f"Entry {index}: future review date")
    except (KeyError, TypeError, ValueError):
        issues.append(f"Entry {index}: invalid reviewed_on date")
print(f"Manifest entries: {len(manifest.get('documents', []))}; issues: {len(issues)}")
for issue in issues: print("-", issue)
raise SystemExit(1 if issues else 0)
