from crewai import Agent, LLM
from crewai.tools import BaseTool
from pydantic import BaseModel
import subprocess
import re
from pathlib import Path
from config import HarnessConfig, SecurityConfig


def _strip_html(text: str) -> str:
    """Remove HTML tags and neutralize HTML entities to prevent stored XSS."""
    import html
    text = html.unescape(text)
    return re.sub(r"<[^>]+>", "", text)

def _ctx_window(model: str) -> int | None:
    """Look up context window size via LiteLLM. Returns None if unknown."""
    try:
        from litellm import get_model_info
        info = get_model_info(model)
        return info.get("max_input_tokens") or info.get("max_tokens")
    except Exception:
        return None


def context_percent(model: str, usage) -> str | None:
    """Return context usage as '42.3%' or None if unknown."""
    if usage is None:
        return None
    total_tokens = getattr(usage, "total_tokens", None)
    if not total_tokens:
        return None
    ctx_size = _ctx_window(model)
    if ctx_size is None:
        return None
    return f"{100 * total_tokens / ctx_size:.1f}%"


class _WriteInput(BaseModel):
    path: str
    content: str
    append: bool = False


class _ReadInput(BaseModel):
    path: str


class _SearchInput(BaseModel):
    query: str


class _ShellInput(BaseModel):
    command: str


class VaultWriteTool(BaseTool):
    name: str = "vault_write"
    description: str = (
        "Write (or append) content to a vault file. "
        "'path' is relative to the vault root (e.g. 'pending/plan.md'). "
        "Set append=true to append instead of overwrite."
    )
    args_schema: type[BaseModel] = _WriteInput
    vault_path: str
    security: SecurityConfig = SecurityConfig()

    def _run(self, path: str, content: str, append: bool = False) -> str:
        if err := self.security.check_vault_path(path):
            return f"Error: {err}"
        root = Path(self.vault_path).resolve()
        full = (root / path).resolve()
        if not full.is_relative_to(root):
            return f"Error: path traversal blocked: {path}"
        full.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(full, mode) as f:
            f.write(_strip_html(content))
        return f"Written: {Path(path).name}"


class VaultReadTool(BaseTool):
    name: str = "vault_read"
    description: str = "Read a vault file. 'path' is relative to the vault root."
    args_schema: type[BaseModel] = _ReadInput
    vault_path: str
    security: SecurityConfig = SecurityConfig()

    def _run(self, path: str) -> str:
        if err := self.security.check_vault_path(path):
            return f"Error: {err}"
        root = Path(self.vault_path).resolve()
        full = (root / path).resolve()
        if not full.is_relative_to(root):
            return f"Error: path traversal blocked: {path}"
        return full.read_text() if full.exists() else f"(file not found: {path})"


class ShellTool(BaseTool):
    name: str = "run_shell_command"
    description: str = "Run a shell command and return its output. Use for git operations and writing project files."
    args_schema: type[BaseModel] = _ShellInput
    security: SecurityConfig = SecurityConfig()

    def _run(self, command: str) -> str:
        import shlex
        if err := self.security.check_command(command):
            return f"Error: {err}"
        try:
            result = subprocess.run(
                shlex.split(command), shell=False, capture_output=True, text=True,
                stdin=subprocess.DEVNULL, timeout=120,
            )
            return result.stdout + result.stderr
        except (subprocess.TimeoutExpired, ValueError) as e:
            return f"Error: {e}"


class TavilySearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the web for a query and return a summary of the top results. "
        "Use for researching trends, patterns, libraries, or best practices."
    )
    args_schema: type[BaseModel] = _SearchInput
    api_key: str

    def _run(self, query: str) -> str:
        import urllib.request, urllib.parse, json
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
                parts.append(f"- {result.get('title', '')}\n  {result.get('url', '')}\n  {result.get('content', '')[:300]}")
            return "\n\n".join(parts) if parts else "(no results found)"
        except (OSError, ValueError) as e:
            return f"(web search failed: {e})"


_LLM_TIMEOUT = 60  # seconds — HTTP-level timeout per LiteLLM call


def make_agents(config: HarnessConfig) -> dict:
    def llm(name):
        return LLM(model=config.model_for(name), timeout=_LLM_TIMEOUT)

    sec = config.security
    vault_rw = [
        VaultWriteTool(vault_path=config.vault_path, security=sec),
        VaultReadTool(vault_path=config.vault_path, security=sec),
    ]
    shell = ShellTool(security=sec)

    tavily_key = getattr(config.research, "tavily_api_key", "")
    research_tools = [*vault_rw, TavilySearchTool(api_key=tavily_key)] if tavily_key else vault_rw

    agents = {
        "clarifier": Agent(
            role="Spec Clarifier",
            goal="Read spec files, identify ambiguities that would block a CrewAI agent, and write an enriched clarifications document",
            backstory="You surface gaps and contradictions in specs before any code is written, so agents never have to guess.",
            llm=llm("clarifier"),
            tools=[*vault_rw, shell],
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "planner": Agent(
            role="Project Planner",
            goal="Parse spec files and produce a complete, ordered feature checklist with numbered acceptance criteria",
            backstory="You extract structured plans from unstructured specs.",
            llm=llm("planner"),
            tools=[*vault_rw, shell],
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "refiner": Agent(
            role="Solution Refiner",
            goal="Evaluate 3 implementation approaches and choose the best one",
            backstory="You prevent premature implementation by forcing deliberate design.",
            llm=llm("refiner"),
            tools=vault_rw,
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "architect": Agent(
            role="Software Architect",
            goal="Produce a concrete, file-level implementation plan and a TECH.md spec",
            backstory="You translate decisions into actionable engineering plans.",
            llm=llm("architect"),
            tools=vault_rw,
            allow_delegation=False,
            verbose=config.verbose,
        ),
        "builder": Agent(
            role="Software Builder",
            goal="Implement the feature exactly as planned and commit the changes",
            backstory="You write clean, working code that follows the plan precisely.",
            llm=llm("builder"),
            tools=[*vault_rw, shell],
            allow_delegation=False,
            verbose=config.verbose,
            max_iter=10,
        ),
        "verifier": Agent(
            role="Test Verifier",
            goal="Run the test suite, analyze failures against acceptance criteria, and write a structured failure report",
            backstory="You catch regressions early by running tests and distilling failures into actionable notes.",
            llm=llm("verifier"),
            tools=[*vault_rw, shell],
            allow_delegation=False,
            verbose=config.verbose,
            max_iter=8,
        ),
        "mapper": Agent(
            role="Vault Mapper",
            goal="Update the vault and TECH.md to accurately reflect what was just built",
            backstory="You keep the knowledge base current so future agents start informed.",
            llm=llm("mapper"),
            tools=[*vault_rw, shell],
            allow_delegation=False,
            verbose=config.verbose,
            max_iter=12,
        ),
    }

    if config.research.enabled:
        agents["research"] = Agent(
            role="Research Analyst",
            goal="Gather targeted research relevant to the feature and write a concise findings report",
            backstory="You surface trends, patterns, and prior art so the team builds on solid ground.",
            llm=llm("research"),
            tools=research_tools,
            allow_delegation=False,
            verbose=config.verbose,
            max_iter=8,
        )

    return agents
