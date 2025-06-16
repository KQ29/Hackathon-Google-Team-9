"""
WanderWise – lightweight Flask backend
• /recommend  → Gemini: suggest 3 destinations in GBP for given budget/travellers/keywords
• /explore    → Google Places: cafés, restaurants & sights for a city
• /select     → NO-OP (would normally persist the user’s choice)
• static files served from ./public
"""

import os, json, requests
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()                                   # read .env if present
app = Flask(__name__, static_folder='public')

# --------------------------------------------------------------------------
# ENVIRONMENT KEYS (put these in .env or export in your shell)
# --------------------------------------------------------------------------
GEMINI_KEY = os.getenv("GEMINI_KEY")             # Google AI Studio key
PLACES_KEY = os.getenv("PLACES_KEY")             # Google Places key

print("Gemini key loaded :", bool(GEMINI_KEY))
print("Places key loaded :", bool(PLACES_KEY))

# --------------------------------------------------------------------------
# HELPER – Gemini
# --------------------------------------------------------------------------
def call_gemini(prompt: str) -> str:
    """Return raw text from Gemini 2.0 Flash."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    )
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

# --------------------------------------------------------------------------
# ROUTES
# --------------------------------------------------------------------------
import json, re

@app.route("/recommend", methods=["POST"])
def recommend():
    """Return 3 destination suggestions as JSON list."""
    data       = request.get_json(force=True)
    budget     = int(data.get("budget", 0))
    travelers  = int(data.get("travelers", 1))
    keywords   = data.get("keywords", "")

    prompt = f"""
You are an expert travel concierge. All prices are in GBP.
The user has £{budget} total for {travelers} traveller(s).
Must-haves / keywords: {keywords or 'none'}.

Reply ONLY with a valid JSON array, no markdown, no commentary:
[{{"name":"City, Country","lat":..,"lng":..,"description":"..","estimated_cost":..}},...]
Return 3 destinations inside budget.
""".strip()

    try:
        raw = call_gemini(prompt).strip()
        # ---- extract JSON block even if Gemini wrapped it in text ----
        try:
            suggestions = json.loads(raw)               # happy path
        except json.JSONDecodeError:
            block = re.search(r"\[.*\]", raw, re.S)     # greedy match
            if not block:
                raise ValueError("No JSON found in Gemini output")
            suggestions = json.loads(block.group(0))

        if not isinstance(suggestions, list):
            raise ValueError("Parsed data is not a list")

        return jsonify(suggestions=suggestions)

    except Exception as err:
        print("Gemini parsing error:", err, "\nRAW:\n", raw)
        return jsonify(error="AI response error"), 502


# --------------------------------------------------------------------------
@app.route("/explore")
def explore():
    """Return 6 cafés / restaurants / sights for a city."""
    city = request.args.get("city", "")
    if not city:
        return jsonify(error="No city provided"), 400

    query = (
        f"top cafés or restaurants or tourist attractions in {city}"
    )
    url = (
        "https://maps.googleapis.com/maps/api/place/textsearch/json"
        f"?key={PLACES_KEY}&query={requests.utils.quote(query)}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])[:6]
        slim = [
            {"name": p["name"], "place_id": p["place_id"]}
            for p in results
        ]
        return jsonify(places=slim)
    except Exception as err:
        print("Places error:", err)
        return jsonify(error="Places lookup failed"), 502

# --------------------------------------------------------------------------
@app.route("/select", methods=["POST"])
def select():
    """NO-OP persistence placeholder."""
    # Normally we’d write to Firestore here. For local use we do nothing.
    return ("", 204)

# --------------------------------------------------------------------------
# STATIC FRONT-END
# --------------------------------------------------------------------------
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_public(path):
    """Serve files from ./public (index.html as default)."""
    return send_from_directory(app.static_folder, path or "index.html")

# --------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
