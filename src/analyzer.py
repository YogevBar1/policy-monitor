import os
import json
from google import genai
from google.genai import types

def analyze_article(title: str, summary: str, source: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)

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
        return json.loads(response.text)
    except Exception as e:
        print(f"Error analyzing with Gemini: {e}")
        return {
            "importance_score": 1,
            "bluf": title,
            "strategic_implications": ["Analysis unavailable."],
            "category": "Diplomacy & Regional Affairs"
        }