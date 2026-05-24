"""Shared helpers used by both the CrewAI loop (loop.py) and BAML loop (baml_loop.py).

Extracted so the two engine paths share vault idempotency checks, path sanitization,
slug generation, and error types without coupling through imports.
"""

from __future__ import annotations

import re
from pathlib import Path


class HarnessError(Exception):
    pass


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def sanitize_slug(slug: str) -> str:
    """Allow only alphanumerics and hyphens to prevent path traversal via slug."""
    sanitized = re.sub(r"[^a-z0-9\-]", "", slug.lower())
    if not sanitized:
        raise HarnessError(f"Invalid slug: {slug!r}")
    return sanitized


def safe_vault_path(vault_path: str, *parts: str) -> Path:
    """Resolve a path inside the vault and raise if it escapes the root."""
    root = Path(vault_path).resolve()
    full = (root / Path(*parts)).resolve()
    if not full.is_relative_to(root):
        raise HarnessError(f"Path traversal blocked: {Path(*parts)}")
    return full


def decision_valid(vault_path: str, slug: str) -> bool:
    p = safe_vault_path(vault_path, "decisions", f"{slug}.md")
    return p.exists() and "## Chosen:" in p.read_text()


def research_done(vault_path: str, slug: str) -> bool:
    p = safe_vault_path(vault_path, "research", f"{slug}.md")
    return p.exists() and "## Findings" in p.read_text()


def questions_has_entry(vault_path: str, slug: str) -> bool:
    p = safe_vault_path(vault_path, "pending", "questions.md")
    return p.exists() and f"## {slug}" in p.read_text()


def verifier_passed(vault_path: str, slug: str) -> bool:
    p = safe_vault_path(vault_path, "pending", f"verify-{slug}.md")
    return p.exists() and bool(re.search(r"\bPASSED\b", p.read_text()))


def verifier_failed(vault_path: str, slug: str) -> bool:
    p = safe_vault_path(vault_path, "pending", f"verify-{slug}.md")
    return p.exists() and "status: FAILED" in p.read_text()


def clear_verifier(vault_path: str, slug: str):
    p = safe_vault_path(vault_path, "pending", f"verify-{slug}.md")
    if p.exists():
        p.unlink()


def feature_checked_off(plan_path: Path, slug: str) -> bool:
    if not plan_path.exists():
        return False
    text = plan_path.read_text()
    return bool(re.search(rf"- \[x\] [^\n]*{re.escape(slug)}", text))


def open_questions(vault_path: str, slug: str) -> list:
    p = safe_vault_path(vault_path, "pending", "questions.md")
    if not p.exists():
        return []
    lines = p.read_text().splitlines()
    in_section = False
    qs = []
    for line in lines:
        if line.startswith(f"## {slug}"):
            in_section = True
            continue
        if in_section:
            if line.startswith("## "):
                break
            if line.startswith("- [ ]"):
                qs.append(line[6:].strip())
    return qs


def read_specs(specs_dir: str) -> str:
    """Read all spec files and return their contents concatenated with headers."""
    safe_dir = Path(specs_dir).resolve()
    parts = []
    for f in sorted(safe_dir.rglob("*")):
        if f.is_file() and f.suffix in (".md", ".txt", ".rst", ".yaml", ".yml", ".json"):
            rel = f.relative_to(safe_dir)
            try:
                parts.append(f"### {rel}\n{f.read_text()}")
            except (OSError, UnicodeDecodeError):
                pass
    return "\n\n".join(parts) if parts else "(no spec files found)"


def project_has_source(project_root: str, specs_dir: str) -> bool:
    """Return True if there are non-spec source files in the project."""
    root = Path(project_root).resolve()
    specs = Path(specs_dir).resolve()
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        parts = f.parts
        if any(p.startswith(".") for p in parts[len(root.parts):]):
            continue
        try:
            f.relative_to(specs)
            continue
        except ValueError:
            pass
        if f.suffix in (".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs",
                        ".java", ".rb", ".cs", ".cpp", ".c", ".php", ".kt"):
            return True
    return False


def vault_file_content(vault_path: str, relative_path: str, default: str = "") -> str:
    """Return file contents or default if missing."""
    p = Path(vault_path) / relative_path
    return p.read_text() if p.exists() else default
