# swarm-agent — Voice Agent for Project Swarm

> Status: **Built — testing and tuning phase**

## What This Is

A voice AI agent that handles inbound phone calls for home service companies (HVAC, plumbing, etc.). One codebase serves all clients — behavior is driven entirely by a playbook JSON config. The agent answers calls, follows the playbook (greeting, field collection, FAQs, closing), then posts structured results back when the call ends.

## Tech Stack

- **Python** with **LiveKit Agents SDK** (`livekit-agents>=1.4`)
- **Gemini 3.1 Flash Live Preview** (`gemini-3.1-flash-live-preview`) — native audio model, no separate STT/TTS
- **Twilio SIP trunk** → LiveKit for phone connectivity
- **uv** for package management, **ruff** for formatting

## Architecture: Single Agent, Stateless

One `VoiceAgent` class (subclass of `Agent`) handles the full conversation. No multi-agent handoffs, no mid-call tool calls. The agent:
1. Loads a playbook at session start
2. Builds a system prompt from it
3. Has a conversation with the caller (Gemini handles audio in/out natively)
4. Calls `end_call` tool when done → logs structured results
5. Session closes

## File Structure (Built)

```
src/
├── agent.py          # Entry point — AgentServer, VoiceAgent class, end_call tool, session handler
├── playbook.py       # Loads resolved playbook from sample_playbook.json (swap to API later)
├── prompt_builder.py # Converts resolved playbook dict → Gemini system instructions
└── call_results.py   # Logs call results locally (swap to POST later)
```

**Note:** `end_call` is defined as a `@function_tool()` method on the `VoiceAgent` class in `agent.py` — not in a separate `tools.py`. LiveKit auto-registers tools defined on the Agent subclass.

## Key Files

### `agent.py`
Entry point. `AgentServer` with `@server.rtc_session` handler. On session start: loads playbook, builds prompt, creates `AgentSession` with Gemini RealtimeModel (voice="Puck"), starts session with BVCTelephony noise cancellation for SIP participants. The `end_call` function tool is defined here as a method on `VoiceAgent` — it validates and logs structured results via `call_results.py`. Valid intent values: `schedule_service`, `request_quote`, `general_inquiry`, `faq`, `message`, `emergency`. Valid urgency values: `normal`, `urgent`, `emergency` (see `DATA-CONTRACTS.md §2`).

### `playbook.py`
Loads `sample_playbook.json` from the repo root. Returns the full resolved playbook dict with keys: `playbook`, `current_time_window`, `service_configs`, `non_services`, `non_service_areas`, `faqs`, `memberships`, `global_questions`. Validates required keys on load. **To swap to real API later:** replace the file load with a GET request to project-d's resolve endpoint — the return shape is identical.

### `prompt_builder.py`
Converts the resolved playbook dict into a Gemini-optimized system instruction string. Sections: PERSONA, CONVERSATION STYLE, CONVERSATIONAL RULES (greeting → service/area check → intake → probing questions → loop → closing → end_call), SERVICES OFFERED, SERVICES NOT OFFERED, SERVICE ZONES, NON-SERVICE AREAS, DISPATCH FEES, MEMBERSHIPS, PROBING QUESTIONS, FAQs, GUARDRAILS, CRITICAL — ENDING THE CALL. Uses helper functions to build each section dynamically from the resolved playbook data. Handles business hours vs after-hours greeting selection based on `current_time_window.name`.

### `call_results.py`
Logs structured call results with PII redaction. Info-level logs show only intent and urgency (safe metadata). Full payload (including caller name, phone, summary, collected fields) is logged at debug level only. **To swap to real API later:** replace the logger call with a POST to `POST /api/v1/organizations/{org}/calls` — the payload shape matches `DATA-CONTRACTS.md §2`.

### `sample_playbook.json`
Fictional "ACE Home Services" multi-trade playbook (HVAC, Electrical, Plumbing, Drains). Uses the resolved playbook format — the output of project-d's `ResolvePlaybookAction`, which pre-resolves the active time window and filters service configs. Used as a stand-in until project-d serves the real resolve endpoint.

## Current Phase: Testing & Tuning

The foundation is built. First test calls have been completed. Prompt tuning is in progress.

### Prompt tuning already done (2026-04-06):
These issues were found during test calls and fixed in `prompt_builder.py`:
1. **One question at a time** — Agent was stacking 3-4 questions per response. Added CONVERSATION STYLE section and guardrail to enforce one question per turn.
2. **Greet first, then listen** — Agent was immediately asking for name after greeting. Now waits for caller to state their need before collecting info.
3. **Field name keys match playbook** — Agent was returning wrong field keys. Intake fields are now dynamically built from `ai_settings.caller_intake` in the playbook; tool invocation instructions enforce using exact keys.

### Known issues to fix:
1. **Caller name transcription accuracy** — Gemini occasionally mishears names (e.g. "Thibodaux" → "Tibbetts"). Not blocking for MVP. Could add spelling confirmation to prompt later.

### What to work on next:
1. **Run remaining test scripts** — see `test-call-scripts.md` in parent project-swarm folder. Still need to test: FAQ only, emergency, after-hours, out-of-area, guardrail pressure, multi-intent
3. **Continue prompt tuning** based on test results
4. **Error handling** — playbook fetch failures, caller hang-ups before end_call, Gemini API errors, end_call timeout fallback
5. **Twilio SIP integration** — test with real phone calls through Twilio → LiveKit

### What NOT to change yet:
- Don't swap `playbook.py` to real API calls — project-d endpoint isn't ready yet
- Don't swap `call_results.py` to POST — project-d calls endpoint isn't built yet
- Don't add multi-agent handoffs — single agent is the MVP
- Don't add mid-call tools — only end_call at conversation end

### When to swap to real API:
Once project-d has these built (waiting on Kyle's review):
1. Resolve endpoint serving the resolved playbook format (playbook + service_configs + faqs + etc.)
2. `POST /api/v1/organizations/{org}/calls` endpoint created
Then update `playbook.py` (file load → GET to resolve endpoint) and `call_results.py` (logger → POST request). The rest of the agent code stays the same — `prompt_builder.py` already consumes the resolved format.

## Gemini 3.1 Compatibility Notes

These LiveKit features do NOT work with Gemini 3.1 Flash Live Preview:
- `update_instructions()` mid-session — not needed, we load at start
- `update_chat_ctx()` mid-session — not needed
- `generate_reply()` mid-session — not needed
- No affective dialog, no proactive audio — not needed
- Tool calling is synchronous only — that's fine, we prefer it

## Data Contracts

See `DATA-CONTRACTS.md` in the parent `project-swarm/` folder for the full contracts between this agent and project-d:
- §1: Resolved playbook schema (what `sample_playbook.json` follows — the output of `ResolvePlaybookAction`)
- §2: Call results schema (what `end_call` produces)

## Environment Variables

```
LIVEKIT_URL=           # LiveKit Cloud project URL
LIVEKIT_API_KEY=       # LiveKit API key
LIVEKIT_API_SECRET=    # LiveKit API secret
GOOGLE_API_KEY=        # Gemini API key
```

## Running Locally

```bash
uv run src/agent.py dev
```

Then join the LiveKit room from the web playground to simulate a caller.
