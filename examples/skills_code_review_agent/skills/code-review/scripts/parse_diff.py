#!/usr/bin/env python3
"""Parse a unified diff and extract change features.

Usage:
    python3 parse_diff.py < input.diff
    python3 parse_diff.py --file input.diff

Outputs JSON summary of changed files, hunks, and line numbers.
"""

import json
import re
import sys
from typing import Optional


def parse_diff(diff_text: str) -> dict:
    """Parse unified diff and return structured summary."""
    files = []
    current_file: Optional[dict] = None
    current_hunk: Optional[dict] = None

    for line in diff_text.splitlines():
        # File headers
        if line.startswith("--- "):
            if current_file:
                files.append(current_file)
            current_file = {"old_path": line[4:].strip(), "new_path": "", "hunks": []}
            continue
        if line.startswith("+++ ") and current_file:
            current_file["new_path"] = line[4:].strip()
            continue

        # Hunk header
        hunk_match = re.match(r"^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
        if hunk_match and current_file is not None:
            current_hunk = {
                "old_start": int(hunk_match.group(1)),
                "old_count": int(hunk_match.group(2)) if hunk_match.group(2) else 1,
                "new_start": int(hunk_match.group(3)),
                "new_count": int(hunk_match.group(4)) if hunk_match.group(4) else 1,
                "added_lines": [],
                "removed_lines": [],
            }
            current_file["hunks"].append(current_hunk)
            continue

        # Track line numbers
        if current_hunk is not None:
            if line.startswith("+"):
                current_hunk["added_lines"].append(
                    current_hunk["new_start"] + len(current_hunk["added_lines"])
                    + len(current_hunk.get("_context_lines", 0))
                )
            elif line.startswith("-"):
                current_hunk["removed_lines"].append(
                    current_hunk["old_start"] + len(current_hunk["removed_lines"])
                    + len(current_hunk.get("_context_lines", 0))
                )
            elif line.startswith(" "):
                current_hunk.setdefault("_context_lines", 0)
                current_hunk["_context_lines"] += 1

    if current_file:
        files.append(current_file)

    # Clean up internal tracking fields
    for f in files:
        for h in f["hunks"]:
            h.pop("_context_lines", None)

    return {
        "file_count": len(files),
        "files": files,
    }


def main() -> None:
    diff_text: str
    if len(sys.argv) > 2 and sys.argv[1] == "--file":
        with open(sys.argv[2]) as f:
            diff_text = f.read()
    else:
        diff_text = sys.stdin.read()

    if not diff_text.strip():
        print(json.dumps({"file_count": 0, "files": []}))
        return

    result = parse_diff(diff_text)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()