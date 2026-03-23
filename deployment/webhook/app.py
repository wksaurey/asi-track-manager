"""
Minimal GitHub webhook receiver.
Triggers update-app.ps1 when main branch is pushed.
"""
import hashlib
import hmac
import os
import subprocess
from flask import Flask, request, abort

app = Flask(__name__)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "").encode()
UPDATE_SCRIPT = os.environ.get("UPDATE_SCRIPT", "/scripts/update-app.ps1")


def verify_signature(payload: bytes, sig_header: str) -> bool:
    """Verify the GitHub HMAC-SHA256 signature."""
    if not WEBHOOK_SECRET:
        return True  # Skip verification if no secret configured (not recommended)
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(payload, signature):
        abort(403, "Invalid signature")

    data = request.get_json(force=True)
    ref = data.get("ref", "")

    if ref != "refs/heads/main":
        return "Not main branch — ignoring", 200

    # Run the update script asynchronously so the webhook returns quickly
    subprocess.Popen(
        ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", UPDATE_SCRIPT],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "Update triggered", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
