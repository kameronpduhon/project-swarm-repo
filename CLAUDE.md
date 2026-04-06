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
├── playbook.py       # Loads playbook from sample_playbook.json (swap to API later)
├── prompt_builder.py # Converts playbook JSON + call_context → Gemini system instructions
└── call_results.py   # Logs call results locally (swap to POST later)
```

**Note:** `end_call` is defined as a `@function_tool()` method on the `VoiceAgent` class in `agent.py` — not in a separate `tools.py`. LiveKit auto-registers tools defined on the Agent subclass.

## Key Files

### `agent.py`
Entry point. `AgentServer` with `@server.rtc_session` handler. On session start: loads playbook, builds prompt, creates `AgentSession` with Gemini RealtimeModel (voice="Puck"), starts session with BVCTelephony noise cancellation for SIP participants. The `end_call` function tool is defined here as a method on `VoiceAgent` — it parses the structured results and passes them to `call_results.py`.

### `playbook.py`
Loads `sample_playbook.json` from the repo root. Returns `(content, call_context)` tuple. **To swap to real API later:** replace the file load with a GET request to `GET /api/v1/organizations/{org}/playbooks/{playbook}` — the return shape is identical.

### `prompt_builder.py`
Converts playbook JSON + call_context into a Gemini-optimized system instruction string. Sections: PERSONA, CONVERSATIONAL RULES (greeting → caller ID → intent loop → closing → end_call), SERVICES, BOOKING INFO, EXPECTATIONS, FAQs, TOOL INVOCATION, GUARDRAILS. Handles business_hours vs after_hours greeting selection.

### `call_results.py`
Logs structured call results to console. **To swap to real API later:** replace the logger call with a POST to `POST /api/v1/organizations/{org}/calls` — the payload shape matches `DATA-CONTRACTS.md §2`.

### `sample_playbook.json`
Fictional "Bayou Comfort Heating and Air" playbook. Matches the exact schema from `DATA-CONTRACTS.md §1`. Used as a stand-in until project-d serves the real API.

## Current Phase: Testing & Tuning

The foundation is built. First test calls have been completed. Prompt tuning is in progress.

### Prompt tuning already done (2026-04-06):
These issues were found during test calls and fixed in `prompt_builder.py`:
1. **One question at a time** — Agent was stacking 3-4 questions per response. Added CONVERSATION STYLE section and guardrail to enforce one question per turn.
2. **Greet first, then listen** — Agent was immediately asking for name after greeting. Now waits for caller to state their need before collecting info.
3. **Field name keys match playbook** — Agent was returning `service_address` instead of `address`. Field list now shows exact machine keys from playbook; tool invocation instructions enforce using them.

### Known issues to fix:
1. **Session doesn't auto-disconnect after end_call** — After Gemini calls end_call and results are logged, the LiveKit session stays open. Caller sits in silence until they hang up. Attempted `session.close()` and `room.disconnect()` via asyncio.create_task — neither worked with Gemini's RealtimeModel. Needs deeper investigation into how to properly tear down a Gemini realtime session in LiveKit. This WILL be a problem for real SIP calls where the caller expects the line to drop.
2. **Caller name transcription accuracy** — Gemini occasionally mishears names (e.g. "Thibodaux" → "Tibbetts"). Not blocking for MVP. Could add spelling confirmation to prompt later.

### What to work on next:
1. **Fix auto-disconnect** — research LiveKit + Gemini session teardown. Check LiveKit Discord, GitHub issues, or examples for how other agents end calls after a tool fires
2. **Run remaining test scripts** — see `test-call-scripts.md` in parent project-swarm folder. Still need to test: FAQ only, emergency, after-hours, out-of-area, guardrail pressure, multi-intent
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
1. `call_context` added to playbook API response
2. `POST /api/v1/organizations/{org}/calls` endpoint created
Then update `playbook.py` (file load → GET request) and `call_results.py` (logger → POST request). The rest of the agent code stays the same.

## Gemini 3.1 Compatibility Notes

These LiveKit features do NOT work with Gemini 3.1 Flash Live Preview:
- `update_instructions()` mid-session — not needed, we load at start
- `update_chat_ctx()` mid-session — not needed
- `generate_reply()` mid-session — not needed
- No affective dialog, no proactive audio — not needed
- Tool calling is synchronous only — that's fine, we prefer it

## Data Contracts

See `DATA-CONTRACTS.md` in the parent `project-swarm/` folder for the full contracts between this agent and project-d:
- §1: Playbook JSON schema (what `sample_playbook.json` follows)
- §2: Call results schema (what `end_call` produces)
- §3: Call context schema (what `call_context` contains)

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
