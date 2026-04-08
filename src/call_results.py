import json
import logging

logger = logging.getLogger("voice-agent")

# Fields that contain PII and should not appear in info-level logs
_PII_FIELDS = {"caller_name", "caller_phone", "collected_fields", "summary"}


def log_call_results(results: dict) -> None:
    """Log structured call results. Later: POST to API.

    Info-level logs show intent, urgency, and summary only.
    Full payload (including PII) is logged at debug level.
    """
    safe = {k: v for k, v in results.items() if k not in _PII_FIELDS}
    logger.info("=== CALL RESULTS === %s", json.dumps(safe))
    logger.debug("Full call results: %s", json.dumps(results, indent=2))
