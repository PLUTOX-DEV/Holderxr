import threading
import asyncio
from flask import Flask
from telegram import Bot
from main import create_bot_app
from bot.config import BOT_TOKEN

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot + Flask is running!"


def run_bot():
    bot_app = create_bot_app()

    async def setup_and_run():
        bot = Bot(BOT_TOKEN)
        await bot.delete_webhook(drop_pending_updates=True)

        # ✅ Manual startup (no auto loop closing)
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(setup_and_run())
    loop.run_forever()


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
