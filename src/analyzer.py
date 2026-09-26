import os
import json
import time

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

class SafeItem:
    """Wrapper ensuring 100% compatibility with Pydantic, dict, and history.py"""
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


def rule_based_fallback(item_dict: dict) -> dict:
    """Fallback classifier when AI quota is exhausted or model is unavailable"""
    title = item_dict.get("title", "").lower()
    summary = (item_dict.get("summary", "") or "").lower()
    text = f"{title} {summary}"

    category = "Diplomacy & Regional Affairs"
    score = 2

    # Category matching
    if any(k in text for k in ["f-35", "military", "defense", "centcom", "fmf", "iron dome", "security"]):
        category = "Strategic & Defense"
        score = 3
    elif any(k in text for k in ["congress", "senate", "house", "bill", "ndaa", "legislation", "resolution"]):
        category = "Capitol Hill & Legislation"
        score = 3
    elif any(k in text for k in ["antisemitism", "campus", "jewish", "synagogue", "jta", "forward", "title vi"]):
        category = "American Jewry & Civil Society"
        score = 3

    if any(k in text for k in ["veto", "sanctions", "strike", "war", "treaty", "hostage"]):
        score = 4

    return {
        **item_dict,
        "importance_score": score,
        "bluf": item_dict.get("title", ""),
        "strategic_implications": [
            "Tracked via automated intelligence rule-engine.",
            "Relevant to ongoing US-Israel policy monitoring."
        ],
        "category": category
    }


def analyze_items(items: list) -> list:
    api_key = os.environ.get("GEMINI_API_KEY")
    client = None

    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"GenAI client init skipped: {e}")

    analyzed_list = []
    ai_quota_available = bool(client)

    for item in items:
        base_dict = extract_dict(item)

        if ai_quota_available:
            try:
                from google.genai import types
                prompt = f"""
You are an expert foreign policy intelligence analyst specializing in US-Israel relations and American Jewry.
Analyze the following item and provide a structured assessment for a policy briefing:

Source: {base_dict.get('source')}
Title: {base_dict.get('title')}
Summary: {base_dict.get('summary')}

Respond ONLY with valid JSON:
{{
  "importance_score": <1 to 5>,
  "bluf": "<Bottom Line Up Front>",
  "strategic_implications": ["<point 1>", "<point 2>"],
  "category": "<'Strategic & Defense' | 'Diplomacy & Regional Affairs' | 'Capitol Hill & Legislation' | 'American Jewry & Civil Society'>"
}}
"""
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                data = json.loads(response.text)
                analyzed_list.append(SafeItem({**base_dict, **data}))
                time.sleep(15)
                continue
            except Exception as e:
                print(f"Switching to rule-based fallback due to: {e}")
                ai_quota_available = False  # מפסיק לנסות לקרוא ל-API אם המכסה נגמרה

        # שימוש במנוע החוקים אם ה-API נכשל או חרג ממכסה
        fallback_data = rule_based_fallback(base_dict)
        analyzed_list.append(SafeItem(fallback_data))

    return analyzed_list