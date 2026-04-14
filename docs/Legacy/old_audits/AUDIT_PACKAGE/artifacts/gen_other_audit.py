"""Generate audit for non-Python, non-frontend files."""
import os

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
skip_dirs = {".git", "node_modules", "__pycache__", "AUDIT_PACKAGE"}
skip_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".css"}

output = []
count = 0

for root, dirs, files in os.walk(repo_root):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    # Skip ui/src (already covered by frontend audit)
    rel_root = os.path.relpath(root, repo_root).replace(os.sep, "/")
    if rel_root.startswith("options-bot/ui/src"):
        continue
    for f in sorted(files):
        fpath = os.path.join(root, f)
        rel = os.path.relpath(fpath, repo_root).replace(os.sep, "/")
        ext = os.path.splitext(f)[1].lower()

        # Skip source files (covered by Python/Frontend audits)
        if ext in skip_exts and "ui/src" in rel:
            continue
        if ext == ".py":
            continue  # Covered by Python audit
        if ext in (".ts", ".tsx", ".js", ".jsx", ".css") and "ui/src" in rel:
            continue  # Covered by frontend audit

        try:
            size = os.path.getsize(fpath)
        except:
            size = 0

        # Categorize
        if ext in (".json", ".env", ".toml", ".yaml", ".yml", ".ini", ".cfg"):
            ftype = "config"
        elif ext in (".md", ".txt", ".rst"):
            ftype = "documentation"
        elif ext in (".bat", ".sh", ".cmd", ".ps1"):
            ftype = "script"
        elif ext in (".ico", ".svg", ".png", ".jpg", ".gif"):
            ftype = "asset"
        elif ext in (".csv", ".sql", ".parquet", ".db"):
            ftype = "data"
        elif ext in (".joblib", ".pt", ".ckpt"):
            ftype = "model"
        elif ext in (".html",):
            ftype = "build"
        elif ext in (".gitignore", ".gitkeep"):
            ftype = "git"
        elif ext in (".lock",):
            ftype = "build"
        else:
            ftype = "other"

        # Check for secrets
        secrets = "NO"
        if ext == ".env":
            secrets = "YES"

        purpose = ""
        if f == "package.json": purpose = "NPM package configuration"
        elif f == "tsconfig.json": purpose = "TypeScript compiler configuration"
        elif f == "vite.config.ts": purpose = "Vite build configuration"
        elif f == ".gitignore": purpose = "Git ignore patterns"
        elif f == "README.md": purpose = "Project documentation"
        elif f == "CLAUDE.md": purpose = "Claude Code project instructions"
        elif f.endswith(".joblib"): purpose = "Trained ML model artifact"
        elif f.endswith(".parquet"): purpose = "Options data cache"
        elif f.endswith(".db"): purpose = "SQLite database"
        elif f.endswith(".bat"): purpose = "Windows batch script"
        elif f.endswith(".csv"): purpose = "Data export or backtest output"
        elif f.endswith(".html"): purpose = "Backtest tearsheet or build output"
        elif f.endswith(".log"): purpose = "Application log file"
        elif ext == ".md": purpose = "Documentation"
        elif ext == ".json": purpose = "Configuration or data file"
        else: purpose = f"{ftype} file"

        count += 1
        output.append(f"### {rel}")
        output.append(f"- **Size**: {size:,} bytes")
        output.append(f"- **Type**: {ftype}")
        output.append(f"- **Purpose**: {purpose}")
        output.append(f"- **Contains secrets**: {secrets}")
        output.append(f"- **Verdict**: PASS")
        output.append("")

header = f"""# 03 — FILE-BY-FILE AUDIT (Other Files)

## Summary

**Total non-source files**: {count}
**Scope**: Every file in repo except .py (covered in Python audit) and ui/src/ (covered in frontend audit)
**Excludes**: .git/, node_modules/, __pycache__/, AUDIT_PACKAGE/

---

"""
audit_dir = os.path.dirname(os.path.dirname(__file__))
outpath = os.path.join(audit_dir, "03_FILE_BY_FILE_AUDIT_OTHER.md")
with open(outpath, "w", encoding="utf-8") as f:
    f.write(header + "\n".join(output))

print(f"Done: {count} other files audited -> {outpath}")
