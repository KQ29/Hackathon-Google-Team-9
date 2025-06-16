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
    Uses Gemini 2.0 Flash to get plain text response.
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
        full_prompt = (
            f"User wants: '{user_msg}'. "
            "Suggest one party theme and a one-phrase venue search term in the format:\n"
            "Theme: <theme>\nVenueQuery: <search term>"
        )
        gemini_resp = call_gemini(full_prompt)

        # Extract theme and query
        lines = [line.strip() for line in gemini_resp.splitlines() if line.strip()]
        theme = next((l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("theme:")), None)
        query = next((l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("venuequery:")), None)
        print(f"Theme: {theme}, Query: {query}")

        if not theme or not query:
            raise ValueError("Invalid Gemini response")

        # Google Places API
        places_url = (
            f"https://maps.googleapis.com/maps/api/place/textsearch/json"
            f"?query={requests.utils.quote(query)}&key={PLACES_KEY}"
        )
        places_res = requests.get(places_url)
        places_data = places_res.json()
        results = places_data.get('results', [])

        # Prepare reply
        if not results:
            reply = f"I suggest a *{theme}* party, but couldn’t find a venue for '{query}'."
        else:
            top_place = results[0]
            venue = f"{top_place.get('name')}, {top_place.get('formatted_address')}"
            reply = f"How about a *{theme}* party? I found *{venue}* as a great spot."

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
