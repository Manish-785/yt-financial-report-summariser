import json
import os
import requests
import time
import logging
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from a .env file if present

logger = logging.getLogger(__name__)

FINANCIAL_ANALYST_PROMPT = """
You are an expert financial analyst. Given the following transcript, identify every company mentioned and for each company return a concise JSON object with three fields: `company_name`, `speaker` and `note`.

Requirements:
- `company_name`: Full official company name as mentioned in the transcript (one string).
- `speaker`: a short string with "Name / Designation" of the person speaking about the company (use the best available name and title from the transcript; if unknown use an empty string).
- `note`: one short sentence (max 25 words) summarizing what the speaker said about industry growth or the company's outlook (forward-looking comment). If no outlook/growth comment exists, return an empty string.

Transcript:
\"\"\"
{text}
\"\"\"

 - Detect all mentions of >30% growth in any key metric (revenue, profit, EBITDA, margins, etc.).
 - For each growth mention, if possible, include the approximate **minute mark** in the call 
   (based on textual cues like “earlier”, “later in the call”, or segment order).
   If not inferable, set timestamp_seconds = null.
   
Return ONLY a JSON array of objects, each object exactly with the keys: `company_name`, `speaker`, `note`.
Do NOT include any explanatory text, markdown, or extra fields. Example:
[
    {
        "company_name": "Hindustan Petroleum Corporation Limited",
        "speaker": "Vikas Sharma / CFO",
        "note": "Management expects gradual margin recovery over the next two quarters."
        "growth_mentions": [
            {
            "metric": "Revenue",
            "growth_value": 42,
            "context": "Revenue grew 42% YoY driven by retail and BFSI segments.",
            "timestamp_seconds": 480, 
            "type": "YoY",
            "reliability": "High"
            }
        ]
    }
]
"""

def summarise_with_gpt(text, PROMPT_TEMPLATE, api_key=None, model="gpt-5-mini", max_retries=3):
    """
    Summarize text using OpenAI GPT API.
    """
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        return None

    prompt = PROMPT_TEMPLATE.format(text=text)

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"[GPT] Attempt {attempt + 1} failed: {e}")
            time.sleep(5)
    return None


def generate_summary(transcript: str, api_key=None) -> dict:
    """
    Generates a financial summary using OpenAI GPT API.
    """
    try:
        response_content = summarise_with_gpt(
            transcript,
            FINANCIAL_ANALYST_PROMPT,
            api_key=api_key,
            model="gpt-5-mini"
        )
        if not response_content:
            raise RuntimeError("No response from OpenAI API.")
        summary_json = json.loads(response_content)
        return summary_json
    except Exception as e:
        raise RuntimeError(f"Error generating summary: {e}")