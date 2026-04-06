# swarm-agent — Build Instructions for Claude Code

## What We're Building

A voice AI agent that handles inbound phone calls for home service companies (HVAC, plumbing, etc.). One codebase serves all clients — behavior is driven entirely by a playbook JSON config. The agent answers calls, follows the playbook (greeting, field collection, FAQs, closing), then posts structured results back when the call ends.

## Starter Template

**Clone and use as the foundation:** https://github.com/livekit-examples/agent-starter-python

This is LiveKit's official Python starter for voice agents. It has the project structure, Dockerfile, testing framework, and SIP noise cancellation patterns we need. Study its patterns (Agent subclass, AgentSession, AgentServer, @function_tool, BVCTelephony) and build on top of them.

## Tech Stack

- **Python** with **LiveKit Agents SDK**
- **Gemini 3.1 Flash Live Preview** (`gemini-3.1-flash-live-preview`) — native audio model, no separate STT/TTS
- **Twilio SIP trunk** → LiveKit for phone connectivity
- **uv** for package management, **ruff** for formatting (from the starter template)

## Architecture: Single Agent, Stateless

One Agent class handles the full conversation. No multi-agent handoffs, no mid-call tool calls. The agent:
1. Loads a playbook at session start
2. Builds a system prompt from it
3. Has a conversation with the caller (Gemini handles audio in/out natively)
4. Calls `end_call` tool when done → logs structured results
5. Session closes

## File Structure to Build

```
src/
├── agent.py          # Entry point — AgentServer, session handler, Agent class
├── playbook.py       # Loads playbook from sample_playbook.json (swap to API later)
├── prompt_builder.py # Converts playbook JSON → Gemini system instructions
├── call_results.py   # Logs call results locally (swap to POST later)
└── tools.py          # @function_tool definitions (end_call tool)
```

## Build Order

Build in this order — each file is testable independently:

### 1. `playbook.py` — Load the sample playbook

For now, this just loads `sample_playbook.json` from the repo root. Later it will make a GET request to the Laravel API.

```python
# Load sample_playbook.json, return two things:
# - playbook_content (the "content" object)
# - call_context (the "call_context" object)
```

The sample playbook file is already in the repo root. It mimics the exact shape the real API will return. See `sample_playbook.json`.

### 2. `prompt_builder.py` — Convert playbook to system instructions

Takes the playbook content + call_context and produces a single system instruction string optimized for Gemini's Live API. Follow this structure:

```
PERSONA:
You are the virtual receptionist for {call_context.organization_name}.
You are currently handling calls during {call_context.current_window} hours.

CONVERSATIONAL RULES:
1. [One-time] Greet the caller using this exact greeting: "{company_info.greeting}"
   (If after_hours/holiday, use: "{company_info.after_hours_message}" instead)
2. [One-time] Identify the caller — ask for their name and phone number.
3. [Loop] Determine what the caller needs and handle it:
   - If they need service: collect these fields: {field_collection items}
   - If they have a question: answer from this FAQ list: {faqs}
   - If the service/area isn't offered: let them know politely
   - If you can't help: take a message
4. [One-time] Close the call: "{company_info.closing}"
5. [One-time] Call the end_call tool with all collected information.

SERVICES OFFERED:
{services.offered}

SERVICES NOT OFFERED:
{services.not_offered}

SERVICE AREAS:
{services.service_areas}

BOOKING INFO:
Method: {booking.method}
{booking.capacity_notes}
{booking.scheduling_rules}

EXPECTATIONS TO SHARE WITH CALLER:
Arrival window: {expectations.arrival_window}
Confirmation: {expectations.confirmation_method}
Cancellation: {expectations.cancellation_policy}

TOOL INVOCATION:
When the conversation is complete and the caller is ready to hang up, invoke the end_call tool with:
- caller_name, caller_phone
- intent (one of: schedule_service, request_quote, general_inquiry, faq, message, emergency)
- summary (brief summary of the conversation)
- urgency (normal, urgent, or emergency)
- collected_fields (key-value pairs of info collected)

GUARDRAILS:
{guardrails items}
- Never make promises about scheduling or pricing unless specified above.
- If you don't know the answer, take a message and let them know someone will follow up.
- Keep responses concise and conversational — this is a phone call, not an essay.
```

Important: This prompt structure is a starting point. Tune it based on how Gemini actually responds during testing.

### 3. `tools.py` — The end_call function tool

Define one tool: `end_call`. This is what Gemini calls when the conversation is done.

Parameters:
- `caller_name` (str) — nullable
- `caller_phone` (str) — nullable
- `intent` (str) — one of: schedule_service, request_quote, general_inquiry, faq, message, emergency
- `summary` (str) — free-text conversation summary
- `urgency` (str) — one of: normal, urgent, emergency
- `collected_fields` (dict) — key-value pairs matching field_collection names from playbook

When called, this tool should:
1. Pass the data to `call_results.py` for logging/posting
2. End the agent session

### 4. `call_results.py` — Log/post call results

For now: log the structured results to console/file. Later: POST to `POST /api/v1/organizations/{org}/calls`.

The result payload shape:
```json
{
  "caller_name": "John Smith",
  "caller_phone": "337-555-1234",
  "intent": "schedule_service",
  "summary": "Caller needs AC repair...",
  "urgency": "normal",
  "collected_fields": {
    "address": "123 Main St, Lafayette, LA",
    "issue_description": "AC blowing warm air",
    "preferred_timeframe": "this week"
  }
}
```

### 5. `agent.py` — Wire everything together

Entry point. Sets up:
1. `AgentServer` with `@server.rtc_session` handler
2. On session start: load playbook via `playbook.py`
3. Build system instructions via `prompt_builder.py`
4. Create `AgentSession` with Gemini RealtimeModel:
   ```python
   llm = google.realtime.RealtimeModel(
       model="gemini-3.1-flash-live-preview",
       instructions=built_prompt,
       voice="Puck"  # or another Gemini voice
   )
   ```
5. Register the `end_call` tool from `tools.py`
6. Start session and connect to room
7. Use `BVCTelephony()` for SIP participants (noise cancellation)

## Gemini 3.1 Compatibility Notes

These LiveKit features do NOT work with Gemini 3.1 Flash Live Preview:
- `update_instructions()` mid-session — not needed, we load at start
- `update_chat_ctx()` mid-session — not needed
- `generate_reply()` mid-session — not needed
- No affective dialog, no proactive audio — not needed
- Tool calling is synchronous only — that's fine, we prefer it

## Things NOT to Build Yet

- No real API calls to project-d — use sample_playbook.json
- No real POST of call results — just log locally
- No error handling for API failures — the API doesn't exist yet
- No multi-agent handoffs — single agent handles everything
- No mid-call tools — only end_call at conversation end

## Environment Variables Needed

```
LIVEKIT_URL=           # LiveKit Cloud project URL
LIVEKIT_API_KEY=       # LiveKit API key
LIVEKIT_API_SECRET=    # LiveKit API secret
GOOGLE_API_KEY=        # Gemini API key
```

## Testing

Follow the starter template's testing patterns. The agent should be testable by:
1. Running locally and connecting to a LiveKit room
2. Joining the room from LiveKit's web playground to simulate a caller
3. Verifying the agent greets correctly, collects fields, answers FAQs, and calls end_call with the right data
