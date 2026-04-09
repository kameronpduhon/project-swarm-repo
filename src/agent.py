import asyncio
import logging
from typing import Literal

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
    get_job_context,
    room_io,
)
from livekit.plugins import google, noise_cancellation

from call_results import log_call_results
from playbook import load_playbook
from prompt_builder import build_prompt

logger = logging.getLogger("voice-agent")

load_dotenv(".env.local")

VALID_INTENTS = Literal[
    "schedule_service",
    "request_quote",
    "general_inquiry",
    "faq",
    "message",
    "emergency",
]

VALID_URGENCY = Literal["normal", "urgent", "emergency"]

_VALID_INTENTS = {
    "schedule_service",
    "request_quote",
    "general_inquiry",
    "faq",
    "message",
    "emergency",
}
_VALID_URGENCY = {"normal", "urgent", "emergency"}


def normalize_end_call_payload(
    intent: str, urgency: str, collected_fields: object
) -> tuple[str, str, dict]:
    """Normalize and validate end_call inputs, returning safe values.

    Invalid intent defaults to 'general_inquiry'.
    Invalid urgency defaults to 'normal'.
    Non-dict collected_fields becomes empty dict.
    """
    if intent not in _VALID_INTENTS:
        logger.warning(
            "end_call received invalid intent '%s', defaulting to 'general_inquiry'",
            intent,
        )
        intent = "general_inquiry"

    if urgency not in _VALID_URGENCY:
        logger.warning(
            "end_call received invalid urgency '%s', defaulting to 'normal'",
            urgency,
        )
        urgency = "normal"

    if not isinstance(collected_fields, dict):
        logger.warning(
            "end_call received non-dict collected_fields: %s",
            type(collected_fields),
        )
        collected_fields = {}

    return intent, urgency, collected_fields


class VoiceAgent(Agent):
    def __init__(self, instructions: str) -> None:
        super().__init__(instructions=instructions)
        self._shutdown_task: asyncio.Task | None = None

    @function_tool()
    async def end_call(
        self,
        context: RunContext,
        caller_name: str,
        caller_phone: str,
        intent: VALID_INTENTS,
        summary: str,
        urgency: VALID_URGENCY,
        collected_fields: dict,
    ):
        """End the call and log the results. Call this IMMEDIATELY after your
        closing statement. Do not say anything else after calling this tool.

        Args:
            caller_name: The caller's name ("unknown" if not collected).
            caller_phone: The caller's phone number ("unknown" if not collected).
            intent: The caller's primary intent.
            summary: Brief summary of the ENTIRE conversation including all topics.
            urgency: The urgency level of the call.
            collected_fields: All information collected. Include keys like service,
                sub_service, service_address, issue_description, is_homeowner, etc.
        """
        intent, urgency, collected_fields = normalize_end_call_payload(
            intent, urgency, collected_fields
        )

        results = {
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "intent": intent,
            "summary": summary,
            "urgency": urgency,
            "collected_fields": collected_fields,
        }

        log_call_results(results)

        # --- Shutdown sequence ---
        # Gemini already spoke the closing via prompt instructions before calling
        # this tool. We wait for that speech to finish, then tear down.
        # NOTE: session.say() does NOT work with Gemini native audio (no TTS).

        @context.session.once("close")
        def _on_session_close(ev):
            # Cancel pending shutdown task if session closes first (e.g. caller hangs up)
            if self._shutdown_task and not self._shutdown_task.done():
                self._shutdown_task.cancel()

            job_ctx = get_job_context()

            async def _delete_room():
                logger.info("Deleting room to disconnect SIP caller")
                await job_ctx.delete_room()

            job_ctx.add_shutdown_callback(_delete_room)
            job_ctx.shutdown(reason="end_call")

        async def _shutdown_after_playout():
            try:
                await context.wait_for_playout()
                logger.info("Playout complete, shutting down session")
            except Exception:
                logger.warning(
                    "Playout wait failed, shutting down session anyway", exc_info=True
                )
            finally:
                context.session.shutdown()

        self._shutdown_task = asyncio.create_task(_shutdown_after_playout())

        return "Call ended. Do not say anything else."


server = AgentServer()


@server.rtc_session(agent_name="voice-agent")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    resolved = load_playbook()
    instructions = build_prompt(resolved)

    logger.info("Playbook loaded for %s", resolved["playbook"]["name"])

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
