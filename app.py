# app.py
from flask import Flask, jsonify
from btc_tracker_mongodb.update_hourly import main as update_main

app = Flask(__name__)

@app.route("/", methods=["GET"])
def run_update():
    try:
        update_main()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # For local testing
    app.run(host="0.0.0.0", port=8080)
