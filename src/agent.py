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
from livekit.agents.llm import RealtimeModel
from livekit.agents.voice.events import SpeechCreatedEvent
from livekit.agents.voice.speech_handle import SpeechHandle
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
        """End the call and log structured results.

        Args:
            caller_name: Caller's name or "unknown".
            caller_phone: Caller's phone number or "unknown".
            intent: Primary intent of the call.
            summary: Brief summary of the entire conversation.
            urgency: Urgency level.
            collected_fields: Dict of all collected info (service, sub_service, service_address, issue_description, etc.).
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

        # --- Shutdown sequence (matches SDK EndCallTool pattern) ---
        # Gemini Realtime auto-generates a tool reply speech after tool execution.
        # We must wait for THAT speech to finish playing, then shut down.

        llm = context.session.current_agent._get_activity_or_raise().llm

        def _on_speech_done(_: SpeechHandle) -> None:
            if (
                not isinstance(llm, RealtimeModel)
                or not llm.capabilities.auto_tool_reply_generation
            ):
                # Non-realtime: shutdown directly after current speech
                context.session.shutdown()
            else:
                # Gemini Realtime: wait for auto-generated tool reply speech
                self._shutdown_task = asyncio.create_task(
                    self._delayed_session_shutdown(context)
                )

        context.speech_handle.add_done_callback(_on_speech_done)

        @context.session.once("close")
        def _on_session_close(ev):
            if self._shutdown_task and not self._shutdown_task.done():
                self._shutdown_task.cancel()

            job_ctx = get_job_context()

            async def _delete_room():
                logger.info("Deleting room to disconnect SIP caller")
                await job_ctx.delete_room()

            job_ctx.add_shutdown_callback(_delete_room)
            job_ctx.shutdown(reason="end_call")

        return "Set expectations for what happens next (e.g. 'We'll get a technician scheduled and someone from the team will reach out to confirm'), then thank the caller warmly and say a brief goodbye. Say nothing else after."

    async def _delayed_session_shutdown(self, context: RunContext) -> None:
        """Wait for Gemini's auto-generated tool reply speech to finish, then shutdown."""
        speech_created_fut: asyncio.Future[SpeechHandle] = asyncio.Future()

        @context.session.once("speech_created")
        def _on_speech_created(ev: SpeechCreatedEvent) -> None:
            if not speech_created_fut.done():
                speech_created_fut.set_result(ev.speech_handle)

        try:
            speech_handle = await asyncio.wait_for(speech_created_fut, timeout=5.0)
            await speech_handle
            logger.info("Tool reply speech finished, shutting down session")
        except asyncio.TimeoutError:
            logger.warning("Tool reply speech timed out, shutting down session anyway")
        finally:
            context.session.off("speech_created", _on_speech_created)
            context.session.shutdown()


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
