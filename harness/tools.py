"""Plain-Python tool implementations used by the BAML agent loop.

Framework-agnostic: no BAML imports. The ToolDispatcher in tool_dispatch.py
routes BAML ToolCall variants to instances of these classes.
"""

from __future__ import annotations

import html
import json
import re
import shlex
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from config import SecurityConfig


def strip_html(text: str) -> str:
    """Remove HTML tags and neutralize HTML entities to prevent stored XSS."""
    return re.sub(r"<[^>]+>", "", html.unescape(text))


class VaultWriter:
    """Write (or append) content to a vault file. Path is vault-relative."""

    def __init__(self, vault_path: str, security: SecurityConfig | None = None):
        self.vault_path = vault_path
        self.security = security or SecurityConfig()

    def write(self, path: str, content: str, append: bool = False) -> str:
        if err := self.security.check_vault_path(path):
            return f"Error: {err}"
        root = Path(self.vault_path).resolve()
        full = (root / path).resolve()
        if not full.is_relative_to(root):
            return f"Error: path traversal blocked: {path}"
        full.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(full, mode) as f:
            f.write(strip_html(content))
        return f"Written: {Path(path).name}"


class VaultReader:
    """Read a vault file. Path is vault-relative."""

    def __init__(self, vault_path: str, security: SecurityConfig | None = None):
        self.vault_path = vault_path
        self.security = security or SecurityConfig()

    def read(self, path: str) -> str:
        if err := self.security.check_vault_path(path):
            return f"Error: {err}"
        root = Path(self.vault_path).resolve()
        full = (root / path).resolve()
        if not full.is_relative_to(root):
            return f"Error: path traversal blocked: {path}"
        return full.read_text() if full.exists() else f"(file not found: {path})"


class Shell:
    """Run a shell command and return combined stdout+stderr."""

    def __init__(self, security: SecurityConfig | None = None, timeout: int = 120):
        self.security = security or SecurityConfig()
        self.timeout = timeout

    def run(self, command: str) -> str:
        if err := self.security.check_command(command):
            return f"Error: {err}"
        try:
            result = subprocess.run(
                shlex.split(command),
                shell=False,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=self.timeout,
            )
            return result.stdout + result.stderr
        except (subprocess.TimeoutExpired, ValueError) as e:
            return f"Error: {e}"


class TavilySearch:
    """Search the web via Tavily. Returns a text summary; never raises."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str) -> str:
        if not self.api_key:
            return "(web search unavailable: no Tavily API key configured)"
        try:
            payload = json.dumps({
                "api_key": self.api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": True,
            }).encode()
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read())
            parts = []
            if d.get("answer"):
                parts.append(f"Summary: {d['answer']}")
            for result in d.get("results", []):
                parts.append(
                    f"- {result.get('title', '')}\n"
                    f"  {result.get('url', '')}\n"
                    f"  {result.get('content', '')[:300]}"
                )
            return "\n\n".join(parts) if parts else "(no results found)"
        except (OSError, ValueError) as e:
            return f"(web search failed: {e})"
