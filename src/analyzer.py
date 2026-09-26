import os
import json
from google import genai
from google.genai import types

def analyze_article(client: genai.Client, item: dict) -> dict:
    title = item.get("title", "")
    summary = item.get("summary", "") or item.get("description", "")
    source = item.get("source", "Unknown")

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
        return {**item, **data}
    except Exception as e:
        print(f"Error analyzing '{title}': {e}")
        return {
            **item,
            "importance_score": 2,
            "bluf": title,
            "strategic_implications": ["Analysis temporarily unavailable."],
            "category": "Diplomacy & Regional Affairs"
        }

def analyze_items(items: list) -> list:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)
    analyzed_list = []

    for item in items:
        result = analyze_article(client, item)
        analyzed_list.append(result)

    return analyzed_list