import streamlit as st
from utils.transcription import get_transcript
from utils.summarization import generate_summary
from utils.report_generator import create_text_report, create_pdf_report

# --- Page Configuration ---
st.set_page_config(
    page_title="Financial Video Summarizer",
    page_icon="📊",
    layout="wide"
)

# --- App Title and Description ---
st.title("📊 AI-Powered Financial Video Summarizer (Local & Private)")
st.markdown("""
    Enter a YouTube URL of an earnings call or investor presentation to generate a structured financial summary.
    This tool runs **100% locally**, using the open-source Ollama framework. Your data never leaves your computer.
""")

# --- Initialize Session State ---
if 'summary' not in st.session_state:
    st.session_state['summary'] = None
if 'transcript' not in st.session_state:
    st.session_state['transcript'] = None
if 'video_url' not in st.session_state:
    st.session_state['video_url'] = ""

# --- Input Section ---
with st.container(border=True):
    youtube_url = st.text_input("Enter YouTube URL:", placeholder="https://www.youtube.com/watch?v=...", key="youtube_url_input")
    analyze_button = st.button("Analyze Video", type="primary")

# --- Processing and Output ---
if analyze_button:
    st.session_state['video_url'] = youtube_url
    if st.session_state['video_url']:
        try:
            with st.spinner("Step 1/2: Retrieving and transcribing video... This may take a few minutes."):
                transcript = get_transcript(st.session_state['video_url'])
                st.session_state['transcript'] = transcript
            
            with st.spinner("Step 2/2: Generating financial summary with local AI..."):
                summary = generate_summary(transcript)
                st.session_state['summary'] = summary
        
        except ValueError as e:
            st.error(f"Input Error: {e}")
        except RuntimeError as e:
            st.error(f"Processing Error: {e}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
    else:
        st.warning("Please enter a YouTube URL.")

# --- Display Results ---
if st.session_state['summary']:
    st.success("Analysis Complete!")
    summary_data = st.session_state['summary']

    # --- Display Summary Sections ---
    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.subheader("📝 Executive Summary")
            st.markdown(summary_data.get("executive_summary", "Not available."))

        with st.container(border=True):
            st.subheader("📈 Key Financials")
            key_financials = summary_data.get("key_financials", {})
            if isinstance(key_financials, dict):
                for metric, value in key_financials.items():
                    st.markdown(f"**{metric}:** {value}")
            elif isinstance(key_financials, list):
                for item in key_financials:
                    st.markdown(f"**{item.get('metric', 'N/A')}:** {item.get('value', 'N/A')}")
                    st.caption(f"Commentary: {item.get('commentary', 'N/A')}")
            else:
                st.markdown("No key financials available.")
    
    with col2:
        with st.container(border=True):
            st.subheader("🎯 Strategic Initiatives")
            initiatives = summary_data.get("strategic_initiatives",)
            if initiatives:
                for initiative in initiatives:
                    st.markdown(f"- {initiative}")
            else:
                st.markdown("No specific initiatives mentioned.")

        with st.container(border=True):
            st.subheader("🔮 Outlook and Guidance")
            st.markdown(summary_data.get("outlook_and_guidance", "Not available."))

        with st.container(border=True):
            st.subheader("⚠️ Key Risks Mentioned")
            risks = summary_data.get("key_risks_mentioned",)
            if risks:
                for risk in risks:
                    st.markdown(f"- {risk}")
            else:
                st.markdown("No specific risks mentioned.")
    
    # --- Download Buttons ---
    st.subheader("Download Report")
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        # Prepare text report for download
        text_report = create_text_report(summary_data)
        st.download_button(
            label="Download as TXT",
            data=text_report,
            file_name="financial_summary.txt",
            mime="text/plain"
        )
    with dl_col2:
        # Prepare PDF report for download
        pdf_report = create_pdf_report(summary_data)
        st.download_button(
            label="Download as PDF",
            data=pdf_report,
            file_name="financial_summary.pdf",
            mime="application/pdf"
        )


    # --- Expander for Full Transcript and Raw JSON ---
    with st.expander("View Full Transcript and Raw JSON Output"):
        st.subheader("Full Transcript")
        st.text_area("Transcript", st.session_state['transcript'], height=300)
        
        st.subheader("Raw AI Output (JSON)")
        st.json(summary_data)