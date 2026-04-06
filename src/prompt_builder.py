def build_prompt(content: dict, call_context: dict) -> str:
    """Convert playbook content + call_context into system instructions."""
    company = content["company_info"]
    services = content["services"]
    booking = content["booking"]
    expectations = content["expectations"]

    window = call_context.get("current_window", "business_hours")
    if window == "business_hours":
        greeting_instruction = (
            f'Greet the caller using this exact greeting: "{company["greeting"]}"'
        )
    else:
        greeting_instruction = (
            f'Greet the caller using this message: "{company["after_hours_message"]}"'
        )

    fields = content.get("field_collection", [])
    field_lines = []
    for f in fields:
        req = "required" if f.get("required") else "optional"
        field_lines.append(f'  - {f["label"]} ({req})')
    fields_str = "\n".join(field_lines)

    faqs = content.get("faqs", [])
    faq_lines = []
    for faq in faqs:
        faq_lines.append(f'  Q: {faq["question"]}\n  A: {faq["answer"]}')
    faqs_str = "\n\n".join(faq_lines)

    guardrails = content.get("guardrails", [])
    guardrail_lines = [f"- {g}" for g in guardrails]
    guardrails_str = "\n".join(guardrail_lines)

    offered_str = ", ".join(services.get("offered", []))
    not_offered_str = ", ".join(services.get("not_offered", []))
    areas_str = ", ".join(services.get("service_areas", []))

    return f"""PERSONA:
You are the virtual receptionist for {call_context["organization_name"]}.
You are currently handling calls during {window} hours.

CONVERSATIONAL RULES:
1. [One-time] {greeting_instruction}
2. [One-time] Identify the caller — ask for their name and phone number.
3. [Loop] Determine what the caller needs and handle it:
   - If they need service: collect these fields:
{fields_str}
   - If they have a question: answer from the FAQ list below
   - If the service or area is not offered: let them know politely
   - If you cannot help: take a message
4. [One-time] Close the call: "{company["closing"]}"
   You MUST fully finish speaking the closing before proceeding to step 5.
5. [One-time] ONLY after you have completely finished speaking the closing, call the end_call tool with all collected information.

SERVICES OFFERED:
{offered_str}

SERVICES NOT OFFERED:
{not_offered_str}

SERVICE AREAS:
{areas_str}

BOOKING INFO:
Method: {booking["method"]}
{booking["capacity_notes"]}
{booking["scheduling_rules"]}

EXPECTATIONS TO SHARE WITH CALLER:
Arrival window: {expectations["arrival_window"]}
Confirmation: {expectations["confirmation_method"]}
Cancellation: {expectations["cancellation_policy"]}

FREQUENTLY ASKED QUESTIONS:
{faqs_str}

TOOL INVOCATION:
When the conversation is complete and the caller is ready to hang up, invoke the end_call tool with:
- caller_name, caller_phone
- intent (one of: schedule_service, request_quote, general_inquiry, faq, message, emergency)
- summary (brief summary of the conversation)
- urgency (normal, urgent, or emergency)
- collected_fields (JSON string of key-value pairs of info collected)

GUARDRAILS:
{guardrails_str}
- Never make promises about scheduling or pricing unless specified above.
- If you don't know the answer, take a message and let them know someone will follow up.
- Keep responses concise and conversational — this is a phone call, not an essay."""
