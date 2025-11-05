import os
import json
import time
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL_2")
EXCEL_PATH = "growth_mentions_llm.xlsx"  # 👈 Change this to your Excel output path
LOG_SENT_PATH = "sent_summary_log.json"  # For deduplication


def send_to_slack(text):
    """Send formatted text message to Slack."""
    if not SLACK_WEBHOOK_URL:
        print("❌ SLACK_WEBHOOK_URL not set in .env")
        return
    payload = {"text": text}
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"Slack send failed: {e}")


def load_sent_log():
    """Load the set of previously sent entries."""
    if os.path.exists(LOG_SENT_PATH):
        try:
            with open(LOG_SENT_PATH, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_sent_log(sent):
    """Save sent entry IDs to JSON."""
    with open(LOG_SENT_PATH, "w") as f:
        json.dump(list(sent), f)


def build_message(row):
    """Format each Excel row for Slack output."""
    title = row.get("Title", "Untitled Video")
    video_url = row.get("Video URL", "")
    channel = row.get("Channel", "Unknown Channel")
    companies = row.get("Companies", "")
    summary = row.get("Summary", "")
    isin = row.get("ISIN", "")
    sector = row.get("Sector", "")

    lines = []
    lines.append(f"🎥 *<{video_url}|{title}>*")
    lines.append(f"📰 Channel: `{channel}`")

    if companies:
        lines.append(f"🏢 Companies: {companies}")
    if isin:
        lines.append(f"🔢 ISIN: `{isin}`")
    if sector:
        lines.append(f"🏭 Sector: {sector}")

    if summary:
        lines.append(f"> {summary}")

    return "\n".join(lines)


def send_summary_report():
    """Send new summary rows from Excel to Slack."""
    if not os.path.exists(EXCEL_PATH):
        print(f"❌ No Excel file found at {EXCEL_PATH}")
        return

    df = pd.read_excel(EXCEL_PATH)
    if df.empty:
        print("No entries in Excel.")
        return

    sent_log = load_sent_log()
    new_sent_log = set(sent_log)

    for idx, row in df.iterrows():
        unique_id = f"{row.get('Video URL', '')}_{row.get('Title', '')}"
        if unique_id in sent_log:
            continue

        msg = build_message(row)
        print(f"Sending to Slack: {row.get('Title')}")
        send_to_slack(msg)
        new_sent_log.add(unique_id)
        time.sleep(2)  # avoid rate limit

    save_sent_log(new_sent_log)
    print("✅ Summary report sent successfully.")


if __name__ == "__main__":
    send_summary_report()
