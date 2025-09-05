from flask import Flask
import threading
import main  # your bot main.py

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

if __name__ == "__main__":
    threading.Thread(target=main.main).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
