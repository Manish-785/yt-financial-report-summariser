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
from thefuzz import process,fuzz
from dotenv import load_dotenv
load_dotenv()

SIMILARITY_THRESHOLD = 80
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 👇 Add your YouTube channel IDs here
CHANNEL_IDS = [
    "UC3uJIdRFTGgLWrUziaHbzrg",
    "UCkXopQ3ubd-rnXnStZqCl2w",
    "UCQIycDaLsBpMKjOCeaKUYVg",
    "UCI_mwTKUhicNzFrhm33MzBQ",
    "UCmRbHAgG2k2vDUvb3xsEunQ",
]

VISITED_LOG = "visited_videos.json"

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

def load_company_data(filepath="accord_bse_mapping.xlsx"):
    """Loads the company data from the Excel file."""
    try:
        df = pd.read_excel(filepath)
        print(f"Successfully loaded {filepath}")
        
        # Create a searchable dataset with company names and their variations
        company_data = {}
        for _, row in df.iterrows():
            company_name = str(row['Company Name']).strip()
            if pd.notna(company_name) and company_name.lower() != 'nan':
                company_info = {
                    'company_name': company_name,
                    'accord_code': row.get('Accord Code', ''),
                    'bse_code': row.get('CD_BSE Code', ''),
                    'nse_symbol': row.get('CD_NSE Symbol', ''),
                    'isin': row.get('CD_ISIN No', ''),
                    'sector': row.get('CD_Sector', ''),
                    'industry': row.get('CD_Industry1', '')
                }
                # Store with original name as key
                company_data[company_name.lower()] = company_info
                
        return company_data
        
    except FileNotFoundError:
        print(f"Error: The file '{filepath}' was not found.")
        return {}
    except Exception as e:
        print(f"Error loading company data: {e}")
        return {}

COMPANY_DATA = load_company_data()

def extract_companies_with_gpt(title: str, api_key=None, model="gpt-5-mini", max_retries=3) -> list[str]:
    """
    Uses GPT to extract company names and their common aliases from the title.
    """
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set")
        return []
    
    prompt = f"""
You are a financial analyst tasked with identifying Indian company names from YouTube video titles.

Given this video title: "{title}"

Extract any Indian company names mentioned. Consider common abbreviations and aliases:
- HPCL = Hindustan Petroleum Corporation Limited
- ONGC = Oil and Natural Gas Corporation
- L&T = Larsen & Toubro
- TCS = Tata Consultancy Services
- HDFC = Housing Development Finance Corporation
- ICICI = Industrial Credit and Investment Corporation of India
- SBI = State Bank of India
- ITC = Indian Tobacco Company
- M&M = Mahindra & Mahindra
- HUL = Hindustan Unilever Limited
- RIL = Reliance Industries Limited
- Adani = Adani Group companies
- Tata = Tata Group companies
- Bajaj = Bajaj Group companies
- Maruti = Maruti Suzuki India Limited

IMPORTANT: Do NOT include news channels, media companies, or YouTube channel names such as:
- ZEE Business, ZEE News, ZEE TV
- CNBC, CNBC News, CNBC TV18
- ET Now, Economic Times
- Bloomberg, Reuters
- Moneycontrol
- Business Standard
- Times Now
- News18
- NDTV
- Any other news/media organizations

Return ONLY the full company names (not abbreviations) of actual Indian businesses/corporations that you can identify with high confidence.
If no Indian companies are mentioned, return an empty list.
Format your response as a JSON array of strings.

Example response: ["Reliance Industries Limited", "Tata Consultancy Services"]
"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise financial analyst. Only identify Indian companies you are confident about. Avoid hallucination."},
            {"role": "user", "content": prompt}
        ],
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            response_content = result["choices"][0]["message"]["content"].strip()
            
            # Parse JSON response
            companies = json.loads(response_content)
            return companies if isinstance(companies, list) else []
            
        except Exception as e:
            print(f"[GPT] Attempt {attempt + 1} failed: {e}")
            time.sleep(1)
    
    return []

def find_companies_in_data(gpt_companies: list[str]) -> list[dict]:
    """
    Matches GPT-extracted company names against the database using a more robust method.

    This function simplifies the matching logic:
    1. For each company name from GPT, generate a set of normalized variations (e.g., "Ltd", "Limited", etc.).
    2. Find the single best fuzzy match from the entire database against these variations.
    3. If this best match's score is above the confidence threshold, accept it.
    
    This avoids prematurely accepting a high-scoring incorrect match.
    """
    found_companies = []
    
    # --- Pre-normalization setup (run once) ---
    normalized_company_data = {}
    for original_key, info in COMPANY_DATA.items():
        normalized_key = re.sub(r'\s+', ' ', original_key.lower().strip().rstrip('.')).strip()
        if normalized_key:
            normalized_company_data[normalized_key] = info
    
    company_names_from_db_normalized = list(normalized_company_data.keys())

    # --- Main matching loop ---
    for gpt_company in gpt_companies:
        print(f"[MATCHING] Searching for: '{gpt_company}'")

        # --- Step 1: Generate all possible variations of the input name ---
        base_normalized = re.sub(r'\s+', ' ', gpt_company.lower().strip().rstrip('.')).strip()
        
        # Use a set to automatically handle duplicate variations
        candidates = {base_normalized}
        
        variations_to_try = [
            base_normalized.replace(" limited", " ltd"),
            base_normalized.replace(" ltd", " limited"),
            base_normalized.replace(" corporation", " corp"),
            base_normalized.replace(" corp", " corporation"),
            re.sub(r'\s+(limited|ltd|corporation|corp|private|pvt|india|group)$', '', base_normalized).strip(),
        ]
        
        for var in variations_to_try:
            clean_var = re.sub(r'\s+', ' ', var).strip()
            if clean_var and clean_var not in candidates:
                candidates.add(clean_var)
        
        print(f"  - Generated candidates: {list(candidates)}")

        # --- Step 2: Find the single best match across all candidates ---
        # We use process.extractOne with a more suitable scorer for this task.
        # fuzz.token_sort_ratio is good at ignoring differences like "Ltd" vs "Limited".
        best_match_result = process.extractOne(
            base_normalized,
            company_names_from_db_normalized,
            scorer=fuzz.token_sort_ratio, # Using a more robust scorer
            score_cutoff=SIMILARITY_THRESHOLD
        )
        
        # --- Step 3: Evaluate the best match found ---
        if best_match_result:
            matched_db_key, score = best_match_result
            matched_company_data = normalized_company_data[matched_db_key]
            
            print(f"  [SUCCESS] Best match found with score {score}: '{gpt_company}' -> '{matched_company_data['company_name']}'")
            found_companies.append(matched_company_data)
        else:
            print(f"  [NO MATCH] Could not find a match above threshold {SIMILARITY_THRESHOLD} for '{gpt_company}'")

    # --- Final deduplication ---
    unique_companies = {}
    for company in found_companies:
        isin = company.get('isin')
        if isin and isin not in unique_companies:
            unique_companies[isin] = company
            
    return list(unique_companies.values())

def test_title_extraction(title: str):
    """
    Test function to check company extraction from a given title.
    """
    print(f"Testing title: '{title}'")
    
    # Extract companies using GPT
    print("\n--- GPT Company Extraction ---")
    gpt_companies = extract_companies_with_gpt(title)
    print(f"GPT extracted companies: {gpt_companies}")
    
    if not gpt_companies:
        print("No companies found by GPT")
        return
    
    # Find companies in our Excel data
    print("\n--- Company Matching ---")
    companies_info = find_companies_in_data(gpt_companies)
    print(f"Matched companies in database: {len(companies_info)}")
    
    for company in companies_info:
        print(f"  - {company['company_name']} (ISIN: {company.get('isin', 'N/A')})")
    
    if not companies_info:
        print("No companies matched in database")

def log_company_growth(summary_data, companies_info, video_url, title):
    """
    Logs one row per company summarizing >30% growth mentions, with timestamped links.
    """
    growth_mentions = summary_data.get("growth_mentions", [])
    summary = summary_data.get("summary", {})

    if not growth_mentions:
        return

    metric_summaries = []
    context_snippets = []
    timestamp_links = []

    video_id = None
    try:
        from utils.transcription import extract_video_id
        video_id = extract_video_id(video_url)
    except Exception:
        pass

    for g in growth_mentions:
        val = g.get("growth_value", 0)
        if val <= 30:
            continue

        metric = g.get("metric", "Unknown")
        metric_summaries.append(f"{metric} ({val}%)")

        ctx = g.get("context", "").replace("\n", " ").strip()
        context_snippets.append(ctx)

        ts = g.get("timestamp_seconds", None)
        if ts and isinstance(ts, (int, float)) and video_id:
            timestamp_links.append(f"https://www.youtube.com/watch?v={video_id}&t={int(ts)}s")
        elif video_id:
            timestamp_links.append(video_url)  # fallback

    if not metric_summaries:
        return

    company_name = (
        companies_info[0].get('company_name', '') if companies_info
        else summary.get('company_name', '')
    )
    isin = (
        companies_info[0].get('isin', '') if companies_info
        else ''
    )

    log_path = "growth_mentions_llm.xlsx"

    if not os.path.exists(log_path):
        df = pd.DataFrame(columns=[
            "Company Name", "ISIN", "Metrics With >30% Growth",
            "Growth Details", "Timestamped Links", "Video URL", "Title"
        ])
        df.to_excel(log_path, index=False)

    df_existing = pd.read_excel(log_path)

    new_entry = {
        "Company Name": company_name,
        "ISIN": isin,
        "Metrics With >30% Growth": "; ".join(metric_summaries),
        "Growth Details": " | ".join(context_snippets),
        "Timestamped Links": "\n".join(timestamp_links),
        "Video URL": video_url,
        "Title": title
    }

    df_existing = pd.concat([df_existing, pd.DataFrame([new_entry])], ignore_index=True)
    df_existing.to_excel(log_path, index=False)

    print(f"✅ Logged growth summary for {company_name}: {len(metric_summaries)} metrics >30%")


def format_summary_for_slack(url, summary, channel_id, title, companies_info):
    # We expect `summary` to be a list of objects with keys: company_name, speaker, note
    lines = []
    lines.append(f"*Summary for channel:* `{channel_id}`\n<{url}>")
    lines.append(f"*Video Title:* {title}")

    if isinstance(summary, list) and summary:
        # Match summary entries to companies_info by company_name (fuzzy if needed)
        for entry in summary:
            cname = entry.get('company_name', '').strip()
            speaker = entry.get('speaker', '').strip()
            note = entry.get('note', '').strip()

            # Find ISIN from companies_info if available
            isin = ''
            for c in companies_info:
                if c.get('company_name') and cname.lower() == c.get('company_name').lower():
                    isin = c.get('isin', '')
                    break

            line = f"• {cname}"
            if isin:
                line += f" (ISIN: {isin})"
            if speaker:
                line += f" — {speaker}"
            if note:
                line += f" — {note}"

            lines.append(line)
    else:
        lines.append("No concise summaries available.")

    return "\n".join(lines)

def main():
    visited_videos = load_visited()
    while True:
        for channel_id in CHANNEL_IDS:
            videos = fetch_latest_videos(channel_id)
            for url, title in videos:
                if url in visited_videos:
                    continue

                # Use GPT to extract company names
                gpt_companies = extract_companies_with_gpt(title)
                if not gpt_companies:
                    print(f"Skipping (no companies found by GPT): {title}")
                    continue
                
                # Find companies in our Excel data
                companies_info = find_companies_in_data(gpt_companies)
                if not companies_info:
                    print(f"Skipping (no companies matched in database): {title}")
                    continue

                company_names = [info['company_name'] for info in companies_info]
                print(f"Processing: {title} ({url}) from channel {channel_id}, Companies: {company_names}")
                
                try:
                    transcript = get_transcript(url)
                    summary = generate_summary(transcript)
                    
                    # Log all >30% growth mentions (if any)
                    try:
                        # Loop through all company summaries
                        for entry in summary:
                            if "growth_mentions" in entry and entry["growth_mentions"]:
                                log_company_growth(entry, companies_info, url, title)
                    except Exception as e:
                        print(f"⚠️ Error logging growth data: {e}")

                    summary_text = format_summary_for_slack(url, summary, channel_id, title, companies_info)
                    send_to_slack(summary_text)
                    visited_videos.add(url)
                except Exception as e:
                    print(f"Error processing {url}: {e}")
                    continue
                    
        save_visited(visited_videos)
        time.sleep(600)  # Wait 10 minutes before checking again

if __name__ == "__main__":
    main()        