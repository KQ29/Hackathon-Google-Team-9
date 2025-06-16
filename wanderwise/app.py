"""
WanderWise – lightweight Flask backend

Routes:
• /recommend  → Gemini: suggest 3 destinations in GBP for given budget/travellers/keywords
• /explore    → Gemini: 6 cafés, restaurants & sights for a city (enriched w/ maps links)
• /select     → NO-OP (would normally persist the user’s choice)
• /chat       → Gemini: general-purpose travel assistant chat (optional)
• static files served from ./public
"""

import os
import json
import re
import logging
import urllib.parse
import requests
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

# --- CONFIGURATION & ENVIRONMENT ---------------------------------------------

load_dotenv()
GEMINI_KEY = os.environ.get("GEMINI_KEY")
PUBLIC_DIR = "public"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
)

app = Flask(__name__, static_folder=PUBLIC_DIR)

# Optional: Enable CORS for local frontend (optional, safe to skip)
try:
    from flask_cors import CORS
    CORS(app)
except ImportError:
    pass

# --- PROMPT TEMPLATES --------------------------------------------------------

EXPLORE_PROMPT = """
You are a local insider in {city}.
There are {travelers} traveller(s) with a total budget of {budget}.
They are particularly interested in: {keywords}.

Suggest exactly 6 places worth checking out (cafés, restaurants, or sights).

Return ONLY valid JSON with this exact shape—no markdown or commentary:
[
  {{ "name": "<place name>",
     "category": "cafe | restaurant | sight",
     "short_desc": "<one‑sentence pitch>" }},
  …
]
""".strip()

# --- HELPERS -----------------------------------------------------------------

def call_gemini(prompt: str) -> str:
    """
    Call Gemini 2.0 Flash API and return the raw text reply.
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

def maps_search_url(query: str) -> str:
    """
    Create a shareable Google Maps search link from a free-text query.
    """
    return (
        "https://www.google.com/maps/search/"
        f"?api=1&query={urllib.parse.quote_plus(query)}"
    )

# --- ENDPOINTS ---------------------------------------------------------------

@app.route("/recommend", methods=["POST"])
def recommend():
    """
    Suggest 3 travel destinations using Gemini, with maps links added.
    """
    data = request.get_json(force=True)
    try:
        budget = int(data.get("budget", 0))
        travelers = int(data.get("travelers", 1))
        keywords = data.get("keywords", "")
    except (TypeError, ValueError):
        return jsonify(error="Invalid budget or travelers number"), 400

    prompt = f"""
You are an expert travel concierge. All prices are in GBP.
The user has £{budget} total for {travelers} traveller(s).
Must-haves / keywords: {keywords or 'none'}.

Reply ONLY with a valid JSON array, no markdown, no commentary:
[{{"name":"City, Country","lat":..,"lng":..,"description":"..","estimated_cost":..}},...]
Return 3 destinations inside budget.
""".strip()

    raw = None
    try:
        raw = call_gemini(prompt).strip()
        # Try direct JSON first, else extract first JSON block in output
        try:
            suggestions = json.loads(raw)
        except json.JSONDecodeError:
            block = re.search(r"\[.*\]", raw, re.S)
            if not block:
                raise ValueError("No JSON found in Gemini output")
            suggestions = json.loads(block.group(0))

        # Enrich each suggestion with a Google Maps URL
        for s in suggestions:
            if "lat" in s and "lng" in s:
                s["maps_url"] = (
                    f"https://www.google.com/maps/@{s['lat']},{s['lng']},12z"
                )
            else:
                s["maps_url"] = maps_search_url(s.get("name", ""))
        return jsonify(suggestions=suggestions)
    except Exception as err:
        logging.error("Gemini parsing error: %s\nRAW:\n%s", err, raw)
        return jsonify(error="AI response error"), 502

@app.route("/explore")
def explore():
    """
    Suggest 6 places in a city using Gemini (cafés, restaurants, sights).
    """
    city = request.args.get("city", "").strip()
    keywords = request.args.get("keywords", "").strip()
    budget = request.args.get("budget", "").strip()
    travelers = request.args.get("travelers", "1").strip()

    if not city:
        return jsonify(error="No city provided"), 400

    budget_str = f"£{budget}" if budget else "any budget"
    keywords_str = keywords if keywords else "general interests"

    prompt = EXPLORE_PROMPT.format(
        city=city,
        travelers=travelers,
        budget=budget_str,
        keywords=keywords_str,
    )

    raw = None
    try:
        raw = call_gemini(prompt).strip()
        match = re.search(r"\[.*\]", raw, re.S)
        if not match:
            raise ValueError("No JSON block found in Gemini output")
        places = json.loads(match.group(0))[:6]

        # Add maps_url for each place
        slim = [
            {
                "name": p.get("name", "Unnamed"),
                "category": p.get("category", "unknown"),
                "short_desc": p.get("short_desc", ""),
                "maps_url": maps_search_url(f"{p.get('name','')} {city}")
            }
            for p in places
        ]
        return jsonify(places=slim)
    except Exception as err:
        logging.error("Gemini parse error: %s\nRAW:\n%s", err, raw)
        return jsonify(error="AI response error"), 502

@app.route("/select", methods=["POST"])
def select():
    """
    NO-OP persistence placeholder for user's destination selection.
    """
    return ("", 204)

@app.route("/chat", methods=["POST"])
def chat():
    """
    General-purpose travel assistant chat (calls Gemini).
    """
    try:
        data = request.get_json(force=True)
        user_message = data.get("message", "").strip()
        if not user_message:
            return jsonify(reply="Please enter a message."), 400

        prompt = (
            "You are WanderWise, a friendly and knowledgeable travel assistant helping users plan trips.\n\n"
            "Your role is to:\n"
            "- Offer insightful and relevant travel advice or suggestions.\n"
            "- Answer travel-related questions clearly and helpfully.\n"
            "- Be conversational, warm, and professional.\n"
            "- Respond only in English.\n\n"
            f"User message:\n\"{user_message}\"\n\n"
            "Now craft a helpful and polite reply:"
        )
        reply = call_gemini(prompt).strip()
        return jsonify(reply=reply)
    except Exception as err:
        logging.error("Chat error: %s", err)
        return jsonify(reply="Error connecting to Gemini."), 500

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_public(path):
    """
    Serve static frontend files from ./public directory.
    """
    return send_from_directory(app.static_folder, path or "index.html")

# --- SERVER ENTRY ------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
