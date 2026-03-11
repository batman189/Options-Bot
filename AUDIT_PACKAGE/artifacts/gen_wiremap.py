"""Generate exhaustive wiremap for all functions/classes/methods."""
import os
import ast
import re

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
base = os.path.join(repo_root, "options-bot")

# Phase 1: Collect all symbols
symbols = []  # (file, name, type, lineno, end_lineno)

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
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append((rel, node.name, "function", node.lineno, getattr(node, "end_lineno", node.lineno)))
                elif isinstance(node, ast.ClassDef):
                    symbols.append((rel, node.name, "class", node.lineno, getattr(node, "end_lineno", node.lineno)))
                    # Also get methods
                    for item in ast.iter_child_nodes(node):
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            symbols.append((rel, f"{node.name}.{item.name}", "method", item.lineno, getattr(item, "end_lineno", item.lineno)))
        except Exception:
            pass

# Phase 2: For each symbol, find callers via grep
# Read all source content into memory
file_contents = {}
for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git")]
    for f in sorted(files):
        if not any(f.endswith(ext) for ext in (".py", ".ts", ".tsx", ".js")):
            continue
        fpath = os.path.join(root, f)
        rel = os.path.relpath(fpath, repo_root).replace(os.sep, "/")
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                file_contents[rel] = fh.read()
        except:
            pass

output = []
wire_id = 0

for file_path, name, sym_type, lineno, end_lineno in symbols:
    wire_id += 1
    # Get bare name for searching (e.g., "ClassName.method" -> "method")
    bare = name.split(".")[-1]

    # Find callers
    callers = []
    for other_file, other_content in file_contents.items():
        if other_file == file_path and sym_type != "method":
            # Skip self-references for top-level functions (but allow for methods)
            pattern = re.compile(r'\b' + re.escape(bare) + r'\s*\(')
            for m in pattern.finditer(other_content):
                call_line = other_content[:m.start()].count("\n") + 1
                if call_line != lineno:  # Skip the definition itself
                    callers.append(f"{other_file}:{call_line}")
        else:
            pattern = re.compile(r'\b' + re.escape(bare) + r'\s*\(')
            for m in pattern.finditer(other_content):
                call_line = other_content[:m.start()].count("\n") + 1
                callers.append(f"{other_file}:{call_line}")

    # Limit callers to avoid massive output
    caller_str = ", ".join(callers[:10])
    if len(callers) > 10:
        caller_str += f" ... (+{len(callers) - 10} more)"

    output.append(f"### WIRE-{wire_id:04d}: {name} ({sym_type})")
    output.append(f"- **File**: {file_path}:{lineno}-{end_lineno}")
    output.append(f"- **Called by**: {caller_str or 'None found'}")
    output.append(f"- **References**: {len(callers)} call sites")
    output.append("")

header = f"""# 04 — FULL WIREMAP

## Summary

**Total wire entries**: {wire_id}
**Scope**: Every function, class, and method in every Python source file
**Method**: AST extraction + regex cross-reference search across all source files

---

"""

audit_dir = os.path.dirname(os.path.dirname(__file__))
outpath = os.path.join(audit_dir, "04_FULL_WIREMAP.md")
with open(outpath, "w", encoding="utf-8") as f:
    f.write(header + "\n".join(output))

print(f"Done: {wire_id} wire entries -> {outpath}")
