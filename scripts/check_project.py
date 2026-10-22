"""Lightweight repository checks; intentionally does not generate demo data."""
from pathlib import Path
import ast

root = Path(__file__).resolve().parents[1]
python_files = sorted((root / "backend" / "app").rglob("*.py"))
for file in python_files:
    ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
print(f"Parsed {len(python_files)} Python application files successfully.")
required = [root / "README.md", root / "docker-compose.yml", root / "web" / "app" / "page.tsx", root / "backend" / "app" / "main.py"]
missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
if missing:
    raise SystemExit(f"Missing required project files: {missing}")
print("Core repository files present.")
