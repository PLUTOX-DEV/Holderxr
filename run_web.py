# run_web.py
import os
import logging
from main import create_bot_app
from bot.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    app = create_bot_app()
    token = BOT_TOKEN

    port_env = os.environ.get("PORT")

    if port_env:
        # Webhook mode (Render/Production)
        port = int(port_env)
        service_name = os.environ.get("RENDER_SERVICE_NAME", "holderxr")
        webhook_url = os.environ.get(
            "WEBHOOK_URL",
            f"https://{service_name}.onrender.com/{token}"
        )
        logger.info("Starting webhook mode on port %s with URL %s", port, webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=webhook_url,
        )
    else:
        # Local dev (polling)
        logger.info("Starting polling mode (local development)")
        app.run_polling()
