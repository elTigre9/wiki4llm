import argparse
import json
import sys
from pathlib import Path
from config import HarnessConfig


def _load_dotenv(config_path: str) -> None:
    """Load .env from the project root (directory containing the config file)."""
    try:
        from dotenv import load_dotenv
        env_file = Path(config_path).parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
    except ImportError:
        pass


def main():
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
    agents = []
    if not config.skip_clarify:
        agents.append("clarifier")
    agents.append("planner")
    if config.research.enabled:
        agents.append("research")
    if not config.no_refine:
        agents.append("refiner")
    agents += ["architect", "builder"]
    if not config.no_verify:
        agents.append("verifier")
    agents.append("mapper")
    print("  Agents:  " + "  ".join(
        f"{a}={models[0]}" + (f" (+{len(models) - 1} fallback)" if len(models) > 1 else "")
        for a in agents if (models := config.fallbacks_for(a))
    ) + "\n")

    from baml_loop import run_loop_baml
    sys.exit(run_loop_baml(config))


if __name__ == "__main__":
    main()
