"""Tests for call results logging — PII redaction."""

import logging

from call_results import log_call_results


def test_info_log_excludes_pii(caplog):
    """Info-level log should NOT contain caller name, phone, or collected fields."""
    results = {
        "caller_name": "John Smith",
        "caller_phone": "337-555-1234",
        "intent": "schedule_service",
        "summary": "Caller needs AC repair.",
        "urgency": "normal",
        "collected_fields": {"address": "123 Main St"},
    }

    with caplog.at_level(logging.INFO, logger="voice-agent"):
        log_call_results(results)

    info_output = caplog.text
    assert "John Smith" not in info_output
    assert "337-555-1234" not in info_output
    assert "123 Main St" not in info_output
    assert "AC repair" not in info_output
    # Only safe metadata should be present
    assert "schedule_service" in info_output
    assert "normal" in info_output


def test_debug_log_includes_full_payload(caplog):
    """Debug-level log should contain the full payload."""
    results = {
        "caller_name": "John Smith",
        "caller_phone": "337-555-1234",
        "intent": "schedule_service",
        "summary": "Caller needs AC repair.",
        "urgency": "normal",
        "collected_fields": {"address": "123 Main St"},
    }

    with caplog.at_level(logging.DEBUG, logger="voice-agent"):
        log_call_results(results)

    debug_output = caplog.text
    assert "John Smith" in debug_output
