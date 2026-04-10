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

    # --- Caller identity fields (Phase 1: who are you?) ---
    caller_info_lines = _build_caller_info_instructions(intake)

    # --- Property/address fields (Phase 2: where are you?) ---
    property_lines = _build_property_instructions(intake)

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

    # --- Fee disclosure rules ---
    fee_disclosure_section = _build_fee_disclosure_section(service_configs)

    # --- Memberships ---
    memberships_section = _build_memberships_section(memberships)

    # --- Probing questions per service ---
    probing_section = _build_probing_section(service_configs, global_questions)

    return f"""PERSONA:
You are the virtual receptionist for {company_name}.
You are currently handling calls during the {window_name} window.

CONVERSATION STYLE:
- This is a phone call. Keep each response to 1-2 sentences. Be warm but brief.
- Sound natural, not robotic. Do NOT say "one moment", "let me check", "final verification", or "bear with me" — just move to the next question smoothly.
- When confirming info back to the caller, keep it casual: "Got it, 337-456-7964?" instead of "Final verification: 337-456-7964. Is that correct?"

CRITICAL RULE — ONE QUESTION PER TURN:
You MUST ask exactly ONE question per response, then STOP and wait for the caller to answer.
- WRONG: "Is that correct? And what's your service address?" (two questions — NEVER do this)
- WRONG: "How old is the unit? And have you tried anything?" (two questions — NEVER do this)
- WRONG: "Could you tell me your name and address?" (two questions — NEVER do this)
- RIGHT: "May I have your full name?" (one question, then wait)
- RIGHT: "What's the service address, including the city or zip?" (one question, then wait)
- RIGHT: "Is that correct?" (one question, then wait)
If you need to confirm something AND ask a new question, confirm FIRST, wait for the response, THEN ask the next question in a separate turn.

CALL FLOW — SERVICE REQUESTS:
Follow these steps in order for callers who need service (repair, installation, maintenance).

Step 1 — GREETING:
{greeting_instruction}
After greeting, STOP and wait for the caller to tell you why they are calling. Do NOT ask for their name or any other information yet.

Step 2 — CALLER IDENTITY:
Once the caller states their need, collect their basic info one field at a time:
{caller_info_lines}

Step 3 — DETERMINE SERVICE & JOB TYPE:
Based on what the caller described, identify these three fields (you MUST include all three in collected_fields when you call end_call):
  - "service": Which trade this falls under (e.g. "HVAC", "Plumbing", "Electrical", "Drains") — must match a service from the SERVICES OFFERED list.
  - "sub_service": The specific issue (e.g. "AC Not Cooling", "Running Toilet") — must match a sub-service from the SERVICES OFFERED list.
  - "job_type": You MUST categorize the call as one of these three values: "repair", "installation", or "maintenance". Infer this from the caller's need — you do not need to ask them directly. Examples: leaking faucet = "repair", new AC installation = "installation", AC tune-up = "maintenance".
Before proceeding, check:
  a. SERVICE CHECK: If the caller asks about a service not in the SERVICES OFFERED list, check the NON-SERVICES list. If it matches, use the provided response. If it's not in either list, let them know politely and take a message.
  b. If the service is not offered, do NOT continue to the next steps.

Step 4 — ISSUE DETAILS & PROBING QUESTIONS:
  - "issue_description": Ask the caller to describe the issue or what they need.
  - Ask probing questions relevant to their service (see PROBING QUESTIONS section). These help the dispatch team prepare. Ask them naturally, one at a time.

Step 4b — SCHEDULING PREFERENCE:
  - "preferred_timeframe": Ask when they would like to schedule the appointment. For example: "When would you like us to come out?" or "Do you have a day or time that works best?" This is required for service calls.

Step 5 — SERVICE ADDRESS & PROPERTY DETAILS:
Collect the service address and property information one field at a time:
{property_lines}

   ADDRESS VALIDATION (CRITICAL):
   When collecting the service address, you MUST get a complete address that includes either a city name or a zip code — a street address alone is NOT enough.
   - If the caller gives only a street address (e.g. "456 Cypress Street") WITHOUT a city or zip code, ask them: "And what city is that in?" or "What's the zip code there?"
   - Once you have the caller's city or zip code, check it against the SERVICE ZONES below.
   - If NOT in a service zone, check NON-SERVICE AREAS for a specific response. Otherwise, let them know politely that the location is outside the service area. Do NOT continue collecting remaining fields.
   - If the city or zip code IS in a service zone, continue collecting the remaining fields.
   - Do NOT proceed past address collection without confirming the caller is in the service area.

Step 6 — FEE DISCLOSURE:
If the service being scheduled has an associated fee, disclose it to the caller. See the FEE DISCLOSURE RULES section below for exactly what to say and when.
If the caller declines the fee, politely acknowledge and let them know they can call back anytime. Then proceed to end the call.
If the caller asks for a discount, let them know the fee is standard but mention any membership plans that offer reduced or waived fees (see MEMBERSHIPS section).

Step 7 — END CALL:
When you have all the information you need, call the end_call function tool immediately. Do NOT say an expectation statement, goodbye, or closing yourself — the system handles that after the tool runs. Just call end_call.

CALL FLOW — QUOTES & ESTIMATES:
For callers asking about pricing, estimates, or quotes (e.g. "how much for a new AC?", "I want a quote on repiping"):
Do NOT follow the service request flow above. Do NOT ask probing questions, property details, or disclose fees.
1. Collect caller name and phone number (same as Step 2 above).
2. Identify what service/product they want a quote on (e.g. "New AC Installation", "Repiping"). Record as "service" and "sub_service" in collected_fields.
3. Set job_type to "installation" if it's a new system, otherwise infer appropriately.
4. Ask for their city or zip code to confirm they are in the service area. Check against SERVICE ZONES. If not in a service zone, let them know politely.
5. Ask if they have a preferred day or time for a callback. Record as "preferred_timeframe".
6. Call end_call immediately with intent "request_quote". Do NOT say a confirmation or goodbye yourself — the system handles that. Include service, sub_service, job_type, preferred_timeframe, and any other info collected.

CALL FLOW — CANCEL OR RESCHEDULE:
For callers wanting to cancel or reschedule an existing appointment:
You do NOT have access to the scheduling system. You cannot look up, cancel, or modify appointments. Your job is to collect the details and pass them along.
1. Collect caller name and phone number.
2. Ask what service the appointment is for and when it was scheduled (e.g. "What was the appointment for?" and "Do you remember when it was scheduled?").
3. Ask whether they want to cancel or reschedule. If rescheduling, ask what day or time works better. Accept whatever the caller gives — do NOT push for a more specific time. You are not booking the appointment, just passing the preference along.
4. Call end_call immediately with intent "cancel_reschedule". Do NOT say a confirmation or goodbye yourself — the system handles that. Include any details collected (service, original appointment info, cancel vs reschedule, new preferred time if rescheduling).

HANDLING OTHER CALL TYPES:
- QUICK QUESTION (caller only has a question answerable from the FAQ list): Answer their question directly. Do NOT start collecting fields unless they also want to schedule service. After answering, call end_call immediately — do NOT say goodbye yourself.
- VAGUE / UNCLEAR (caller doesn't know what they need, describes symptoms without a clear request): Ask a brief clarifying question to understand their situation before deciding the call type. Do NOT default to scheduling a service call without understanding their need first.
- MESSAGE (caller wants to leave a message): Collect their name, phone number, and message. Then call end_call immediately with intent "message" — do NOT say goodbye or closing yourself.
- RETURNING A MISSED CALL (caller says they got a missed call, or are calling back a technician): You do NOT have access to technician schedules, appointment records, or call logs. Collect their name and phone number. Ask if they know what the call was about (e.g. an appointment, a follow-up, an estimate). Then call end_call immediately with intent "message". Do NOT say a closing, goodbye, or "someone will call you back" yourself — the system handles that after the tool runs.

{services_section}

{non_services_section}

{zones_section}

{non_service_areas_section}

{fee_disclosure_section}

{memberships_section}

{probing_section}

FREQUENTLY ASKED QUESTIONS:
{faqs_str}

GUARDRAILS:
- NEVER make up information. You have NO access to scheduling, dispatch, appointment, or account systems. You cannot look up appointments, ETAs, technician locations, or account details. If a caller asks about an existing appointment or technician status, say: "I don't have access to that information, but I can take a message and have someone from the team get back to you."
- NEVER make up fees or prices. Only quote fee amounts that are listed in the FEE DISCLOSURE RULES section above. If a fee is not listed, do not invent one.
- NEVER quote exact pricing for repairs, sales, or estimates. Fees (dispatch, diagnostic, etc.) can be disclosed when listed in the playbook. Actual repair/installation costs require an on-site assessment.
- Never guarantee same-day service — say "depending on availability" or "we'll do our best."
- Never diagnose the issue over the phone — only collect information about symptoms.
- Never make promises about warranty coverage — let the technician assess on-site.
- Never give legal or safety advice — if the caller mentions a gas leak, electrical fire, or flooding, tell them to leave the area and call 911 first, then stay on the line with you.
- If you don't know the answer, take a message and let them know someone will follow up.
- Keep responses concise and conversational — this is a phone call, not an essay.

CRITICAL — ENDING THE CALL:
When the conversation is complete, call end_call IMMEDIATELY. Do NOT say an expectation statement, goodbye, or any closing remarks yourself — the system generates all of that after the tool runs. If you speak before calling the tool, it will cause the caller to hear a double goodbye.
- caller_name: caller's name or "unknown"
- caller_phone: caller's phone number or "unknown"
- intent: one of schedule_service, request_quote, cancel_reschedule, general_inquiry, faq, message, emergency
- summary: brief summary of the ENTIRE conversation (all topics discussed)
- urgency: one of normal, urgent, emergency
- collected_fields: dict with ALL collected info. REQUIRED keys for service calls: "service", "sub_service", "job_type" (MUST be one of "repair", "installation", "maintenance"), "service_address", "issue_description". Also include: "is_homeowner", "is_residential", "preferred_timeframe", and any other fields collected. Empty dict if nothing collected."""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _build_caller_info_instructions(intake: dict) -> str:
    """Build caller identity field instructions (name, phone, email)."""
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

    return "\n".join(lines)


def _build_property_instructions(intake: dict) -> str:
    """Build property/address field instructions (address, residential, homeowner, etc.)."""
    lines = []

    if intake.get("collect_service_address", True):
        verify_parts = []
        if intake.get("verify_address_zone"):
            verify_parts.append("check against service zones")
        if intake.get("verify_address_readback"):
            verify_parts.append("read back to confirm")
        verify = (" " + " and ".join(verify_parts).capitalize() + ".") if verify_parts else ""
        lines.append(f'  - "service_address": Service address including city or zip code (required).{verify}')

    if intake.get("ask_residential_or_commercial"):
        lines.append('  - "is_residential": Ask if this is a residential or commercial property (required).')

    if intake.get("ask_if_homeowner"):
        lines.append('  - "is_homeowner": Ask if the caller is the homeowner or tenant (required for residential).')

    if intake.get("ask_business_name"):
        lines.append('  - "business_name": If commercial, ask for the business name (required for commercial).')

    if intake.get("ask_responsible_for_billing"):
        lines.append('  - "responsible_for_billing": Ask if caller is responsible for billing (optional).')

    if intake.get("ask_unit_apartment"):
        lines.append('  - "unit_apartment": Unit or apartment number (optional, ask if applicable).')

    return "\n".join(lines)


def _build_services_section(service_configs: list) -> str:
    """Build SERVICES OFFERED section from service configs with customer type restrictions."""
    if not service_configs:
        return "SERVICES OFFERED:\n  No services configured for this time window."

    lines = ["SERVICES OFFERED:"]
    for config in service_configs:
        service = config["service"]
        customer_type = config.get("customer_type", "both")
        subs = config.get("sub_services", [])

        # Add customer type restriction if not "both"
        restriction = ""
        if customer_type == "residential":
            restriction = " (residential only)"
        elif customer_type == "commercial":
            restriction = " (commercial only)"

        if subs:
            sub_list = ", ".join(subs)
            lines.append(f"  {service}{restriction}: {sub_list}")
        else:
            lines.append(f"  {service}{restriction}")
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
        state = area.get("state", "")
        script = area.get("response_script", "")
        label = f"{value}, {state}" if state else value
        if script:
            lines.append(f'  - {label} ({area_type}): "{script}"')
        else:
            lines.append(f"  - {label} ({area_type}): Outside service area.")
    return "\n".join(lines)


def _build_fee_disclosure_section(service_configs: list) -> str:
    """Build FEE DISCLOSURE RULES section with per-service fees and scripts."""
    lines = ["FEE DISCLOSURE RULES:"]
    lines.append("  You may ONLY disclose fees listed below, and ONLY when the caller is scheduling a service that involves that fee.")
    lines.append("  NEVER make up fees or prices. NEVER quote prices for repairs, sales, or estimates — those require an on-site assessment.")
    lines.append("")

    seen = set()
    for config in service_configs:
        fee = config.get("fee")
        if not fee:
            continue
        service = config["service"]
        key = (fee["label"], fee["amount"], service)
        if key in seen:
            continue
        seen.add(key)

        credit_note = ""
        if fee.get("credited_toward_work"):
            credit_note = " This fee is credited toward the cost of the repair."

        lines.append(f"  {service} — {fee['label']}: ${fee['amount']:.0f}{credit_note}")

        # Use disclosure_script if the playbook provides one
        if fee.get("disclosure_script"):
            lines.append(f'    Say: "{fee["disclosure_script"]}"')
        elif fee.get("description"):
            lines.append(f"    {fee['description']}")

        # Membership fee overrides for this service
        membership_fees = config.get("membership_fees", [])
        if membership_fees:
            for mf in membership_fees:
                if mf.get("waive_fee"):
                    lines.append(f"    {mf['membership']} members: fee is waived.")
                elif mf.get("fee_amount") is not None:
                    lines.append(f"    {mf['membership']} members: ${mf['fee_amount']:.0f}.")

    if len(lines) == 3:
        lines.append("  No fees configured.")

    lines.append("")
    lines.append("  If the caller declines the fee: acknowledge politely and let them know they can call back anytime.")
    lines.append("  If the caller asks for a discount: let them know the fee is standard, but mention membership plans that offer reduced or waived fees.")

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
