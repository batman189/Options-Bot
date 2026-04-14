"""Generate import/export matrix CSV."""
import os
import ast
import csv
import re

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
base = os.path.join(repo_root, "options-bot")
rows = []

# Python imports
for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git", "ui")]
    for f in sorted(files):
        if not f.endswith(".py"):
            continue
        fpath = os.path.join(root, f)
        rel = os.path.relpath(fpath, repo_root).replace(os.sep, "/")
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        rows.append({
                            "source_file": rel,
                            "import_type": "python_import",
                            "imported_name": alias.name,
                            "from_module": alias.name,
                            "target_file": "",
                            "line_number": node.lineno,
                            "is_used": "TRUE",
                            "notes": ""
                        })
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for alias in (node.names or []):
                        rows.append({
                            "source_file": rel,
                            "import_type": "python_from_import",
                            "imported_name": alias.name,
                            "from_module": mod,
                            "target_file": "",
                            "line_number": node.lineno,
                            "is_used": "TRUE",
                            "notes": ""
                        })
        except Exception as e:
            rows.append({
                "source_file": rel,
                "import_type": "error",
                "imported_name": str(e)[:80],
                "from_module": "",
                "target_file": "",
                "line_number": 0,
                "is_used": "",
                "notes": "parse error"
            })

# TypeScript/JS imports
ui_src = os.path.join(base, "ui", "src")
if os.path.exists(ui_src):
    for root, dirs, files in os.walk(ui_src):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for f in sorted(files):
            if not any(f.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx")):
                continue
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath, repo_root).replace(os.sep, "/")
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    content = fh.read()
                for m in re.finditer(r'import\s+(?:type\s+)?(?:\{([^}]+)\}|(\w+))\s+from\s+["\']([^"\']+)["\']', content):
                    named = m.group(1) or m.group(2) or ""
                    from_mod = m.group(3)
                    lineno = content[:m.start()].count("\n") + 1
                    for name in named.split(","):
                        name = name.strip().split(" as ")[0].strip()
                        if name:
                            rows.append({
                                "source_file": rel,
                                "import_type": "es_import",
                                "imported_name": name,
                                "from_module": from_mod,
                                "target_file": "",
                                "line_number": lineno,
                                "is_used": "TRUE",
                                "notes": ""
                            })
            except Exception:
                pass

# Write CSV
audit_dir = os.path.dirname(os.path.dirname(__file__))
outpath = os.path.join(audit_dir, "05_IMPORT_EXPORT_MATRIX.csv")
with open(outpath, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "source_file", "import_type", "imported_name", "from_module",
        "target_file", "line_number", "is_used", "notes"
    ])
    writer.writeheader()
    writer.writerows(rows)

print(f"Done: {len(rows)} import entries -> {outpath}")
