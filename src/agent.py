import json
import logging

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    RunContext,
    cli,
    function_tool,
    room_io,
)
from livekit.plugins import google, noise_cancellation

from call_results import log_call_results
from playbook import load_playbook
from prompt_builder import build_prompt

logger = logging.getLogger("voice-agent")

load_dotenv(".env.local")


class VoiceAgent(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)

    @function_tool()
    async def end_call(
        self,
        context: RunContext,
        caller_name: str,
        caller_phone: str,
        intent: str,
        summary: str,
        urgency: str,
        collected_fields: str,
    ):
        """End the call and log the results. Call this when the conversation is
        complete and the caller is ready to hang up.

        Args:
            caller_name: The caller's name, if provided.
            caller_phone: The caller's phone number, if provided.
            intent: The caller's intent. One of: schedule_service, request_quote, general_inquiry, faq, message, emergency.
            summary: A brief summary of the conversation.
            urgency: The urgency level. One of: normal, urgent, emergency.
            collected_fields: JSON string of key-value pairs of information collected during the call.
        """
        if isinstance(collected_fields, str):
            try:
                fields = json.loads(collected_fields)
            except json.JSONDecodeError:
                fields = {"raw": collected_fields}
        elif isinstance(collected_fields, dict):
            fields = collected_fields
        else:
            fields = {}

        results = {
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "intent": intent,
            "summary": summary,
            "urgency": urgency,
            "collected_fields": fields,
        }

        log_call_results(results)

        return "Call ended successfully. Results logged."


server = AgentServer()


@server.rtc_session(agent_name="voice-agent")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    content, call_context = load_playbook()
    instructions = build_prompt(content, call_context)

    logger.info("Playbook loaded for %s", call_context["organization_name"])

    session = AgentSession(
        llm=google.realtime.RealtimeModel(
            model="gemini-3.1-flash-live-preview",
            voice="Puck",
        ),
    )

    await session.start(
        agent=VoiceAgent(instructions=instructions),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
