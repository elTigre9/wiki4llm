import sys
import time
import threading
from contextlib import contextmanager

FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# Heartbeat interval for --trace mode (seconds)
HEARTBEAT_INTERVAL = 60


def _usage_str(stats: dict) -> str:
    usage = stats.get("usage")
    if usage is None:
        return ""
    total = getattr(usage, "total_tokens", None)
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    ctx_pct = stats.get("ctx_pct")

    parts = []
    if total is not None:
        parts.append(f"{total:,} tokens (cumulative)")
        if prompt is not None and completion is not None:
            parts.append(f"↑{prompt:,} ↓{completion:,}")
    if ctx_pct is not None:
        parts.append(f"peak ctx ~{ctx_pct}")
    return f"  [{', '.join(parts)}]" if parts else ""


def _fmt_elapsed(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def print_over_spinner(pause_event: threading.Event, msg: str) -> None:
    """Pause the spinner, print a full line, then let the spinner resume."""
    pause_event.set()
    time.sleep(0.1)  # let the spin thread finish its current write
    sys.stdout.write(f"\r{' ' * 60}\r{msg}\n")
    sys.stdout.flush()
    pause_event.clear()


@contextmanager
def agent_spinner(agent_name: str, verbose: bool = False, model: str = "",
                  trace: bool = False, vault_path: str = "", slug: str = ""):
    model_tag = f" ({model})" if model else ""
    label = f"[{agent_name}]{model_tag}"
    start = time.time()
    stats: dict = {"pause_event": threading.Event()}

    stop_event = threading.Event()
    pause_event: threading.Event = stats["pause_event"]

    def spin():
        i = 0
        last_heartbeat = time.time()
        while not stop_event.is_set():
            if pause_event.is_set():
                time.sleep(0.05)
                continue
            now = time.time()
            elapsed = _fmt_elapsed(now - start)
            if not verbose:
                frame = FRAMES[i % len(FRAMES)]
                sys.stdout.write(f"\r  {frame} {label} thinking... ({elapsed})")
                sys.stdout.flush()
            if trace and (now - last_heartbeat) >= HEARTBEAT_INTERVAL:
                last_heartbeat = now
                pause_event.set()
                time.sleep(0.1)
                sys.stdout.write(f"\r{' ' * 72}\r  … [{agent_name}] still running ({elapsed})\n")
                sys.stdout.flush()
                pause_event.clear()
            time.sleep(0.08)
            i += 1

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()

    if verbose:
        print(f"  {label} starting...")
        sys.stdout.flush()

    try:
        yield stats
        stop_event.set()
        thread.join()
        elapsed = time.time() - start
        sys.stdout.write(f"\r  ✓ {label} done ({_fmt_elapsed(elapsed)}){_usage_str(stats)}\n")
        sys.stdout.flush()
    except Exception:
        stop_event.set()
        thread.join()
        elapsed = time.time() - start
        sys.stdout.write(f"\r  ✗ {label} failed ({_fmt_elapsed(elapsed)})\n")
        sys.stdout.flush()
        raise
