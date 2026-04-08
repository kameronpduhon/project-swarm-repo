"""Tests for playbook loading — path resolution and error handling."""

import os

import pytest

from playbook import _REPO_ROOT, load_playbook


def test_load_from_default_path():
    """Default load works regardless of cwd."""
    original_cwd = os.getcwd()
    try:
        os.chdir("/tmp")  # Simulate running from a different directory
        content, call_context = load_playbook()
        assert "company_info" in content
        assert "organization_name" in call_context
    finally:
        os.chdir(original_cwd)


def test_load_from_explicit_path():
    """Explicit path argument takes priority."""
    sample = _REPO_ROOT / "sample_playbook.json"
    content, call_context = load_playbook(path=str(sample))
    assert "company_info" in content
    assert "organization_name" in call_context


def test_missing_file_raises_error():
    """Missing playbook file raises FileNotFoundError with helpful message."""
    with pytest.raises(FileNotFoundError, match="Playbook not found"):
        load_playbook(path="/nonexistent/playbook.json")
