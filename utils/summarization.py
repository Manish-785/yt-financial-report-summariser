import streamlit as st
import json
import os
import requests
import time
import logging
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from a .env file if present

logger = logging.getLogger(__name__)

FINANCIAL_ANALYST_PROMPT = """
You are an expert financial analyst from a top-tier investment bank. Your task is to analyze the following earnings call transcript and provide a structured summary in JSON format. Extract the key financial metrics, summarize management's discussion, and identify any forward-looking guidance or risk factors.

Transcript:
\"\"\"
{text}
\"\"\"

Provide your response as a single, valid JSON object with the following schema. Do not include any introductory text, apologies, or explanations outside of the JSON structure.
{{
  "executive_summary": "A concise, 3-5 sentence abstractive summary of the quarter.",
  "key_financials": {{}},
  "strategic_initiatives": [
    "A bullet point list of key strategies discussed, such as new product launches or market expansions."
  ],
  "outlook_and_guidance": "A summary of management's forecast for the upcoming quarter or full year.",
  "key_risks_mentioned": [
    "A bullet point list of any risks or headwinds mentioned, such as supply chain issues or competitive pressures."
  ]
}}
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
            time.sleep(5 * (attempt + 1))
    return None

@st.cache_data
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