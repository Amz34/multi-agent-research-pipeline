"""HTTP API: POST /run {"topic": "..."} | GET /health | GET /"""
import os

from flask import Flask, jsonify, request

from agents.coordinator import run_pipeline_safe

app = Flask(__name__)

PORT = int(os.environ.get("PIPELINE_PORT", "8088"))
HOST = os.environ.get("PIPELINE_HOST", "127.0.0.1")  # private by default - never public

MAX_TOPIC_LEN = 500


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/")
def index():
    return jsonify({"name": "4-agent research pipeline", "endpoints": ["POST /run", "GET /health"]})


@app.post("/run")
def run():
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "topic is required"}), 400
    if len(topic) > MAX_TOPIC_LEN:
        return jsonify({"error": f"topic too long (max {MAX_TOPIC_LEN} chars)"}), 400
    result = run_pipeline_safe(topic)
    status = 200 if result.get("status") == "ok" else 500
    return jsonify(result), status


if __name__ == "__main__":
    app.run(host=HOST, port=PORT)
