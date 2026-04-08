import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def load_playbook(path: str | None = None) -> tuple[dict, dict]:
    """Load playbook JSON, returning (content, call_context).

    Args:
        path: Explicit path to playbook file. If None, loads sample_playbook.json
              from the repo root (resolved relative to this module, not cwd).
    """
    resolved = _REPO_ROOT / "sample_playbook.json" if path is None else Path(path)

    if not resolved.exists():
        raise FileNotFoundError(
            f"Playbook not found: {resolved}. "
            "Ensure sample_playbook.json exists in repo root."
        )

    data = json.loads(resolved.read_text())
    return data["content"], data["call_context"]
