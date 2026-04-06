import logging

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
)
from livekit.plugins import google, noise_cancellation

logger = logging.getLogger("voice-agent")

load_dotenv(".env.local")


class VoiceAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a friendly virtual receptionist for a home services company. "
                "You are currently handling a phone call. "
                "Greet the caller warmly and ask how you can help them today. "
                "Keep your responses concise and conversational — this is a phone call, not an essay. "
                "Do not use any special formatting, emojis, or markdown in your responses."
            ),
        )


server = AgentServer()


@server.rtc_session(agent_name="voice-agent")
async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    session = AgentSession(
        llm=google.realtime.RealtimeModel(
            model="gemini-3.1-flash-live-preview",
            voice="Puck",
        ),
    )

    await session.start(
        agent=VoiceAgent(),
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
