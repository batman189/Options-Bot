"""Backfill exact line numbers for UI controls in 07_UI_CONTROL_MATRIX.csv."""
import os, re, csv

repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ui_src = os.path.join(repo, "options-bot", "ui", "src")
audit = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Read all source files
sources = {}
for root, dirs, files in os.walk(ui_src):
    dirs[:] = [d for d in dirs if d != "node_modules"]
    for f in files:
        if f.endswith(('.tsx', '.ts')):
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath, ui_src).replace(os.sep, "/")
            with open(fpath, "r", encoding="utf-8") as fh:
                sources[rel] = fh.readlines()

# Map of handler/label patterns to line numbers
def find_line(file_key, patterns):
    """Find line number in file matching any pattern."""
    # Normalize file_key: strip pages/ or components/ prefix if needed
    candidates = [file_key]
    if "/" not in file_key:
        candidates.extend([f"pages/{file_key}", f"components/{file_key}"])

    for fk in candidates:
        if fk in sources:
            lines = sources[fk]
            for pat in patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pat, line):
                        return fk, i
    return file_key, 0

# Read current CSV
csv_path = os.path.join(audit, "07_UI_CONTROL_MATRIX.csv")
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames
    rows = list(reader)

# Add notes column if not present
if "notes" not in fields:
    fields = list(fields) + ["notes"]

# Backfill each row
filled = 0
unfilled = 0

for row in rows:
    ctrl_id = row.get("control_id", "")
    handler = row.get("event_handler", "")
    label = row.get("label_text", "").strip('"')
    comp = row.get("component_file", "")

    # Build search patterns from handler and label
    patterns = []
    if handler:
        h = handler.strip('"').split("(")[0].strip()
        if h:
            patterns.append(re.escape(h))
    if label:
        # Use key words from label
        words = label.split()
        if len(words) >= 2:
            patterns.append(re.escape(words[0]) + r".*" + re.escape(words[1]))

    if not patterns:
        patterns = [ctrl_id]

    file_key, lineno = find_line(comp, patterns)

    # Extract verdict commentary into notes
    verdict = row.get("verdict", "").strip('"')
    notes = ""
    if " — " in verdict:
        parts = verdict.split(" — ", 1)
        verdict = parts[0].strip()
        notes = parts[1].strip()
    elif " - " in verdict:
        parts = verdict.split(" - ", 1)
        verdict = parts[0].strip()
        notes = parts[1].strip()

    # Normalize verdict to pure PASS or FAIL
    if verdict.startswith("PASS"):
        verdict = "PASS"
    elif verdict.startswith("FAIL"):
        verdict = "FAIL"

    row["verdict"] = verdict
    row["line_number"] = str(lineno) if lineno > 0 else ""

    # Store notes
    if "notes" in row:
        existing_notes = row.get("notes", "")
        if notes and not existing_notes:
            row["notes"] = notes
        elif notes:
            row["notes"] = existing_notes + "; " + notes
    else:
        row["notes"] = notes

    if lineno > 0:
        filled += 1
    else:
        unfilled += 1

# Write back
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"Filled: {filled}, Unfilled: {unfilled}, Total: {len(rows)}")
