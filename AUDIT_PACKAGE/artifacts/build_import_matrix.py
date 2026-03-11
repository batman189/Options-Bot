"""
Build 05_IMPORT_EXPORT_MATRIX.csv by scanning every Python and TypeScript file.
Extracts all import statements, checks if imported symbols are used in the file body,
and writes results with PASS/FAIL verdict.
"""
import ast
import csv
import os
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Trading Bot v2\Options-Bot\options-bot")
UI_SRC = PROJECT_ROOT / "ui" / "src"
OUTPUT = Path(r"C:\Trading Bot v2\Options-Bot\AUDIT_PACKAGE\05_IMPORT_EXPORT_MATRIX.csv")

# ── Collect files ──────────────────────────────────────────────
PYTHON_FILES = sorted(PROJECT_ROOT.rglob("*.py"))
# Exclude node_modules, dist, etc.
PYTHON_FILES = [f for f in PYTHON_FILES if "node_modules" not in str(f) and "__pycache__" not in str(f)]

TS_FILES = sorted(list(UI_SRC.rglob("*.ts")) + list(UI_SRC.rglob("*.tsx")))
TS_FILES = [f for f in TS_FILES if "node_modules" not in str(f)]

def rel(path: Path) -> str:
    """Return path relative to project root."""
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ── Python import extraction ───────────────────────────────────
def extract_python_imports(filepath: Path):
    """Extract all imports from a Python file, including inline/deferred ones."""
    source = filepath.read_text(encoding="utf-8", errors="replace")
    lines = source.split("\n")
    results = []

    # --- AST-based extraction for top-level imports ---
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None

    # We also do regex to catch inline imports inside functions
    # First pass: AST for structured extraction
    if tree:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    stmt = f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")
                    results.append({
                        "statement": stmt,
                        "from": alias.name,
                        "symbols": alias.asname or alias.name.split(".")[-1],
                        "all_symbols": [alias.asname or alias.name.split(".")[-1]],
                        "lineno": node.lineno,
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [a.name for a in node.names]
                asnames = [a.asname for a in node.names]
                symbols_list = []
                for a in node.names:
                    symbols_list.append(a.asname if a.asname else a.name)

                names_str = ", ".join(
                    (f"{a.name} as {a.asname}" if a.asname else a.name) for a in node.names
                )
                stmt = f"from {module} import {names_str}"
                results.append({
                    "statement": stmt,
                    "from": module,
                    "symbols": ", ".join(symbols_list),
                    "all_symbols": symbols_list,
                    "lineno": node.lineno,
                })

    # Check usage for each imported symbol
    for entry in results:
        used_symbols = []
        unused_symbols = []
        for sym in entry["all_symbols"]:
            if sym == "*":
                used_symbols.append(sym)
                continue
            # Check if symbol appears in code OUTSIDE of import lines
            # Build a pattern that looks for the symbol as a word boundary
            pattern = re.compile(r'\b' + re.escape(sym) + r'\b')
            # Check all non-import lines
            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    continue
                if pattern.search(line):
                    found = True
                    break
            if found:
                used_symbols.append(sym)
            else:
                unused_symbols.append(sym)

        entry["used"] = "YES" if len(unused_symbols) == 0 else "PARTIAL" if used_symbols else "NO"
        entry["verdict"] = "PASS" if len(unused_symbols) == 0 else "FAIL"

    return results


# ── TypeScript import extraction ───────────────────────────────
def extract_ts_imports(filepath: Path):
    """Extract all imports from a TypeScript/TSX file, including multi-line."""
    source = filepath.read_text(encoding="utf-8", errors="replace")
    lines = source.split("\n")
    results = []

    # First, join multi-line imports into single statements
    # Walk through lines and collect complete import statements
    import_stmts = []  # (statement_text, start_line)
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("import"):
            stmt_lines = [lines[i]]
            start_line = i + 1
            # Check if this import spans multiple lines (has { but no })
            combined = stripped
            while ("from " not in combined or combined.endswith(",")) and i + 1 < len(lines):
                # Also check: if we have { but no }, keep reading
                if "{" in combined and "}" not in combined:
                    i += 1
                    stmt_lines.append(lines[i])
                    combined = " ".join(l.strip() for l in stmt_lines)
                elif combined.endswith(",") or combined.endswith("{"):
                    i += 1
                    stmt_lines.append(lines[i])
                    combined = " ".join(l.strip() for l in stmt_lines)
                else:
                    break
            # Normalize whitespace
            full_stmt = " ".join(l.strip() for l in stmt_lines)
            import_stmts.append((full_stmt, start_line))
        i += 1

    import_pattern = re.compile(
        r"""^import\s+"""
        r"""(?:type\s+)?"""
        r"""(?:"""
        r"""\{([^}]+)\}"""  # named imports { X, Y }
        r"""|(\w+)"""  # default import
        r"""|(\*\s+as\s+\w+)"""  # namespace import
        r""")?"""
        r"""\s*(?:,\s*\{([^}]+)\})?\s*"""  # optional additional named after default
        r"""(?:from\s+)?"""
        r"""['"]([^'"]+)['"]"""  # module path
    )

    for stmt, lineno in import_stmts:
        m = import_pattern.match(stmt)
        if m:
            named1 = m.group(1)
            default_imp = m.group(2)
            namespace = m.group(3)
            named2 = m.group(4)
            module = m.group(5)

            symbols = []
            if named1:
                for s in named1.split(","):
                    s = s.strip()
                    if " as " in s:
                        symbols.append(s.split(" as ")[1].strip())
                    elif s:
                        symbols.append(s)
            if default_imp:
                symbols.append(default_imp)
            if namespace:
                sym = namespace.replace("* as ", "").strip()
                symbols.append(sym)
            if named2:
                for s in named2.split(","):
                    s = s.strip()
                    if " as " in s:
                        symbols.append(s.split(" as ")[1].strip())
                    elif s:
                        symbols.append(s)

            if not symbols and module:
                symbols = ["(side-effect)"]

            # Clean up the statement for CSV readability
            display_stmt = re.sub(r'\s+', ' ', stmt).strip()
            if display_stmt.endswith(";"):
                display_stmt = display_stmt[:-1]

            results.append({
                "statement": display_stmt,
                "from": module or "",
                "symbols": ", ".join(symbols),
                "all_symbols": symbols,
                "lineno": lineno,
            })
        else:
            simple = re.match(r"import\s+['\"]([^'\"]+)['\"]", stmt)
            if simple:
                results.append({
                    "statement": stmt.strip(),
                    "from": simple.group(1),
                    "symbols": "(side-effect)",
                    "all_symbols": ["(side-effect)"],
                    "lineno": lineno,
                })

    # Check usage
    for entry in results:
        used_symbols = []
        unused_symbols = []
        for sym in entry["all_symbols"]:
            if sym == "(side-effect)":
                used_symbols.append(sym)
                continue
            pattern = re.compile(r'\b' + re.escape(sym) + r'\b')
            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("import "):
                    continue
                if pattern.search(line):
                    found = True
                    break
            if found:
                used_symbols.append(sym)
            else:
                unused_symbols.append(sym)

        entry["used"] = "YES" if len(unused_symbols) == 0 else "PARTIAL" if used_symbols else "NO"
        entry["verdict"] = "PASS" if len(unused_symbols) == 0 else "FAIL"

    return results


# ── Main ───────────────────────────────────────────────────────
rows = []
imp_id = 0

print(f"Scanning {len(PYTHON_FILES)} Python files...")
for fp in PYTHON_FILES:
    try:
        imports = extract_python_imports(fp)
    except Exception as e:
        print(f"  ERROR reading {fp}: {e}")
        continue
    for entry in imports:
        imp_id += 1
        rows.append({
            "import_id": f"IMP-{imp_id:03d}",
            "source_file": rel(fp),
            "import_statement": entry["statement"],
            "imported_from": entry["from"],
            "imported_symbols": entry["symbols"],
            "used_in_file": entry["used"],
            "verdict": entry["verdict"],
        })

print(f"Scanning {len(TS_FILES)} TypeScript files...")
for fp in TS_FILES:
    try:
        imports = extract_ts_imports(fp)
    except Exception as e:
        print(f"  ERROR reading {fp}: {e}")
        continue
    for entry in imports:
        imp_id += 1
        rows.append({
            "import_id": f"IMP-{imp_id:03d}",
            "source_file": rel(fp),
            "import_statement": entry["statement"],
            "imported_from": entry["from"],
            "imported_symbols": entry["symbols"],
            "used_in_file": entry["used"],
            "verdict": entry["verdict"],
        })

# Write CSV
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "import_id", "source_file", "import_statement",
        "imported_from", "imported_symbols", "used_in_file", "verdict"
    ])
    writer.writeheader()
    writer.writerows(rows)

print(f"\nDone. Wrote {len(rows)} import entries to {OUTPUT}")
# Summary
pass_count = sum(1 for r in rows if r["verdict"] == "PASS")
fail_count = sum(1 for r in rows if r["verdict"] == "FAIL")
print(f"  PASS: {pass_count}  |  FAIL: {fail_count}")
