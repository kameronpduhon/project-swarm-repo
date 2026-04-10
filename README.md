# Project Swarm — Voice Agent

AI-powered phone handling for home service companies. This is the voice agent that answers inbound calls, follows the client's playbook, collects caller information, and delivers structured results back to the platform.

## How It Works

1. Inbound call arrives via **Twilio SIP** into a **LiveKit** room
2. Agent fetches the client's **resolved playbook** (company info, services, zones, FAQs, fees, scripts)
3. **Gemini 3.1 Flash** handles the full conversation using native audio (no separate speech-to-text or text-to-speech)
4. Agent collects caller info, answers FAQs, validates service areas, asks probing questions
5. When done, agent calls `end_call` with structured results and gracefully disconnects

## Stack

- **Python 3.12** (managed with `uv`)
- **LiveKit Agents SDK** — real-time voice infrastructure
- **Gemini 3.1 Flash Live Preview** — native audio model
- **Twilio SIP** — telephony ingress

## Project Structure

```
src/
  agent.py           — Entry point, VoiceAgent class, end_call tool, shutdown
  playbook.py        — Loads and validates resolved playbook JSON
  prompt_builder.py  — Transforms playbook into Gemini system instructions
  call_results.py    — PII-redacted call result logging
tests/
  test_playbook.py
  test_call_results.py
  test_end_call_validation.py
sample_playbook.json — Reference playbook (ACE Home Services)
Dockerfile           — Production container build
```

## Quick Start

```bash
# Install dependencies
uv sync

# Run in dev mode (connects to LiveKit playground)
uv run src/agent.py dev

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
```

Requires a `.env.local` with `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `GOOGLE_API_KEY`.

## Key Design Principles

- **One codebase, many clients** — agent behavior is 100% driven by the playbook JSON
- **Stateless** — fetches config at call start, posts results at call end
- **Native audio** — Gemini handles speech directly, no TTS/STT pipeline
- **One question per turn** — strict prompt rule prevents LLM chattiness
- **PII-aware logging** — info-level logs never contain caller names, phones, or addresses

## Part of Project Swarm

This repo is the voice agent component. The platform (client dashboard, playbook builder, billing, call records) lives in the [project-d](https://github.com/kyle-duhon/project-d) repo.
