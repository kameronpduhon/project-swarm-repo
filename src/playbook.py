import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def load_playbook(path: str | None = None) -> dict:
    """Load resolved playbook JSON from file (dev) or API (future).

    Returns the full resolved playbook dict with keys:
        playbook, current_time_window, service_configs, non_services,
        non_service_areas, faqs, memberships, global_questions

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

    # Validate required top-level keys
    required = {"playbook", "current_time_window", "service_configs", "faqs"}
    missing = required - data.keys()
    if missing:
        raise ValueError(
            f"Playbook JSON missing required keys: {missing}. "
            "Expected resolved playbook format from project-d /resolve endpoint."
        )

    return data
