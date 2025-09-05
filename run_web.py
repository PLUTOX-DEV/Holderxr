import os
import asyncio
from flask import Flask
from dotenv import load_dotenv
import main  # your async main.py

load_dotenv()
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

if __name__ == "__main__":
    # Run bot in background async loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(main.main())  # schedule bot

    # Run Flask (blocking)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
