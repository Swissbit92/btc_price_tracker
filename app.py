# app.py
from flask import Flask, jsonify

from btc_tracker_mongodb.pipeline import run_update_all

app = Flask(__name__)

@app.route("/", methods=["GET"])
def run_update():
    try:
        run_update_all(timeframe="1h")
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # For local testing
    app.run(host="0.0.0.0", port=8080)
