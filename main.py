import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from bot.config import BOT_TOKEN
from bot.db import init_db
from bot.handlers import cmd_start, cmd_admin, on_button, on_message, send_channel_pin


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger("bot")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set. Put it in .env")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    # Send pin message once when the bot starts
    app.job_queue.run_once(send_channel_pin, when=2)  # 2 sec after startup

    log.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
