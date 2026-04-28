import re
from pathlib import Path
from datetime import datetime, timezone


def read_vault_slice(vault_path: str, files: list) -> str:
    parts = []
    for f in files:
        full = Path(vault_path) / f
        if full.exists():
            parts.append(f"### {f}\n{full.read_text()}")
    return "\n\n".join(parts)


def write_vault_file(vault_path: str, relative_path: str, content: str, append=False):
    full = Path(vault_path) / relative_path
    full.parent.mkdir(parents=True, exist_ok=True)
    if append:
        with open(full, "a") as fh:
            fh.write(content)
    else:
        full.write_text(content)


def next_unchecked_feature(plan_path: str):
    if not Path(plan_path).exists():
        return None
    for line in Path(plan_path).read_text().splitlines():
        # Strict: - [ ] slug: description
        m = re.match(r"- \[ \] ([a-z0-9-]+): (.+)", line)
        if m:
            return (m.group(1), m.group(2))
        # Lenient: - [ ] anything (LLM didn't follow slug:desc format)
        m = re.match(r"- \[ \] (.+)", line)
        if m:
            description = m.group(1).strip()
            # Derive slug from description
            slug = re.sub(r"[^a-z0-9]+", "-", description.lower())[:40].strip("-")
            return (slug, description)
    return None


def check_off_feature(plan_path: str, slug: str):
    text = Path(plan_path).read_text()
    # Try strict slug: format first
    updated = re.sub(rf"- \[ \] {re.escape(slug)}:", f"- [x] {slug}:", text)
    if updated == text:
        # Fallback: match any unchecked line containing the slug
        updated = re.sub(
            rf"- \[ \] ([^\n]*{re.escape(slug)}[^\n]*)",
            lambda m: f"- [x] {m.group(1)}",
            text,
        )
    Path(plan_path).write_text(updated)


def append_log(vault_path: str, agent: str, slug: str, message: str):
    ts = datetime.now(timezone.utc).isoformat()
    entry = f"\n## {ts} — {agent} — {slug}\n{message}\n"
    write_vault_file(vault_path, "log.md", entry, append=True)
