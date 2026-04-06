import json
import logging

logger = logging.getLogger("voice-agent")


def log_call_results(results: dict) -> None:
    """Log structured call results. Later: POST to API."""
    logger.info("=== CALL RESULTS ===")
    logger.info(json.dumps(results, indent=2))
