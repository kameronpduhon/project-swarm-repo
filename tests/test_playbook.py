"""Tests for playbook loading — path resolution and error handling."""

import os

import pytest

from playbook import _REPO_ROOT, load_playbook


def test_load_from_default_path():
    """Default load works regardless of cwd."""
    original_cwd = os.getcwd()
    try:
        os.chdir("/tmp")  # Simulate running from a different directory
        resolved = load_playbook()
        assert "playbook" in resolved
        assert "current_time_window" in resolved
        assert "service_configs" in resolved
        assert "faqs" in resolved
    finally:
        os.chdir(original_cwd)


def test_load_from_explicit_path():
    """Explicit path argument takes priority."""
    sample = _REPO_ROOT / "sample_playbook.json"
    resolved = load_playbook(path=str(sample))
    assert "playbook" in resolved
    assert "name" in resolved["playbook"]
    assert isinstance(resolved["service_configs"], list)


def test_missing_file_raises_error():
    """Missing playbook file raises FileNotFoundError with helpful message."""
    with pytest.raises(FileNotFoundError, match="Playbook not found"):
        load_playbook(path="/nonexistent/playbook.json")
