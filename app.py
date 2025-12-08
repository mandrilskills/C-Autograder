# App.py
import streamlit as st
import json
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from grader_langgraph import run_grader_pipeline
from config import WEIGHT_FUNCTIONAL, WEIGHT_STATIC, WEIGHT_PERF

st.set_page_config(page_title="C Autograder (Dev)", layout="wide")

st.title("C Autograder — Development Mode")
st.write("Paste your C code below and run the local grading pipeline. (Dev-mode: runs gcc/cppcheck if installed.)")

code_input = st.text_area("C Source Code", height=300, value="""#include <stdio.h>
int main() {
    int x;
    if (scanf("%d", &x) == 1) {
        printf("%d", x);
    }
    return 0;
}
""")

col1, col2 = st.columns([3,1])
with col2:
    if st.button("Run Agentic Autograder"):
        with st.spinner("Running pipeline..."):
            results = run_grader_pipeline(code_input)
        st.session_state["results"] = results

results = st.session_state.get("results", None)
if results:
    st.subheader("Summary")
    final_score = results.get("final_score", 0.0)
    try:
        final_score_f = float(final_score)
    except Exception:
        final_score_f = 0.0
    st.metric("Final Agentic Score", f"{final_score_f*100:.1f} / 100")

    # Show scoring rubric and earned marks
    st.subheader("Scoring Rubric")
    st.markdown(f"- **Functional (weight: {WEIGHT_FUNCTIONAL:.2f})** — earned: **{results.get('scores_breakdown',{}).get('functional',0.0):.2f}**")
    st.markdown(f"- **Static (weight: {WEIGHT_STATIC:.2f})** — earned: **{results.get('scores_breakdown',{}).get('static',0.0):.2f}**")
    st.markdown(f"- **Performance (weight: {WEIGHT_PERF:.2f})** — earned: **{results.get('scores_breakdown',{}).get('perf',0.0):.2f}**")
    st.markdown(f"- **Final (weighted)** — **{results.get('final_score',0.0):.4f} / 1.0** ({results.get('final_score',0.0)*100:.1f}/100)")

    st.subheader("Detailed Report (bullet points)")

    # Compilation section
    st.markdown("### Compilation")
    compile_info = results.get("compile_info", {})
    comp_lines = []
    comp_status = compile_info.get("status", "unknown")
    comp_lines.append(f"Status: **{comp_status}**")
    if "returncode" in compile_info:
        comp_lines.append(f"Return code: {compile_info.get('returncode')}")
    stderr_preview = compile_info.get("stderr", "")
    if stderr_preview:
        # show only first few lines
        preview = "\n".join(stderr_preview.splitlines()[:8])
        comp_lines.append("Stderr (preview):")
        comp_lines.extend([f"- {line}" for line in preview.splitlines()])

    for line in comp_lines:
        st.markdown(f"- {line}")

    # Static analysis
    st.markdown("### Static Analysis (cppcheck)")
    static_info = results.get("static_info", {})
    if static_info:
        issues = static_info.get("issues", [])
        if issues:
            st.markdown(f"- Issues found: {len(issues)}")
            for i, it in enumerate(issues[:10], start=1):
                st.markdown(f"  - {it}")
        else:
            st.markdown("- No issues reported by cppcheck (or cppcheck not installed).")
    else:
        st.markdown("- No static analysis information available.")

    # Tests
    st.markdown("### Tests (Functional)")
    test_info = results.get("test_info", {})
    total = test_info.get("total_count", 0)
    passed = test_info.get("passed_count", 0)
    st.markdown(f"- Tests run: **{total}**, Passed: **{passed}**")
    for tr in test_info.get("test_results", []):
        inp = tr.get("input", "")
        expected = tr.get("expected", "")
        actual = tr.get("actual", "")
        passed_flag = tr.get("passed", False)
        timeout = tr.get("timeout", False)
        st.markdown(f"- Input: `{inp.strip()}` — Expected: `{expected.strip()}` — Actual: `{str(actual).strip()}` — Passed: **{passed_flag}**{' (timeout)' if timeout else ''}")

    # Performance
    st.markdown("### Performance")
    perf_info = results.get("perf_info", {})
    avg = perf_info.get("average_s", None)
    if avg is not None:
        st.markdown(f"- Average runtime (s): **{avg:.4f}**")
        st.markdown(f"- Individual timings: {', '.join([f'{t:.4f}s' for t in perf_info.get('timings', [])])}")
    else:
        st.markdown("- Performance not measured (compilation failed or no runs).")

    # Final reviewer comments
    st.subheader("Reviewer Comments")
    final_report = results.get("final_report", {})
    comments = final_report.get("comments", [])
    for c in comments:
        st.markdown(f"- {c}")

    # JSON dump toggle
    st.subheader("Raw JSON (for debugging)")
    st.json(results)

    # PDF export
    def build_pdf(report_data: dict) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        Story = []

        # Title
        Story.append(Paragraph("C Autograder Report", styles['Title']))
        Story.append(Spacer(1, 12))

        # Score safely formatted
        final_score_v = report_data.get('final_score', 0.0)
        try:
            final_score_f = float(final_score_v)
            score_text = f"{final_score_f:.4f}"
        except Exception:
            score_text = "N/A"
        Story.append(Paragraph(f"<b>Final Score (weighted):</b> {score_text} / 1.0", styles['Normal']))
        Story.append(Spacer(1, 12))

        # Sections as bullet lists (Compilation, Static, Tests, Performance)
        Story.append(Paragraph("<b>Compilation</b>", styles['Heading3']))
        ci = report_data.get("compile_info", {})
        Story.append(Paragraph(f"Status: {ci.get('status','unknown')}", styles['Normal']))
        if ci.get("stderr"):
            st_preview = "\n".join(ci.get("stderr", "").splitlines()[:10])
            Story.append(Paragraph("Stderr preview:", styles['Normal']))
            Story.append(Paragraph(st_preview.replace('\n', '<br/>'), styles['Code'] if 'Code' in styles else styles['Normal']))
        Story.append(Spacer(1,6))

        Story.append(Paragraph("<b>Static Analysis</b>", styles['Heading3']))
        si = report_data.get("static_info", {})
        errs = si.get("errors", 0)
        Story.append(Paragraph(f"Issues found: {errs}", styles['Normal']))
        Story.append(Spacer(1,6))

        Story.append(Paragraph("<b>Tests (Functional)</b>", styles['Heading3']))
        ti = report_data.get("test_info", {})
        Story.append(Paragraph(f"Passed {ti.get('passed_count',0)} / {ti.get('total_count',0)} tests", styles['Normal']))
        Story.append(Spacer(1,6))

        Story.append(Paragraph("<b>Performance</b>", styles['Heading3']))
        pi = report_data.get("perf_info", {})
        if pi.get("average_s") is not None:
            Story.append(Paragraph(f"Average runtime (s): {pi.get('average_s'):.4f}", styles['Normal']))
        else:
            Story.append(Paragraph("Not measured", styles['Normal']))
        Story.append(Spacer(1,12))

        # Scoring rubric
        Story.append(Paragraph("<b>Scoring Rubric</b>", styles['Heading3']))
        Story.append(Paragraph(f"- Functional weight: {WEIGHT_FUNCTIONAL:.2f}", styles['Normal']))
        Story.append(Paragraph(f"- Static weight: {WEIGHT_STATIC:.2f}", styles['Normal']))
        Story.append(Paragraph(f"- Performance weight: {WEIGHT_PERF:.2f}", styles['Normal']))
        Story.append(Spacer(1,6))

        doc.build(Story)
        pdf = buf.getvalue()
        buf.close()
        return pdf

    pdf_bytes = build_pdf(results)
    st.download_button("Download PDF report", data=pdf_bytes, file_name="autograder_report.pdf", mime="application/pdf")
else:
    st.info("Run the grader to see results here.")
