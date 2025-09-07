import os
import logging
from main import create_bot_app
from bot.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    app = create_bot_app()

    # Render expects you to listen on port 8080
    port = int(os.environ.get("PORT", 8080))
    token = BOT_TOKEN

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=token,
        webhook_url=f"https://your-app-name.onrender.com/{token}"
    )
import os
import logging
from main import create_bot_app
from bot.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    app = create_bot_app()

    # Render expects you to listen on port 8080
    port = int(os.environ.get("PORT", 8080))
    token = BOT_TOKEN

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=token,
        webhook_url=f"https://holderxr.onrender.com/{token}"
    )
