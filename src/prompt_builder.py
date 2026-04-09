"""Build Gemini system instructions from resolved playbook JSON.

The resolved playbook is the output of project-d's ResolvePlaybookAction,
which pre-resolves the active time window and filters service configs
for the current time. The agent receives a ready-to-use snapshot.
"""


def build_prompt(resolved: dict) -> str:
    """Convert resolved playbook dict into Gemini system instructions.

    Args:
        resolved: Full resolved playbook from load_playbook() or project-d API.
                  Keys: playbook, current_time_window, service_configs, non_services,
                  non_service_areas, faqs, memberships, global_questions
    """
    pb = resolved["playbook"]
    time_window = resolved.get("current_time_window")
    service_configs = resolved.get("service_configs", [])
    non_services = resolved.get("non_services", [])
    non_service_areas = resolved.get("non_service_areas", [])
    faqs = resolved.get("faqs", [])
    memberships = resolved.get("memberships", [])
    global_questions = resolved.get("global_questions", [])

    company_name = pb["name"]
    intake = pb.get("ai_settings", {}).get("caller_intake", {})
    window_name = time_window["name"] if time_window else "Business Hours"

    # --- Greeting ---
    is_after_hours = window_name.lower() in ("after hours", "weekend")
    if is_after_hours and pb.get("after_hours_message"):
        greeting_instruction = (
            f'Greet the caller using this message: "{pb["after_hours_message"]}"'
        )
    else:
        greeting_instruction = (
            f'Greet the caller using this exact greeting: "{pb["greeting_script"]}"'
        )

    # --- Caller intake fields ---
    intake_lines = _build_intake_instructions(intake)

    # --- Services offered (from service_configs) ---
    services_section = _build_services_section(service_configs)

    # --- Non-services ---
    non_services_section = _build_non_services_section(non_services)

    # --- Service zones (deduplicated across all configs) ---
    zones_section = _build_zones_section(service_configs)

    # --- Non-service areas ---
    non_service_areas_section = _build_non_service_areas_section(non_service_areas)

    # --- FAQs ---
    faq_lines = []
    for faq in faqs:
        faq_lines.append(f"  Q: {faq['question']}\n  A: {faq['answer']}")
    faqs_str = "\n\n".join(faq_lines) if faq_lines else "  No FAQs configured."

    # --- Fees ---
    fees_section = _build_fees_section(service_configs)

    # --- Memberships ---
    memberships_section = _build_memberships_section(memberships)

    # --- Probing questions per service ---
    probing_section = _build_probing_section(service_configs, global_questions)

    return f"""PERSONA:
You are the virtual receptionist for {company_name}.
You are currently handling calls during the {window_name} window.

CONVERSATION STYLE:
- This is a phone call. Keep each response to 1-2 sentences. Be warm but brief.

CRITICAL RULE — ONE QUESTION PER TURN:
You MUST ask exactly ONE question per response, then STOP and wait for the caller to answer.
- WRONG: "Is that correct? And what's your service address?" (two questions — NEVER do this)
- WRONG: "How old is the unit? And have you tried anything?" (two questions — NEVER do this)
- WRONG: "Could you tell me your name and address?" (two questions — NEVER do this)
- RIGHT: "May I have your full name?" (one question, then wait)
- RIGHT: "What's the service address, including the city or zip?" (one question, then wait)
- RIGHT: "Is that correct?" (one question, then wait)
If you need to confirm something AND ask a new question, confirm FIRST, wait for the response, THEN ask the next question in a separate turn.

CONVERSATIONAL RULES:
1. [One-time] {greeting_instruction}
   After greeting, STOP and wait for the caller to tell you why they are calling. Do NOT ask for their name or any other information yet.
2. [After caller states their need] Before collecting any information, check two things FIRST:
   a. SERVICE CHECK: If the caller asks about a service not in the SERVICES OFFERED list below, check the NON-SERVICES list. If it matches a non-service, use the provided response. If it's not in either list, let them know politely and take a message.
   b. SERVICE AREA CHECK: If the caller mentions a location or address, check it against the SERVICE ZONES and NON-SERVICE AREAS below. If they match a non-service area, use the provided response script. If their location is not in any service zone, let them know politely — do NOT collect their info first.
   Then determine the call type:
   - SERVICE CALL (caller clearly needs repair, installation, quote, or scheduling): Acknowledge what they need, identify which service/trade it falls under, then begin collecting caller information one piece at a time.
   - QUICK QUESTION (caller only has a question answerable from the FAQ list): Answer their question directly. Do NOT start collecting fields unless they also want to schedule service.
   - VAGUE / UNCLEAR (caller doesn't know what they need, describes symptoms without a clear request, or is unsure): Ask a brief clarifying question to understand their situation before deciding the call type. For example: "It sounds like something's going on — can you tell me a bit more about what you're experiencing?" Do NOT default to scheduling a service call without understanding their need first.
3. [Service calls only] Collect caller information one field at a time, waiting for the response before asking the next:
{intake_lines}

   ADDRESS VALIDATION (CRITICAL):
   When collecting the service address, you MUST get a complete address that includes either a city name or a zip code — a street address alone is NOT enough.
   - If the caller gives only a street address (e.g. "456 Cypress Street") WITHOUT a city or zip code, ask them: "And what city is that in?" or "What's the zip code there?"
   - Once you have the caller's city or zip code, check it against the SERVICE ZONES below.
   - If NOT in a service zone, check NON-SERVICE AREAS for a specific response. Otherwise, let them know politely that the location is outside the service area. Do NOT continue collecting remaining fields.
   - If the city or zip code IS in a service zone, continue collecting the remaining fields.
   - Do NOT proceed past address collection without confirming the caller is in the service area.
4. [Service calls only] Ask probing questions relevant to the caller's service need (see PROBING QUESTIONS section). These help the dispatch team prepare. Ask them naturally, one at a time.
5. [Loop] Handle the caller's need:
   - If they need service: make sure all required caller info and relevant probing questions are addressed
   - If they have a question: answer from the FAQ list below
   - If the service or area is not offered: let them know politely using the provided response if available
   - If you cannot help: take a message
6. [One-time] When the conversation is complete, call the end_call function tool with the structured call data. Do NOT say goodbye first — the system will handle the closing after you call the tool. Just call end_call when you have all the information you need.

{services_section}

{non_services_section}

{zones_section}

{non_service_areas_section}

{fees_section}

{memberships_section}

{probing_section}

FREQUENTLY ASKED QUESTIONS:
{faqs_str}

GUARDRAILS:
- NEVER make up information. You have NO access to scheduling, dispatch, appointment, or account systems. You cannot look up appointments, ETAs, technician locations, or account details. If a caller asks about an existing appointment or technician status, say: "I don't have access to that information, but I can take a message and have someone from the team get back to you."
- Never quote exact pricing for repairs — you may mention the dispatch fee amount listed above, but actual repair costs require an on-site assessment.
- Never guarantee same-day service — say "depending on availability" or "we'll do our best."
- Never diagnose the issue over the phone — only collect information about symptoms.
- Never make promises about warranty coverage — let the technician assess on-site.
- Never give legal or safety advice — if the caller mentions a gas leak, electrical fire, or flooding, tell them to leave the area and call 911 first, then stay on the line with you.
- If you don't know the answer, take a message and let them know someone will follow up.
- Keep responses concise and conversational — this is a phone call, not an essay.
CRITICAL — ENDING THE CALL:
When the conversation is complete, call end_call BEFORE saying goodbye. The system will generate the goodbye message after the tool runs. Do NOT say goodbye yourself — just call the tool.
- caller_name: caller's name or "unknown"
- caller_phone: caller's phone number or "unknown"
- intent: one of schedule_service, request_quote, general_inquiry, faq, message, emergency
- summary: brief summary of the ENTIRE conversation (all topics discussed)
- urgency: one of normal, urgent, emergency
- collected_fields: dict with ALL collected info including "service" (e.g. "Plumbing"), "sub_service" (e.g. "Running Toilet"), "service_address", "issue_description", "is_homeowner", "is_residential", and any other fields. Empty dict if nothing collected."""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _build_intake_instructions(intake: dict) -> str:
    """Build caller intake field instructions from ai_settings.caller_intake."""
    lines = []

    if intake.get("collect_name", True):
        verify = " Verify by reading it back." if intake.get("verify_name") else ""
        lines.append(f'  - "caller_name": Caller\'s full name (required).{verify}')

    if intake.get("collect_callback_number", True):
        verify = (
            " Read the number back to confirm."
            if intake.get("verify_callback_number")
            else ""
        )
        lines.append(f'  - "caller_phone": Callback phone number (required).{verify}')

    if intake.get("collect_email"):
        verify = (
            " Spell it back to confirm."
            if intake.get("verify_email")
            else ""
        )
        lines.append(f'  - "caller_email": Email address (optional).{verify}')

    if intake.get("collect_service_address", True):
        verify_parts = []
        if intake.get("verify_address_zone"):
            verify_parts.append("check against service zones")
        if intake.get("verify_address_readback"):
            verify_parts.append("read back to confirm")
        verify = (" " + " and ".join(verify_parts).capitalize() + ".") if verify_parts else ""
        lines.append(f'  - "service_address": Service address including city or zip code (required).{verify}')

    if intake.get("ask_unit_apartment"):
        lines.append('  - "unit_apartment": Unit or apartment number (optional, ask if applicable).')

    if intake.get("ask_residential_or_commercial"):
        lines.append('  - "is_residential": Ask if this is a residential or commercial property (required).')

    if intake.get("ask_if_homeowner"):
        lines.append('  - "is_homeowner": Ask if the caller is the homeowner or tenant (required for residential).')

    if intake.get("ask_business_name"):
        lines.append('  - "business_name": If commercial, ask for the business name (required for commercial).')

    if intake.get("ask_responsible_for_billing"):
        lines.append('  - "responsible_for_billing": Ask if caller is responsible for billing (optional).')

    # Always collect issue description
    lines.append('  - "issue_description": Description of the issue or what they need (required).')
    lines.append('  - "preferred_timeframe": Preferred timeframe for service (optional, ask naturally).')

    return "\n".join(lines)


def _build_services_section(service_configs: list) -> str:
    """Build SERVICES OFFERED section from service configs."""
    if not service_configs:
        return "SERVICES OFFERED:\n  No services configured for this time window."

    lines = ["SERVICES OFFERED:"]
    for config in service_configs:
        service = config["service"]
        subs = config.get("sub_services", [])
        if subs:
            sub_list = ", ".join(subs)
            lines.append(f"  {service}: {sub_list}")
        else:
            lines.append(f"  {service}")
    return "\n".join(lines)


def _build_non_services_section(non_services: list) -> str:
    """Build NON-SERVICES section. Handles both string-only and dict formats."""
    if not non_services:
        return "SERVICES NOT OFFERED:\n  None configured."

    lines = ["SERVICES NOT OFFERED:"]
    for ns in non_services:
        if isinstance(ns, dict):
            name = ns.get("name", "")
            script = ns.get("response_script", "")
            if script:
                lines.append(f'  - {name}: "{script}"')
            else:
                lines.append(f"  - {name}")
        else:
            # string-only format (current ResolvePlaybookAction)
            lines.append(f"  - {ns}")
    return "\n".join(lines)


def _build_zones_section(service_configs: list) -> str:
    """Build SERVICE ZONES from deduplicated zone entries across all configs."""
    all_zips = set()
    all_cities = set()

    for config in service_configs:
        for zone in config.get("zones", []):
            if zone["type"] == "zip":
                all_zips.add(zone["value"])
            elif zone["type"] in ("city", "county"):
                all_cities.add(zone["value"])

    parts = []
    if all_cities:
        parts.append("Cities: " + ", ".join(sorted(all_cities)))
    if all_zips:
        parts.append("Zip codes: " + ", ".join(sorted(all_zips)))

    if not parts:
        return "SERVICE ZONES:\n  No zones configured."

    return "SERVICE ZONES:\n  " + "\n  ".join(parts)


def _build_non_service_areas_section(non_service_areas: list) -> str:
    """Build NON-SERVICE AREAS section with custom response scripts."""
    if not non_service_areas:
        return "NON-SERVICE AREAS:\n  None configured."

    lines = ["NON-SERVICE AREAS:"]
    for area in non_service_areas:
        area_type = area.get("type", "location")
        value = area["value"]
        script = area.get("response_script", "")
        if script:
            lines.append(f'  - {value} ({area_type}): "{script}"')
        else:
            lines.append(f"  - {value} ({area_type}): Outside service area.")
    return "\n".join(lines)


def _build_fees_section(service_configs: list) -> str:
    """Build DISPATCH FEES section from service config fee data."""
    seen = set()
    lines = ["DISPATCH FEES:"]

    for config in service_configs:
        fee = config.get("fee")
        if not fee:
            continue
        key = (fee["label"], fee["amount"])
        if key in seen:
            continue
        seen.add(key)

        credit_note = ""
        if fee.get("credited_toward_work"):
            credit_note = " (credited toward the cost of repair)"

        lines.append(
            f"  - {fee['label']}: ${fee['amount']:.0f}{credit_note}"
        )
        if fee.get("description"):
            lines.append(f"    {fee['description']}")

    if len(lines) == 1:
        lines.append("  No fees configured.")

    return "\n".join(lines)


def _build_memberships_section(memberships: list) -> str:
    """Build MEMBERSHIPS section."""
    if not memberships:
        return "MEMBERSHIPS:\n  No membership plans configured."

    lines = ["MEMBERSHIPS:"]
    for m in memberships:
        lines.append(f"  - {m['name']}: {m['description']}")
    return "\n".join(lines)


def _build_probing_section(service_configs: list, global_questions: list) -> str:
    """Build PROBING QUESTIONS section, organized by service."""
    lines = ["PROBING QUESTIONS:"]
    lines.append("  Ask these questions naturally during the conversation, one at a time, based on the caller's service need.")

    if global_questions:
        lines.append("\n  For ALL service calls:")
        for q in global_questions:
            lines.append(f"    - {q}")

    for config in service_configs:
        questions = config.get("probing_questions", [])
        if questions:
            service = config["service"]
            lines.append(f"\n  For {service} calls:")
            for q in questions:
                lines.append(f"    - {q}")

    if len(lines) == 2 and not global_questions:
        lines.append("  No probing questions configured.")

    return "\n".join(lines)
