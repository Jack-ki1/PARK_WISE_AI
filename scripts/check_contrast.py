#!/usr/bin/env python3
"""WCAG 2.1 AA Contrast Ratio Checker for ParkWise design tokens.

Validates that all foreground/surface pairs meet AA thresholds:
- Normal text: >= 4.5:1
- UI components / graphical objects: >= 3.0:1
"""
import re
import sys
from pathlib import Path


def lum(h: str) -> float:
    h = h.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def _f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _f(r) + 0.7152 * _f(g) + 0.0722 * _f(b)


def cr(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


PAIRS_LIGHT = [
    ("--text", "--surface", 4.5),
    ("--text-muted", "--surface", 4.5),
    ("--text-subtle", "--surface", 4.5),
    ("--text-subtle", "--bg", 4.5),
    ("--accent", "--surface", 4.5),
    ("--on-accent", "--accent", 4.5),
    ("--border-strong", "--surface", 3.0),
    ("--success-text", "--surface", 4.5),
    ("--warning-text", "--surface", 4.5),
    ("--danger-text", "--surface", 4.5),
    ("--info-text", "--surface", 4.5),
    ("--series-1", "--surface", 3.0),
    ("--series-2", "--surface", 3.0),
    ("--series-3", "--surface", 3.0),
    ("--series-4", "--surface", 3.0),
    ("--series-5", "--surface", 3.0),
    ("--series-6", "--surface", 3.0),
]

PAIRS_DARK = [
    ("--text", "--surface", 4.5),
    ("--text-muted", "--surface", 4.5),
    ("--text-subtle", "--surface", 4.5),
    ("--accent-text", "--surface", 4.5),
    ("--on-accent", "--accent", 4.5),
    ("--success", "--surface", 4.5),
    ("--warning", "--surface", 4.5),
    ("--danger", "--surface", 4.5),
]


def check_tokens(css_path: Path) -> int:
    if not css_path.exists():
        print(f"Error: {css_path} not found")
        return 1

    content = css_path.read_text(encoding="utf-8")
    parts = content.split(':root[data-theme="dark"]')
    light_block = parts[0]
    dark_block = parts[1] if len(parts) > 1 else ""

    light_tok = dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", light_block))
    dark_tok = dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", dark_block))

    failures = []
    print("Checking LIGHT theme tokens...")
    for a, b, min_cr in PAIRS_LIGHT:
        if a not in light_tok or b not in light_tok:
            continue
        val = cr(light_tok[a], light_tok[b])
        if val < min_cr:
            failures.append(f"LIGHT FAIL: {a} ({light_tok[a]}) on {b} ({light_tok[b]}) = {val:.2f}:1 (min {min_cr}:1)")
        else:
            print(f"  PASS: {a} on {b} = {val:.2f}:1 (min {min_cr}:1)")

    if dark_tok:
        print("\nChecking DARK theme tokens...")
        for a, b, min_cr in PAIRS_DARK:
            if a not in dark_tok or b not in dark_tok:
                continue
            val = cr(dark_tok[a], dark_tok[b])
            if val < min_cr:
                failures.append(f"DARK FAIL: {a} ({dark_tok[a]}) on {b} ({dark_tok[b]}) = {val:.2f}:1 (min {min_cr}:1)")
            else:
                print(f"  PASS: {a} on {b} = {val:.2f}:1 (min {min_cr}:1)")

    if failures:
        print("\nContrast check FAILED:")
        for f in failures:
            print("  " + f)
        return 1

    print("\nAll contrast checks passed WCAG 2.1 AA.")
    return 0


if __name__ == "__main__":
    tokens_path = Path(__file__).resolve().parents[1] / "web" / "styles" / "tokens.css"
    sys.exit(check_tokens(tokens_path))
