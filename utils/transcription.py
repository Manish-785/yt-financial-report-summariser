import streamlit as st
import yt_dlp
import whisper
import os
import re
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled

def extract_video_id(url):
    """Extracts the YouTube video ID from a URL."""
    match = re.search(r"(?<=v=)[^&#]+", url)
    if not match:
        match = re.search(r"(?<=be/)[^&#]+", url)
    if match:
        return match.group(0)
    return None

@st.cache_data
def get_transcript(video_url: str) -> str:
    """
    Retrieves the transcript for a YouTube video using a hybrid approach.
    First, it tries the youtube_transcript_api. If that fails, it falls back
    to downloading the audio with yt-dlp and transcribing with Whisper.
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        raise ValueError("Invalid YouTube URL provided.")

    # --- Method 1: Try youtube_transcript_api (fast and cheap) ---
    try:
        # This is the updated, correct method call. It directly fetches the
        # transcript in the specified languages.
        ytt_api = YouTubeTranscriptApi()
        transcript_data = ytt_api.fetch(video_id, languages=['en'])
        transcript_text = " ".join([d['text'] for d in transcript_data])
        return transcript_text
    except TranscriptsDisabled:
        st.warning("Transcripts are disabled for this video. Falling back to audio transcription. This may take a few minutes.")
    except Exception as e:
        st.warning(f"Could not retrieve transcript with first method ({e}). Falling back to audio transcription.")

    # --- Method 2: Fallback to yt-dlp and Whisper (robust) ---
    try:
        audio_file = download_audio(video_url)
        
        # Load whisper model
        # Using the "base" model for a balance of speed and accuracy.
        # For higher accuracy, "small" or "medium" can be used, but they are slower.
        model = whisper.load_model("base")
        
        # Transcribe the audio
        result = model.transcribe(audio_file)
        transcript_text = result['text']
        
        # Clean up the downloaded audio file
        os.remove(audio_file)
        
        return transcript_text
    except Exception as e:
        raise RuntimeError(f"Failed to transcribe audio: {e}")

def download_audio(url: str) -> str:
    """Downloads the audio from a YouTube URL and returns the file path."""
    ydl_opts = {
        'format': '140',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': 'downloaded_audio.%(ext)s',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return "downloaded_audio.mp3"