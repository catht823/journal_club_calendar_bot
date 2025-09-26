from flask import Flask, jsonify
from main import run_once

app = Flask(__name__)

@app.get("/healthz")
def health():
    return "ok", 200

@app.post("/run")
def run():
    run_once()
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)