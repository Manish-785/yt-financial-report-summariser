from fpdf import FPDF

def create_text_report(summary_data: dict) -> str:
    """Formats the summary dictionary into a string for TXT download."""
    report = []
    report.append("AI-Generated Financial Summary\n")
    report.append("="*30 + "\n")

    report.append("Executive Summary\n")
    report.append("-" * 20)
    report.append(summary_data.get("executive_summary", "N/A") + "\n")

    report.append("Key Financials\n")
    report.append("-" * 20)
    key_financials = summary_data.get("key_financials", {})
    if isinstance(key_financials, dict):
        for metric, value in key_financials.items():
            report.append(f"- {metric}: {value}")
    elif isinstance(key_financials, list):
        for item in key_financials:
            if isinstance(item, dict):
                report.append(f"- {item.get('metric', 'N/A')}: {item.get('value', 'N/A')}")
                report.append(f"  Commentary: {item.get('commentary', 'N/A')}")
            else:
                report.append(f"- {str(item)}")
    else:
        report.append("No key financials available.")
    report.append("\n")

    report.append("Strategic Initiatives\n")
    report.append("-" * 20)
    for item in summary_data.get("strategic_initiatives", []):
        report.append(f"- {str(item)}")
    report.append("\n")

    report.append("Outlook and Guidance\n")
    report.append("-" * 20)
    report.append(summary_data.get("outlook_and_guidance", "N/A") + "\n")

    report.append("Key Risks Mentioned\n")
    report.append("-" * 20)
    for item in summary_data.get("key_risks_mentioned", []):
        report.append(f"- {str(item)}")
    
    return "\n".join(report)

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'AI-Generated Financial Summary', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(5)

    def chapter_body(self, body):
        self.set_font('Arial', '', 12)
        # Avoid empty or whitespace-only strings
        if not body or not str(body).strip():
            body = "N/A"
        self.multi_cell(0, 10, str(body).encode('latin-1', 'replace').decode('latin-1'))
        self.ln()

    def chapter_list(self, items):
        self.set_font('Arial', '', 12)
        for item in items:
            text = f'- {item}' if not isinstance(item, dict) else f"- {item.get('metric', 'N/A')}: {item.get('value', 'N/A')}"
            # Avoid empty or whitespace-only strings
            if not text.strip() or text == "-":
                continue
            self.multi_cell(0, 10, text.encode('latin-1', 'replace').decode('latin-1'))
        self.ln()

def create_pdf_report(summary_data: dict) -> bytes:
    """Generates a formatted PDF report from the summary data."""
    pdf = PDF()
    pdf.add_page()

    # Executive Summary
    pdf.chapter_title("Executive Summary")
    pdf.chapter_body(summary_data.get("executive_summary", "N/A"))

    # Key Financials
    pdf.chapter_title("Key Financials")
    key_financials = summary_data.get("key_financials", {})
    if isinstance(key_financials, dict):
        for metric, value in key_financials.items():
            pdf.chapter_body(f"- {metric}: {value}")
    elif isinstance(key_financials, list):
        for item in key_financials:
            if isinstance(item, dict):
                metric = f"{item.get('metric', 'N/A')}: {item.get('value', 'N/A')}"
                commentary = f"Commentary: {item.get('commentary', 'N/A')}"
                pdf.chapter_body(f"- {metric}\n  {commentary}")
            else:
                pdf.chapter_body(f"- {str(item)}")
    else:
        pdf.chapter_body("No key financials available.")

    # Strategic Initiatives
    pdf.chapter_title("Strategic Initiatives")
    initiatives = summary_data.get("strategic_initiatives", [])
    if initiatives:
        pdf.chapter_list(initiatives)
    else:
        pdf.chapter_body("N/A")

    # Outlook and Guidance
    pdf.chapter_title("Outlook and Guidance")
    pdf.chapter_body(summary_data.get("outlook_and_guidance", "N/A"))

    # Key Risks Mentioned
    pdf.chapter_title("Key Risks Mentioned")
    risks = summary_data.get("key_risks_mentioned", [])
    if risks:
        pdf.chapter_list(risks)
    else:
        pdf.chapter_body("N/A")

    return bytes(pdf.output())