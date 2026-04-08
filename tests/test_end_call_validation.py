"""Tests for end_call payload normalization — exercises the real production helper."""

from agent import normalize_end_call_payload


def test_valid_inputs_pass_through():
    """Valid intent, urgency, and dict fields are returned unchanged."""
    intent, urgency, fields = normalize_end_call_payload(
        "schedule_service", "urgent", {"address": "123 Main St"}
    )
    assert intent == "schedule_service"
    assert urgency == "urgent"
    assert fields == {"address": "123 Main St"}


def test_invalid_intent_defaults_to_general_inquiry():
    """Invalid intent string should default to 'general_inquiry'."""
    intent, _, _ = normalize_end_call_payload("bogus_intent", "normal", {})
    assert intent == "general_inquiry"


def test_invalid_urgency_defaults_to_normal():
    """Invalid urgency string should default to 'normal'."""
    _, urgency, _ = normalize_end_call_payload("faq", "super_urgent", {})
    assert urgency == "normal"


def test_non_dict_collected_fields_becomes_empty():
    """Non-dict collected_fields should become empty dict."""
    _, _, fields = normalize_end_call_payload("faq", "normal", "not a dict")
    assert fields == {}


def test_none_collected_fields_becomes_empty():
    """None collected_fields should become empty dict."""
    _, _, fields = normalize_end_call_payload("faq", "normal", None)
    assert fields == {}


def test_all_valid_intents_accepted():
    """Every valid intent value should pass through unchanged."""
    for value in ("schedule_service", "request_quote", "general_inquiry",
                  "faq", "message", "emergency"):
        intent, _, _ = normalize_end_call_payload(value, "normal", {})
        assert intent == value


def test_all_valid_urgency_accepted():
    """Every valid urgency value should pass through unchanged."""
    for value in ("normal", "urgent", "emergency"):
        _, urgency, _ = normalize_end_call_payload("faq", value, {})
        assert urgency == value
