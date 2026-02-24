"""Discord bot handler — routes messages to the orchestrator loop."""
import logging
import os

logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")


def is_enabled() -> bool:
    return bool(DISCORD_TOKEN)


async def start() -> None:
    if not is_enabled():
        logger.info("Discord bot disabled (DISCORD_BOT_TOKEN not set)")
        return

    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("Discord bot logged in as %s", client.user)

    @client.event
    async def on_message(message):
        if message.author == client.user:
            return
        if client.user and client.user.mentioned_in(message):
            from orchestrator.loop import process_message
            text = message.content.replace(f"<@{client.user.id}>", "").strip()
            result = await process_message(text)
            response = result.get("response") or result.get("reason", "No response")
            await message.channel.send(response)

    logger.info("Discord bot starting...")
    await client.start(DISCORD_TOKEN)
