from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
import json
import io

# === Initialize Gemini Model ===
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)

# === Test Case Generation ===
def generate_test_cases(source_code: str):
    prompt = PromptTemplate.from_template("""
    You are an expert C programmer. Analyze the C program below and 
    generate 5 practical test cases that fully validate its correctness.
    Output a pure JSON list like:
    [{"input": "...", "expected_output": "..."}, ...]
    Code:
    ```c
    {source_code}
    ```
    """)
    resp = llm.invoke(prompt.format(source_code=source_code))
    return resp.content

# === Detailed Report Generation ===
def generate_detailed_report(feedback_obj: dict):
    prompt = PromptTemplate.from_template("""
    You are an expert AI reviewer. Based on this structured feedback, 
    write a detailed paragraph-style report including:
    - Overall evaluation summary
    - Compilation outcome
    - Logic & test performance analysis
    - Static code issues
    - Performance feedback
    - Final suggestions for improvement.
    Feedback JSON:
    {feedback_obj}
    """)
    resp = llm.invoke(prompt.format(feedback_obj=str(feedback_obj)))
    return resp.content

# === PDF Report Creation ===
def create_pdf_report(feedback_obj: dict, ai_report: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("C Code Autograder – AI Evaluation Report", styles["Title"]))
    story.append(Spacer(1, 12))

    # Final score
    story.append(Paragraph(f"Final Score: {feedback_obj.get('final_score', 0)}%", styles["Heading2"]))
    story.append(Spacer(1, 12))

    # Table of section results
    data = [["Section", "Score", "Summary"]]
    for sec in feedback_obj["sections"]:
        data.append([sec["section"], f"{sec['score']}%", sec["text"][:100] + "..."])
    table = Table(data, colWidths=[120, 60, 320])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))
    story.append(table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("AI Generated Detailed Analysis", styles["Heading2"]))
    story.append(Paragraph(ai_report, styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Conclusion", styles["Heading2"]))
    story.append(Paragraph(feedback_obj.get("conclusion", ""), styles["Normal"]))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf
