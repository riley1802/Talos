"""Telegram bot handler — routes messages to the orchestrator loop."""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


def is_enabled() -> bool:
    return bool(TELEGRAM_TOKEN)


async def start() -> None:
    if not is_enabled():
        logger.info("Telegram bot disabled (TELEGRAM_BOT_TOKEN not set)")
        return

    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))

    logger.info("Telegram bot starting...")
    await app.run_polling()


async def _cmd_start(update, context) -> None:
    await update.message.reply_text(
        "Talos v4.0 online. Send a message to interact."
    )


async def _on_message(update, context) -> None:
    from orchestrator.loop import process_message
    user_text = update.message.text
    result = await process_message(user_text)
    response = result.get("response") or result.get("reason", "No response")
    await update.message.reply_text(response)
