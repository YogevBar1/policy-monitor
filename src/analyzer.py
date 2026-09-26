import os
import json
import time
from google import genai
from google.genai import types

def analyze_article(client: genai.Client, item_dict: dict) -> dict:
    title = item_dict.get("title", "")
    summary = item_dict.get("summary", "") or item_dict.get("description", "")
    source = item_dict.get("source", "Unknown")

    prompt = f"""
You are an expert foreign policy intelligence analyst specializing in US-Israel relations and American Jewry.
Analyze the following item and provide a structured assessment for a policy briefing:

Source: {source}
Title: {title}
Summary/Content: {summary}

Respond ONLY with a valid JSON object matching this schema:
{{
  "importance_score": <Integer from 1 to 5, where 5 is critical strategic shift and 1 is routine>,
  "bluf": "<One crisp, objective sentence stating the Bottom Line Up Front>",
  "strategic_implications": [
    "<Implication 1 for Israel or American Jewry>",
    "<Implication 2 for Israel or American Jewry>"
  ],
  "category": "<Must be exactly one of: 'Strategic & Defense', 'Diplomacy & Regional Affairs', 'Capitol Hill & Legislation', 'American Jewry & Civil Society'>"
}}
"""
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
        return {**item_dict, **data}
    except Exception as e:
        print(f"Skipping AI enrichment for '{title}' due to API status: {e}")
        return {
            **item_dict,
            "importance_score": 2,
            "bluf": title,
            "strategic_implications": ["Automated policy tracking update."],
            "category": "Diplomacy & Regional Affairs"
        }

class SafeItem:
    """Wrapper ensuring compatibility with Pydantic, dictionary access, and history.py"""
    def __init__(self, data: dict):
        self._data = dict(data)
        for k, v in self._data.items():
            setattr(self, k, v)

    def to_dict(self):
        return self._data

    def model_dump(self):
        return self._data

    def dict(self):
        return self._data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data


def extract_dict(item) -> dict:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if hasattr(item, "dict"):
        return item.dict()
    if isinstance(item, dict):
        return dict(item)
    return {
        "title": getattr(item, "title", ""),
        "summary": getattr(item, "summary", "") or getattr(item, "description", ""),
        "source": getattr(item, "source", "Unknown"),
        "url": getattr(item, "url", getattr(item, "link", "")),
        "url_hash": getattr(item, "url_hash", ""),
        "published": getattr(item, "published", "")
    }


def analyze_items(items: list) -> list:
    api_key = os.environ.get("GEMINI_API_KEY")
    client = None
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"Could not initialize Gemini Client: {e}")

    analyzed_list = []
    
    # כדי לא לחרוג ממגבלת 5 בקשות בדקה של גוגל:
    # מנתחים עד 4 כתבות ראשונות עם השהיה של 15 שניות, ואת השאר מכניסים עם ערכי ברירת מחדל
    max_ai_calls = 4
    processed_count = 0

    for item in items:
        base_dict = extract_dict(item)

        if client and processed_count < max_ai_calls:
            enriched = analyze_article(client, base_dict)
            analyzed_list.append(SafeItem(enriched))
            processed_count += 1
            time.sleep(15)  # מרווח של 15 שניות מבטיח מקסימום 4 בקשות בדקה
        else:
            # ערכי ברירת מחדל לשאר הכתבות כדי לא לקרוס ולא לחרוג ממכסה
            default_dict = {
                **base_dict,
                "importance_score": 1,
                "bluf": base_dict.get("title", ""),
                "strategic_implications": ["Monitored open-source update."],
                "category": "Diplomacy & Regional Affairs"
            }
            analyzed_list.append(SafeItem(default_dict))

    return analyzed_list