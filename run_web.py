import threading
import asyncio
from flask import Flask
from main import main_async  # only async function

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot + Flask is running!"

def run_bot():
    loop = asyncio.new_event_loop()        # new loop for this thread
    asyncio.set_event_loop(loop)
    loop.create_task(main_async())         # schedule bot
    loop.run_forever()                     # keep loop alive

if __name__ == "__main__":
    # start bot in background thread
    threading.Thread(target=run_bot, daemon=True).start()

    # run flask server
    app.run(host="0.0.0.0", port=10000)
    