import os
import json
import time
from google import genai
from google.genai import types

def analyze_article(client: genai.Client, item) -> None:
    # Safely extract text attributes from Pydantic object or dict
    title = getattr(item, "title", None) or (item.get("title", "") if isinstance(item, dict) else "")
    summary = (
        getattr(item, "summary", None) 
        or getattr(item, "description", None) 
        or (item.get("summary", "") or item.get("description", "") if isinstance(item, dict) else "")
    )
    source = getattr(item, "source", None) or (item.get("source", "Unknown") if isinstance(item, dict) else "Unknown")

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
            model='gemini-3.8-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        data = json.loads(response.text)
    except Exception as e:
        print(f"Error analyzing '{title}': {e}")
        data = {
            "importance_score": 2,
            "bluf": title,
            "strategic_implications": ["Analysis temporarily unavailable."],
            "category": "Diplomacy & Regional Affairs"
        }

    # Assign attributes directly to the object so history.py keeps url_hash intact
    for key, value in data.items():
        if hasattr(item, key):
            setattr(item, key, value)
        elif isinstance(item, dict):
            item[key] = value

def analyze_items(items: list) -> list:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)

    for item in items:
        analyze_article(client, item)
        time.sleep(4)

    return items