import json
from pathlib import Path


def load_playbook(path: str = "sample_playbook.json") -> tuple[dict, dict]:
    """Load playbook JSON, returning (content, call_context)."""
    data = json.loads(Path(path).read_text())
    return data["content"], data["call_context"]
