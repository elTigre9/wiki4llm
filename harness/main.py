import argparse
import json
import multiprocessing
import sys
from pathlib import Path
from loop import run_loop
from config import HarnessConfig


def _load_dotenv(config_path: str) -> None:
    """Load .env from the project root (directory containing the config file)."""
    try:
        from dotenv import load_dotenv
        env_file = Path(config_path).parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)  # shell env takes precedence
    except ImportError:
        pass  # python-dotenv not installed; silently skip


def main():
    multiprocessing.set_start_method("fork", force=True)  # fork avoids re-importing on macOS/Linux
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to merged config JSON")
    args = parser.parse_args()

    with open(args.config) as f:
        raw = json.load(f)

    _load_dotenv(args.config)
    config = HarnessConfig.from_dict(raw)
    config.inject_api_keys()

    print(f"\nwiki4llm Run Mode")
    print(f"  Vault:   {config.vault_path}")
    print(f"  Specs:   {config.specs_dir}")
    print(f"  Model:   {config.default_model}")
    agents = ["planner"]
    if config.research.enabled:
        agents.append("research")
    if not config.no_refine:
        agents.append("refiner")
    agents += ["architect", "builder"]
    if not config.no_verify:
        agents.append("verifier")
    agents.append("mapper")
    print("  Agents:  " + "  ".join(f"{a}={config.model_for(a)}" for a in agents) + "\n")

    sys.exit(run_loop(config))


if __name__ == "__main__":
    main()
