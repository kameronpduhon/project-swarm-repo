# Project Swarm - Voice Agent

AI voice agent for home service companies. Answers inbound calls via Twilio SIP + LiveKit, follows the client's playbook, collects caller info, and posts structured results back to the platform.

## Stack

- **Python 3.12**, managed with `uv`
- **LiveKit Agents SDK** (v1.5+) — real-time voice infrastructure
- **Gemini 3.1 Flash Live Preview** — native audio model (no separate TTS/STT)
- **Twilio SIP** — telephony ingress
- **Linter/formatter:** `ruff`
- **Tests:** `pytest` + `pytest-asyncio`

## Architecture

```
Inbound call → Twilio SIP → LiveKit room → entrypoint(ctx)
  → load_playbook()        # playbook.py — loads resolved JSON
  → build_prompt(resolved) # prompt_builder.py — generates system instructions
  → AgentSession w/ Gemini Realtime
  → Conversation runs (native audio I/O)
  → end_call() tool fires  # agent.py — validates, logs, shuts down
  → log_call_results()     # call_results.py — PII-redacted logging
  → Room deleted (disconnects SIP caller)
```

### Source Files (4 total, all in `src/`)

| File | Purpose |
|------|---------|
| `agent.py` | Entry point, `VoiceAgent` class, `end_call()` function tool, `normalize_end_call_payload()`, shutdown sequence |
| `playbook.py` | `load_playbook()` — loads and validates resolved playbook JSON. Uses module-relative paths (not cwd) |
| `prompt_builder.py` | `build_prompt()` — transforms playbook dict into structured Gemini system instructions (~5KB). 7 helper functions for each section |
| `call_results.py` | `log_call_results()` — info-level logs exclude PII, debug-level includes full payload |

### Key Types

```python
VALID_INTENTS = "schedule_service" | "request_quote" | "general_inquiry" | "faq" | "message" | "emergency"
VALID_URGENCY = "normal" | "urgent" | "emergency"
```

`normalize_end_call_payload()` defaults invalid values to `"general_inquiry"` / `"normal"` / `{}`.

## Commands

```bash
# Run locally (dev mode)
uv run src/agent.py dev

# Run (production)
uv run src/agent.py start

# Install/sync dependencies
uv sync

# Run tests
uv run pytest

# Lint/format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Key Design Decisions

1. **Stateless agent** — fetches playbook config at call start, posts results at call end. No persistent state between calls.
2. **Playbook-driven behavior** — agent does nothing that isn't in the playbook JSON. One codebase, many clients.
3. **Resolved playbook** — project-d pre-joins 20+ tables into a flat JSON structure. The agent never assembles this itself.
4. **Native audio** — Gemini Realtime handles speech directly (no TTS/STT pipeline). Don't add separate TTS/STT.
5. **One question per turn** — strict prompt rule to prevent LLM chattiness.
6. **PII redaction** — info-level logs never contain caller name, phone, collected fields, or summary.
7. **Graceful shutdown** — follows the SDK `EndCallTool` pattern: `end_call` fires first (logs data, returns goodbye instruction), Gemini speaks goodbye as tool reply, `_delayed_session_shutdown` waits for that speech to finish, then closes session and deletes room.
8. **Tool-first call ending** — agent calls `end_call` BEFORE saying goodbye (not after). The tool return value instructs Gemini to generate the goodbye as the tool reply speech. This is required because Gemini Realtime won't invoke a function tool after speaking.

## What NOT to Change

- **Don't swap `playbook.py` to fetch from the real API** until the project-d endpoint is confirmed ready. Currently uses `sample_playbook.json`.
- **Don't swap `call_results.py` to POST results** to project-d until that endpoint is confirmed ready. Currently logs to stdout.
- **Don't add TTS/STT plugins** — Gemini Realtime handles audio natively.
- **Don't change the Gemini model** without testing — `gemini-3.1-flash-live-preview` is specifically chosen for realtime audio support.
- **Don't change the end_call flow** — the tool-first pattern (call tool, then Gemini speaks goodbye as tool reply) is required for Gemini Realtime. Telling the agent to say goodbye THEN call the tool will not work — Gemini won't invoke tools after speaking.
- **Don't put behavioral instructions in tool docstrings** — Gemini Realtime may speak docstring text aloud. Keep tool descriptions minimal/mechanical; put behavioral rules in the system prompt only.
- **Don't change noise cancellation settings** — BVCTelephony for SIP calls, BVC for others. These are tuned.

## Playbook Structure

The resolved playbook JSON contains these top-level keys (all required except where noted):

- `playbook` — company info, greeting, after-hours message, AI settings, caller intake config
- `current_time_window` — active window name (e.g., "Business Hours", "After Hours")
- `service_configs` — list of trade configs with sub-services, zones (zips/cities), dispatch fees, probing questions
- `faqs` — question/answer pairs
- `non_services` — services the company does NOT offer (with rejection scripts)
- `non_service_areas` — geographic areas outside service zone (with response scripts)
- `memberships` — membership tier descriptions
- `global_questions` — questions asked on all service calls

See `sample_playbook.json` for the full reference format, and `docs/DATA-CONTRACTS.md` in the parent project for the schema spec.

## Tests

Tests live in `tests/`. Run with `uv run pytest`.

- `test_playbook.py` — playbook loading from default/explicit paths, missing file errors
- `test_call_results.py` — PII redaction at info vs debug log levels
- `test_end_call_validation.py` — payload normalization for all intent/urgency values, edge cases

## Parent Project

This repo is part of the Project Swarm workspace. The parent directory contains:
- `SWARM-MANAGER.md` — project roadmap, session history, current priorities
- `project-d/` — Laravel platform that serves playbooks and receives call results
- `docs/` — data contracts, architecture docs, test call scripts
