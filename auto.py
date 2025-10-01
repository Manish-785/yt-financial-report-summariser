import os
import requests
import time
import json
import feedparser
import spacy
from utils.transcription import get_transcript
from utils.summarization import generate_summary
import pandas as pd
import re
from thefuzz import process

SIMILARITY_THRESHOLD = 85
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# 👇 Add your YouTube channel IDs here
CHANNEL_IDS = [
    "UC3uJIdRFTGgLWrUziaHbzrg",
    "UCkXopQ3ubd-rnXnStZqCl2w",
    "UCQIycDaLsBpMKjOCeaKUYVg",
    "UCI_mwTKUhicNzFrhm33MzBQ",
    "UCmRbHAgG2k2vDUvb3xsEunQ",
]

VISITED_LOG = "visited_videos.json"

# Load spaCy small English model
nlp = spacy.load("en_core_web_sm")


def fetch_latest_videos(channel_id, max_videos=3):
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id.strip()}"
    feed = feedparser.parse(rss_url)
    return [(entry.link, entry.title) for entry in feed.entries[:max_videos]]


def send_to_slack(text):
    if not SLACK_WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL not set")
        return
    payload = {"text": text}
    requests.post(SLACK_WEBHOOK_URL, json=payload)


def load_visited():
    if os.path.exists(VISITED_LOG):
        with open(VISITED_LOG, "r") as f:
            return set(json.load(f))
    return set()


def save_visited(visited):
    with open(VISITED_LOG, "w") as f:
        json.dump(list(visited), f)

def load_company_data(filepath="comp.csv"):
    """Loads the company names from the provided CSV file."""
    try:
        df = pd.read_csv(filepath)
        company_names = df['Company Name'].dropna().tolist()
        company_names_lower = [name.lower() for name in company_names]
        name_map = dict(zip(company_names_lower, company_names))
        return company_names_lower, name_map
    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        return [], {}
    except KeyError:
        print("Error: The CSV must have a column named 'Company Name'. Please check your file.")
        return [], {}

COMPANY_NAMES_LOWER, COMPANY_NAME_MAP = load_company_data()

FINANCIAL_STOP_WORDS = {
    "earnings", "report", "call", "guidance", "analysis", "stock", "stocks",
    "market", "quarter", "investing", "finance", "inc", "company", "corporation",
    "ltd", "limited", "industries"
}


def extract_company_names(title: str) -> list[str]:
    """
    Extracts Indian and international company names using Noun Chunks and fuzzy matching.
    """
    if not COMPANY_NAMES_LOWER:
        print("Company list is not loaded. Cannot extract names.")
        return []

    found_companies = set()
    doc = nlp(title)

    candidates = [chunk.text for chunk in doc.noun_chunks]
    
    # Use Fuzzy Matching for each candidate
    for candidate in candidates:
        candidate_lower = candidate.lower()

        # Simple filter for very short or irrelevant chunks
        if len(candidate_lower.split()) > 5 or len(candidate_lower) < 3:
            continue
            
        # Remove common stop words from the candidate to improve matching
        # e.g., "reliance industries stock" -> "reliance"
        filtered_candidate_parts = [word for word in candidate_lower.split() if word not in FINANCIAL_STOP_WORDS]
        if not filtered_candidate_parts:
            continue
        filtered_candidate = " ".join(filtered_candidate_parts)

        # Find the best match from our loaded list
        best_match = process.extractOne(filtered_candidate, COMPANY_NAMES_LOWER)

        # Apply the threshold
        if best_match and best_match[1] >= SIMILARITY_THRESHOLD:
            # We found a good match. Use the correctly cased name from our map.
            official_name = COMPANY_NAME_MAP[best_match[0]]
            found_companies.add(official_name)

    return list(found_companies)


def format_summary_for_slack(url, summary, channel_id, title, companies):
    lines = []
    lines.append(f"*Summary for channel:* `{channel_id}`\n<{url}>")
    lines.append(f"*Video Title:* {title}")
    
    if companies:
        lines.append(f"*Detected Companies:* {', '.join(companies)}\n")
    
    # Executive Summary - only add if exists and not empty
    exec_summary = summary.get('executive_summary')
    if exec_summary and exec_summary.strip() and exec_summary.lower() != 'n/a':
        lines.append(f"*Executive Summary:*\n{exec_summary}\n")

    # Key Financials - only add if exists and not empty
    key_financials = summary.get("key_financials", {})
    if key_financials and key_financials != {} and key_financials != "N/A":
        lines.append("*Key Financials:*")
        for section, details in key_financials.items():
            if details and details != "N/A":  # Skip empty/N/A details
                lines.append(f"• *{section.replace('_', ' ').title()}*")
                if isinstance(details, dict):
                    for k, v in details.items():
                        if v and v != "N/A":  # Skip empty/N/A values
                            lines.append(f"    - {k.replace('_', ' ').title()}: {v}")
                else:
                    lines.append(f"    - {details}")
        lines.append("")

    # Strategic Initiatives - only add if exists and not empty
    initiatives = summary.get("strategic_initiatives", [])
    if initiatives and initiatives != ["N/A"] and any(item for item in initiatives if item and item.strip()):
        lines.append("*Strategic Initiatives:*")
        for item in initiatives:
            if item and item.strip() and item.lower() != 'n/a':
                lines.append(f"• {item}")
        lines.append("")

    # Outlook and Guidance - only add if exists and not empty
    outlook = summary.get("outlook_and_guidance")
    if outlook and outlook.strip() and outlook.lower() != 'n/a':
        lines.append(f"*Outlook and Guidance:*\n{outlook}\n")

    # Key Risks - only add if exists and not empty
    risks = summary.get("key_risks_mentioned", [])
    if risks and risks != ["N/A"] and any(risk for risk in risks if risk and risk.strip()):
        lines.append("*Key Risks Mentioned:*")
        for risk in risks:
            if risk and risk.strip() and risk.lower() != 'n/a':
                lines.append(f"• {risk}")
        lines.append("")

    return "\n".join(lines)

def main():
    visited_videos = load_visited()
    while True:
        for channel_id in CHANNEL_IDS:
            videos = fetch_latest_videos(channel_id)
            for url, title in videos:
                if url in visited_videos:
                    continue

                companies = extract_company_names(title)
                if not companies:
                    print(f"Skipping (no company found): {title}")
                    continue

                print(f"Processing: {title} ({url}) from channel {channel_id}, Companies: {companies}")
                try:
                    transcript = get_transcript(url)
                    summary = generate_summary(transcript)
                    summary_text = format_summary_for_slack(url, summary, channel_id, title, companies)
                    send_to_slack(summary_text)
                    visited_videos.add(url)
                except Exception as e:
                    print(f"Error processing {url}: {e}")
                    continue
        save_visited(visited_videos)
        time.sleep(600)  # Wait 10 minutes before checking again


if __name__ == "__main__":
    main()
