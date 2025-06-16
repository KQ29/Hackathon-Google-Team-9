from flask import Flask, request, jsonify, send_from_directory
import os
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='public')

# Load API keys
GEMINI_KEY = os.environ.get('GEMINI_KEY')
PLACES_KEY = os.environ.get('PLACES_KEY')
print(f"GEMINI_KEY set: {bool(GEMINI_KEY)}")
print(f"PLACES_KEY set: {bool(PLACES_KEY)}")

def call_gemini(prompt: str) -> str:
    """
    Uses Gemini 2.0 Flash to get a guided party planning suggestion.
    """
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    resp = requests.post(url, json=body, headers=headers)
    if not resp.ok:
        print("--- Gemini API ERROR ---")
        print("Status:", resp.status_code)
        print("Body:", resp.text)
        resp.raise_for_status()

    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '')
    print("Received chat request:", user_msg)
    try:
        # Prompt Gemini with planning guidance
        full_prompt = (
            f"The user provided this input: '{user_msg}'. "
            "You are a professional event planner. Based on the user's message, suggest a themed party idea. "
            "Give a short, enthusiastic paragraph describing the plan, including theme, suggested activities, and ideal venue type. "
            "At the end, include one search term to find a suitable venue in the format:\nVenueQuery: <search term>"
        )
        gemini_resp = call_gemini(full_prompt)

        # Extract response and venue query
        lines = gemini_resp.splitlines()
        venue_query = next((l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("venuequery:")), None)
        planning_text = gemini_resp.replace(f"VenueQuery: {venue_query}", '').strip()

        print("Gemini suggested:", planning_text)
        print("Query:", venue_query)

        # Google Places API
        venue = ""
        if venue_query:
            places_url = (
                f"https://maps.googleapis.com/maps/api/place/textsearch/json"
                f"?query={requests.utils.quote(venue_query)}&key={PLACES_KEY}"
            )
            places_res = requests.get(places_url)
            places_data = places_res.json()
            results = places_data.get('results', [])

            if results:
                top = results[0]
                venue = f"\n\nTop Venue Suggestion: *{top.get('name')}*, {top.get('formatted_address')}"

        reply = planning_text + venue if planning_text else "Sorry, no ideas right now."
        return jsonify({'reply': reply})
    except Exception as e:
        print("Error:", e)
        return jsonify({'reply': 'Sorry, something went wrong.'}), 500

# Serve static files from public/
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_public(path):
    return send_from_directory(app.static_folder, path or 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
