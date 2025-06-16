"""
WanderWise – lightweight Flask backend
--------------------------------------
Routes:
• /recommend  → Gemini: suggest 3 destinations in GBP for given budget/travellers/keywords
• /explore    → Google Places: cafés, restaurants & sights for a city
• /select     → NO-OP (would normally persist the user’s choice)
• /chat       → Gemini: general-purpose travel assistant chat
• static files served from ./public
"""

import os
import json
import requests
import re
import logging
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

# --- CONFIG & ENVIRONMENT ----------------------------------------------------

load_dotenv()
GEMINI_KEY = os.environ.get("GEMINI_KEY")
PLACES_KEY = os.environ.get("PLACES_KEY")

PUBLIC_DIR = "public"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
)

# --- FLASK APP INIT ----------------------------------------------------------

app = Flask(__name__, static_folder=PUBLIC_DIR)

# --- OPTIONAL: Enable CORS if frontend is on different port/domain -----------

try:
    from flask_cors import CORS
    CORS(app)
except ImportError:
    pass  # If CORS not installed, ignore

# --- GEMINI API HELPER -------------------------------------------------------

def call_gemini(prompt: str) -> str:
    """
    Call Gemini 2.0 Flash and return the raw text reply.
    """
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    response = requests.post(url, headers=headers, json=body, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

# --- ENDPOINT: /recommend ----------------------------------------------------

@app.route("/recommend", methods=["POST"])
def recommend():
    """
    Suggest 3 travel destinations based on user's budget, traveler count, and keywords.
    Returns a JSON array of destination objects.
    """
    data = request.get_json(force=True)
    try:
        budget = int(data.get("budget", 0))
        travelers = int(data.get("travelers", 1))
    except (TypeError, ValueError):
        return jsonify(error="Invalid budget or travelers number"), 400

    keywords = data.get("keywords", "").strip()

    prompt = (
        "You are an expert travel concierge. All prices are in GBP.\n"
        f"The user has £{budget} total for {travelers} traveller(s).\n"
        f"Must-haves / keywords: {keywords or 'none'}.\n\n"
        "Reply ONLY with a valid JSON array, no markdown, no commentary:\n"
        "[{\"name\":\"City, Country\",\"lat\":..,\"lng\":..,\"description\":\"..\",\"estimated_cost\":..},...]\n"
        "Return 3 destinations inside budget."
    )

    raw = None
    try:
        raw = call_gemini(prompt).strip()
        try:
            suggestions = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON array if Gemini returns surrounding text
            block = re.search(r"\[.*\]", raw, re.S)
            if not block:
                raise ValueError("No JSON found in Gemini output")
            suggestions = json.loads(block.group(0))

        if not isinstance(suggestions, list):
            raise ValueError("Parsed Gemini data is not a list.")

        return jsonify(suggestions=suggestions)

    except Exception as err:
        logging.error("Gemini parsing error: %s\nRAW: %r", err, raw)
        return jsonify(error="AI response error"), 502

# --- ENDPOINT: /explore ------------------------------------------------------

@app.route("/explore")
def explore():
    """
    Return 6 cafés/restaurants/sights for a given city using Google Places API.
    """
    city = request.args.get("city", "").strip()
    if not city:
        return jsonify(error="No city provided"), 400

    query = f"top cafés or restaurants or tourist attractions in {city}"
    url = (
        "https://maps.googleapis.com/maps/api/place/textsearch/json"
        f"?key={PLACES_KEY}&query={requests.utils.quote(query)}"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])[:6]
        slim = [
            {"name": p.get("name", ""), "place_id": p.get("place_id", "")}
            for p in results if p.get("name") and p.get("place_id")
        ]
        return jsonify(places=slim)
    except Exception as err:
        logging.error("Google Places error: %s", err)
        return jsonify(error="Places lookup failed"), 502

# --- ENDPOINT: /select -------------------------------------------------------

@app.route("/select", methods=["POST"])
def select():
    """
    Simulated save (NO-OP) for user's destination selection.
    """
    return ("", 204)

# --- ENDPOINT: /chat ---------------------------------------------------------

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

# --- STATIC FRONTEND ---------------------------------------------------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_public(path):
    """
    Serve static frontend files from ./public directory.
    """
    return send_from_directory(app.static_folder, path or "index.html")

# --- MAIN SERVER ENTRY POINT -------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)
