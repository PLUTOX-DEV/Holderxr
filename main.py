import logging
import os
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from bot.config import BOT_TOKEN
from bot.db import init_db
from bot.handlers import cmd_start, cmd_admin, on_button, on_message, send_channel_pin

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    force=True,
)
log = logging.getLogger("bot")


def create_bot_app():
    token = BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set. Put it in .env or Render Environment Variables.")

    init_db()

    app = Application.builder().token(token).build()

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    # Schedule pin message
    app.job_queue.run_once(send_channel_pin, when=5)

    log.info("🤖 Bot is ready (returning Application)...")
    return app
