"""Tool-call dispatcher for the BAML agent loop.

A BAML function returning a ToolCall union variant gives us a tool name and
arguments dict; ToolDispatcher routes each call to the right plain-Python tool
instance and returns the tool's string output. The BAML tool loop then feeds
that string back as the next conversation turn.
"""

from __future__ import annotations

from typing import Any

from config import HarnessConfig
from tools import Shell, TavilySearch, VaultReader, VaultWriter


class ToolDispatcher:
    """Holds tool instances and dispatches calls by name.

    Tool names match what BAML's agent functions emit:
      - vault_read(path)
      - vault_write(path, content, append=False)
      - run_shell_command(command)
      - web_search(query)
    """

    def __init__(self, config: HarnessConfig):
        self.config = config
        self.vault_writer = VaultWriter(config.vault_path, config.security)
        self.vault_reader = VaultReader(config.vault_path, config.security)
        self.shell = Shell(config.security, timeout=config.agent_timeout)
        tavily_key = getattr(config.research, "tavily_api_key", "")
        self.tavily = TavilySearch(tavily_key)

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        try:
            if name == "vault_read":
                return self.vault_reader.read(args["path"])
            if name == "vault_write":
                return self.vault_writer.write(
                    args["path"],
                    args["content"],
                    bool(args.get("append", False)),
                )
            if name == "run_shell_command":
                return self.shell.run(args["command"])
            if name == "web_search":
                return self.tavily.search(args["query"])
            return f"Error: unknown tool '{name}'"
        except KeyError as e:
            return f"Error: missing required argument {e} for tool '{name}'"
        except (TypeError, ValueError) as e:
            return f"Error: invalid arguments for tool '{name}': {e}"
