import re
import json
from io import BytesIO
import requests
from collections import Counter
from datetime import datetime

import streamlit as st
from gtts import gTTS
import google.generativeai as genai

from pipeline import (
    run_pipeline,
    evaluate_quiz_answers,
    generate_word_report,
    generate_powerpoint_deck,
    generate_pdf_report,
    find_reference_images_cached,
)


st.set_page_config(
    page_title="Agent ARCA",
    page_icon="🤖",
    layout="wide",
)


st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 1180px;
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
    }

    div[data-testid="stVerticalBlock"] {
        gap: 0.45rem;
    }

    .arca-hero {
        padding: 1rem 1.2rem;
        border: 1px solid rgba(120,120,120,0.25);
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(120,120,255,0.08), rgba(120,255,220,0.05));
        margin-bottom: 0.65rem;
    }

    .arca-title {
        font-size: 2rem;
        font-weight: 750;
        margin-bottom: 0.15rem;
    }

    .arca-subtitle {
        color: rgba(150,150,150,0.95);
        font-size: 1rem;
    }

    .arca-card {
        padding: 0.85rem 1rem;
        border: 1px solid rgba(120,120,120,0.22);
        border-radius: 16px;
        background: rgba(250,250,250,0.03);
        min-height: 95px;
    }

    .arca-card-title {
        font-weight: 700;
        font-size: 1rem;
        margin-bottom: 0.25rem;
    }

    .arca-card-text {
        color: rgba(150,150,150,0.95);
        font-size: 0.9rem;
    }

    .arca-badge {
        display: inline-block;
        padding: 0.2rem 0.55rem;
        border-radius: 999px;
        border: 1px solid rgba(120,120,120,0.22);
        background: rgba(120,120,120,0.08);
        font-size: 0.8rem;
        margin-right: 0.35rem;
        margin-bottom: 0.25rem;
    }

    .answer-card {
        padding: 1rem 1.1rem;
        border: 1px solid rgba(120,120,120,0.22);
        border-radius: 18px;
        background: rgba(250,250,250,0.035);
        margin-top: 0.4rem;
    }

    .input-wrap {
        padding: 0.55rem 0;
        margin-top: 0.3rem;
    }

    .small-muted {
        color: rgba(150,150,150,0.95);
        font-size: 0.86rem;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.75rem;
    }

    .stTabs [data-baseweb="tab"] {
        height: 2.35rem;
        padding: 0 0.65rem;
    }

    h1, h2, h3 {
        margin-top: 0.25rem;
        margin-bottom: 0.35rem;
    }

    hr {
        margin-top: 0.7rem;
        margin-bottom: 0.7rem;
    }

    button[kind="secondary"] {
        border-radius: 12px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def make_clickable_source_markers(answer, sources):
    for i, src in enumerate(sources, start=1):
        url = src.get("url", "")
        marker = f"[Source {i}]"

        if url:
            answer = answer.replace(
                marker,
                f'<a href="{url}" target="_blank">{marker}</a>',
            )

    return answer


def clean_text_for_audio(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"\[Source\s+\d+\]", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]", r"\1", text)
    text = text.replace("*", "")
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()

    return text[:1200]


def create_audio_bytes(text):
    try:
        clean_text = clean_text_for_audio(text)

        if not clean_text:
            return None, "No readable text found for audio."

        audio_buffer = BytesIO()

        tts = gTTS(
            text=clean_text,
            lang="en",
            slow=False,
        )

        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)

        audio_bytes = audio_buffer.getvalue()

        if not audio_bytes:
            return None, "Generated audio was empty."

        return audio_bytes, None

    except Exception as e:
        return None, str(e)


def render_answer_audio_button(answer, key_prefix):
    if not answer:
        return

    safe_key_prefix = re.sub(r"[^a-zA-Z0-9_]", "_", str(key_prefix))
    audio_key = f"audio_bytes_{safe_key_prefix}"
    error_key = f"audio_error_{safe_key_prefix}"

    if st.button("🔊 Listen", key=f"listen_{safe_key_prefix}", use_container_width=False):
        with st.spinner("Creating audio..."):
            audio_bytes, error = create_audio_bytes(answer)

        if audio_bytes:
            st.session_state[audio_key] = audio_bytes
            st.session_state[error_key] = ""
        else:
            st.session_state[audio_key] = None
            st.session_state[error_key] = error or "Audio could not be generated."

    if st.session_state.get(audio_key):
        st.audio(
            st.session_state[audio_key],
            format="audio/mpeg",
        )

    if st.session_state.get(error_key):
        st.warning(f"Audio could not be generated: {st.session_state[error_key]}")


def extract_json_from_text(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)

        if match:
            return json.loads(match.group(0))

    except Exception:
        pass

    return None


def generate_learning_activity(answer):
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")

        if not api_key:
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")

        prompt = f"""
Create an interactive learning activity from this answer.

Return ONLY valid JSON. No markdown. No explanation.

JSON format:
{{
  "multiple_choice": [
    {{
      "question": "Question text",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "Why the correct answer is right"
    }}
  ],
  "flashcards": [
    {{
      "front": "Question or concept",
      "back": "Short answer"
    }}
  ],
  "revision_tips": [
    "Tip 1",
    "Tip 2",
    "Tip 3"
  ]
}}

Rules:
- Create 5 multiple-choice questions.
- Create 5 flashcards.
- Keep questions clear and beginner-friendly.
- Base everything only on the answer below.

Answer:
{answer}
""".strip()

        response = model.generate_content(prompt)
        text = getattr(response, "text", "").strip()

        data = extract_json_from_text(text)

        if not data:
            return None

        return data

    except Exception:
        return None


def transcribe_voice(audio_input):
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")

        if not api_key:
            return ""

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3-flash-preview")

        audio_bytes = audio_input.read()

        response = model.generate_content(
            [
                "Only transcribe the spoken words. Do not answer or explain.",
                {
                    "mime_type": "audio/wav",
                    "data": audio_bytes,
                },
            ]
        )

        return response.text.strip()

    except Exception as e:
        error_text = str(e)

        if (
            "429" in error_text
            or "quota" in error_text.lower()
            or "ResourceExhausted" in error_text
        ):
            st.warning("Voice quota reached. Type your question or try again later.")
        elif "403" in error_text or "leaked" in error_text.lower():
            st.warning("Gemini API key issue. Update your key in Streamlit secrets.")
        else:
            st.warning("Voice transcription failed. Please type your question.")

        return ""


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_image_bytes(image_url):
    try:
        response = requests.get(
            image_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            "image/jpeg",
        )

        if not content_type.startswith("image/"):
            return None, None

        return response.content, content_type

    except Exception:
        return None, None


def split_uploaded_files(uploaded_files):
    uploaded_pdfs = []
    uploaded_docs = []
    uploaded_ppts = []
    uploaded_images = []

    for file in uploaded_files or []:
        name = file.name.lower()

        if name.endswith(".pdf"):
            uploaded_pdfs.append(file)
        elif name.endswith(".docx"):
            uploaded_docs.append(file)
        elif name.endswith(".pptx"):
            uploaded_ppts.append(file)
        elif name.endswith((".png", ".jpg", ".jpeg")):
            uploaded_images.append(file)

    return uploaded_pdfs, uploaded_docs, uploaded_ppts, uploaded_images


def file_icon(file_name):
    name = file_name.lower()

    if name.endswith(".pdf"):
        return "📄"
    if name.endswith(".docx"):
        return "📝"
    if name.endswith(".pptx"):
        return "📊"
    if name.endswith((".png", ".jpg", ".jpeg")):
        return "🖼️"

    return "📎"


def show_attached_files(uploaded_files):
    if not uploaded_files:
        return

    with st.expander(f"Attached files ({len(uploaded_files)})", expanded=False):
        for file in uploaded_files:
            st.markdown(f"{file_icon(file.name)} **{file.name}**")


def build_style_instruction(output_style):
    if output_style == "Simple Summary":
        return "Answer as a simple, short summary. Use plain language and avoid unnecessary detail."
    if output_style == "Study Guide":
        return "Answer as a student study guide with concepts, examples, quick revision points, and a short quiz."
    if output_style == "Detailed Research":
        return "Answer as a detailed research synthesis with evidence, comparisons, limits, and next steps."
    if output_style == "Presentation Notes":
        return "Answer as presentation-ready notes with clear bullets, slide-friendly wording, and key takeaways."
    if output_style == "Decision Brief":
        return "Answer as a professional decision brief with recommendation, evidence, risks, and next actions."

    return "Answer clearly and use evidence from sources."


def is_vague_question(question):
    vague_phrases = {
        "what is this",
        "what's this",
        "what is it",
        "explain this",
        "explain it",
        "summarize this",
        "summarize it",
        "tell me about this",
        "what does this mean",
        "what are you",
        "what is arca",
        "what is agent arca",
    }

    cleaned = question.strip().lower().replace("?", "")

    return cleaned in vague_phrases


def build_about_arca_answer():
    return """
## Key Takeaway
Agent ARCA is an AI-powered research, learning, and decision-intelligence assistant.

## What Agent ARCA Does
Agent ARCA helps students and professionals turn scattered information into clear, useful outputs. You can upload files, paste links, use web research, ask questions, and generate summaries, study guides, reports, PowerPoint decks, and source-backed answers.

## What You Can Use It For
- Summarizing PDFs, Word documents, PowerPoint decks, screenshots, and images
- Understanding class notes, lecture material, or research topics
- Creating study guides and quiz questions
- Comparing sources and finding conflicts
- Generating presentation notes
- Creating professional research reports
- Reviewing source credibility and trust scores
- Exporting findings as Word, PDF, or PowerPoint files

## Modes
- Student Mode: explains concepts simply, creates quizzes, and helps with learning.
- General Mode: creates professional summaries, decision briefs, and research insights.

## Simple Summary
Agent ARCA is like a research assistant that reads your sources, explains them clearly, checks source quality, and helps you turn the result into study or work-ready outputs.

## Try Asking
- Summarize this file.
- Explain this topic like I am a beginner.
- Compare these sources.
- Make presentation notes.
- Create a study guide with quiz questions.
""".strip()


def prepare_effective_question(question, uploaded_files, urls):
    has_context = bool(uploaded_files) or bool(urls)

    if is_vague_question(question) and has_context:
        return f"""
The user asked: "{question}"

They are referring to the uploaded file(s), image(s), document(s), slide deck(s), or pasted URL(s).

Analyze the provided source content and explain:
1. What this content is about
2. The key points
3. Why it matters
4. A simple summary
5. Any important details the user should notice
""".strip()

    if is_vague_question(question) and not has_context:
        return "__ABOUT_ARCA__"

    return question


def show_inline_visual_reference(question):
    if not st.session_state.show_inline_image or not question:
        return

    with st.expander("🖼️ Add visual snapshot", expanded=False):
        if st.button("Find one visual", use_container_width=True):
            with st.spinner("Finding visual..."):
                images = find_reference_images_cached(
                    query=f"{question} educational diagram visual reference",
                    max_images=1,
                    prefer_trusted_sources=True,
                )

            if not images:
                st.info("No visual found.")
                return

            image = images[0]
            image_url = image.get("image_url", "")
            source_url = image.get("source_url", "")
            description = image.get("description", "Visual reference")

            if not image_url:
                st.info("No visual found.")
                return

            image_bytes, _ = fetch_image_bytes(image_url)

            if not image_bytes:
                st.info("Image preview unavailable.")
                st.markdown(f"[Open image]({image_url})")
                return

            st.image(
                image_bytes,
                caption=description,
                use_container_width=True,
            )

            cols = st.columns(2)

            with cols[0]:
                st.markdown(f"[Open image]({image_url})")

            with cols[1]:
                if source_url and source_url != image_url:
                    st.markdown(f"[Open source page]({source_url})")


def build_saved_research_markdown(saved_findings):
    content = "# Agent ARCA Saved Research Collection\n\n"

    if not saved_findings:
        return content + "No saved findings yet.\n"

    for i, item in enumerate(saved_findings, start=1):
        content += f"## Finding {i}: {item['question']}\n\n"
        content += f"**Mode:** {item['user_mode']}\n\n"
        content += f"**Analysis:** {item['analysis_mode']}\n\n"
        content += f"**Saved:** {item['timestamp']}\n\n"

        metadata = item.get("metadata", {})

        if metadata:
            content += "### Metrics\n\n"
            content += f"- Response Time: {metadata.get('response_time_seconds', 'N/A')} seconds\n"
            content += f"- Trust Score: {metadata.get('trust_score', 'N/A')}/100\n"
            content += f"- Cost Level: {metadata.get('estimated_cost_level', 'N/A')}\n"
            content += f"- Sources Used: {metadata.get('source_count', 'N/A')}\n\n"

        content += "### Answer\n\n"
        content += f"{item['answer']}\n\n"

        if item["sources"]:
            content += "### Sources\n\n"

            for j, src in enumerate(item["sources"], start=1):
                content += (
                    f"{j}. **Source {j}: {src.get('source_name', 'Source')}** — "
                    f"{src.get('title', 'Untitled')}  \n"
                )
                content += f"   {src.get('url', '')}  \n"
                content += (
                    f"   Reliability: {src.get('reliability_label', 'Unknown')} "
                    f"({src.get('reliability_score', 'N/A')}/100)\n"
                )

        content += "\n---\n\n"

    return content


def show_hero():
    st.markdown(
        """
        <div class="arca-hero">
            <div class="arca-title">Agent ARCA</div>
            <div class="arca-subtitle">
                Research faster, understand better, and turn sources into summaries, reports, slides, and study tools.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_quick_start(mode_name):
    st.session_state.pending_quick_start = mode_name
    st.rerun()


def apply_pending_quick_start():
    preset = st.session_state.get("pending_quick_start")

    if not preset:
        return

    if preset == "study":
        st.session_state.user_mode_widget = "Student Mode"
        st.session_state.source_mode_widget = "Search the web"
        st.session_state.output_style_widget = "Study Guide"
        st.session_state.question_box = "Explain this topic like I am a beginner: "

    elif preset == "files":
        st.session_state.user_mode_widget = "Student Mode"
        st.session_state.source_mode_widget = "Use my sources"
        st.session_state.output_style_widget = "Simple Summary"
        st.session_state.question_box = "Summarize the attached files in simple terms."

    elif preset == "web":
        st.session_state.user_mode_widget = "General Mode"
        st.session_state.source_mode_widget = "Search the web"
        st.session_state.output_style_widget = "Detailed Research"
        st.session_state.question_box = "Research this topic using reliable sources: "

    st.session_state.pending_quick_start = None


def show_start_cards():
    if st.session_state.chat_history:
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class="arca-card">
                <div class="arca-card-title">🎓 Study a topic</div>
                <div class="arca-card-text">Explain concepts, create quizzes, and simplify class materials.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Start studying", use_container_width=True):
            apply_quick_start("study")

    with col2:
        st.markdown(
            """
            <div class="arca-card">
                <div class="arca-card-title">📎 Summarize files</div>
                <div class="arca-card-text">Upload PDFs, docs, slides, or screenshots and get clean findings.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Summarize files", use_container_width=True):
            apply_quick_start("files")

    with col3:
        st.markdown(
            """
            <div class="arca-card">
                <div class="arca-card-title">🔍 Research the web</div>
                <div class="arca-card-text">Use trusted sources, evidence maps, and exportable outputs.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Research web", use_container_width=True):
            apply_quick_start("web")

    st.markdown("")


def show_example_prompts():
    if st.session_state.chat_history:
        return

    st.markdown("**Try asking:**")

    examples = [
        "Summarize this document in simple terms",
        "Compare these sources and find conflicts",
        "Create presentation notes from this topic",
        "Explain this like I am a beginner",
        "Make a study guide with quiz questions",
    ]

    cols = st.columns(len(examples))

    for col, example in zip(cols, examples):
        with col:
            if st.button(example, use_container_width=True):
                st.session_state.question_box = example
                st.rerun()


def show_answer_badges(user_mode, analysis_mode, research_depth, source_mode, output_style):
    st.markdown(
        f"""
        <span class="arca-badge">{user_mode}</span>
        <span class="arca-badge">{analysis_mode}</span>
        <span class="arca-badge">{research_depth}</span>
        <span class="arca-badge">{source_mode}</span>
        <span class="arca-badge">{output_style}</span>
        """,
        unsafe_allow_html=True,
    )


def render_question_bar():
    st.markdown('<div class="input-wrap">', unsafe_allow_html=True)

    cols = st.columns([0.82, 0.08, 0.10])

    with cols[0]:
        st.text_input(
            "Question",
            key="question_box",
            label_visibility="collapsed",
            placeholder="Ask a question, paste a task, or upload files and ask what you need...",
        )

    voice_text = ""

    with cols[1]:
        with st.popover("🎤", use_container_width=True):
            audio_input = st.audio_input("Record")
            if audio_input:
                voice_text = transcribe_voice(audio_input)
                if voice_text:
                    st.success("Voice captured.")

    with cols[2]:
        send_clicked = st.button("↑", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if voice_text:
        return voice_text

    if send_clicked and st.session_state.question_box.strip():
        return st.session_state.question_box.strip()

    return None


def show_dashboard():
    if not st.session_state.latest_student_answer:
        st.info("Ask a question first.")
        return

    answer = st.session_state.latest_student_answer
    sources = st.session_state.latest_sources
    metadata = st.session_state.latest_metadata

    source_count = len(sources)
    word_count = len(answer.split()) if answer else 0
    source_types = Counter([src.get("type", "unknown") for src in sources])

    st.subheader("📊 Dashboard")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Sources", source_count)
    col2.metric("Words", word_count)
    col3.metric("Trust", f"{metadata.get('trust_score', 0)}/100")
    col4.metric("Time", f"{metadata.get('response_time_seconds', 'N/A')}s")
    col5.metric("Cost", metadata.get("estimated_cost_level", "N/A"))

    with st.expander("Source breakdown", expanded=False):
        if source_types:
            for source_type, count in source_types.items():
                st.write(f"- **{source_type}**: {count}")
        else:
            st.write("No sources available.")

    with st.expander("Source reliability", expanded=False):
        if not sources:
            st.warning("No sources available.")
        else:
            st.markdown(
                f"**Overall Trust:** {metadata.get('trust_score', 0)}/100 "
                f"({metadata.get('trust_label', 'N/A')})"
            )
            st.caption(metadata.get("trust_message", ""))

            for i, src in enumerate(sources, start=1):
                st.markdown(
                    f"**Source {i}: {src.get('source_name', 'Source')}** — "
                    f"{src.get('reliability_label', 'Unknown')} "
                    f"({src.get('reliability_score', 'N/A')}/100)"
                )
                st.caption(src.get("reliability_reason", ""))

    with st.expander("Performance details", expanded=False):
        st.markdown(f"**Workflow:** {metadata.get('workflow_type', 'N/A')}")
        st.markdown(f"**Research Depth:** {metadata.get('research_depth', 'N/A')}")
        st.markdown(f"**Input Tokens:** {metadata.get('input_tokens_estimate', 'N/A')}")
        st.markdown(f"**Output Tokens:** {metadata.get('output_tokens_estimate', 'N/A')}")
        st.markdown(f"**Total Tokens:** {metadata.get('total_tokens_estimate', 'N/A')}")


def show_workspace():
    st.subheader("🗂️ Workspace")

    saved_count = len(st.session_state.saved_findings)

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Saved Findings", saved_count)

    with col2:
        if st.button("Clear Saved", use_container_width=True):
            st.session_state.saved_findings = []
            st.rerun()

    if saved_count == 0:
        st.info("No saved findings yet.")
        return

    for i, item in enumerate(st.session_state.saved_findings, start=1):
        with st.expander(f"{i}. {item['question']}"):
            st.markdown(f"**Mode:** {item['user_mode']}")
            st.markdown(f"**Analysis:** {item['analysis_mode']}")
            st.markdown(f"**Saved:** {item['timestamp']}")

            metadata = item.get("metadata", {})

            if metadata:
                st.markdown(f"**Trust:** {metadata.get('trust_score', 'N/A')}/100")
                st.markdown(f"**Time:** {metadata.get('response_time_seconds', 'N/A')}s")

            st.markdown("### Answer")
            st.markdown(item["answer"])

            if item["sources"]:
                st.markdown("### Sources")
                for j, src in enumerate(item["sources"], start=1):
                    st.markdown(
                        f"{j}. **Source {j}: {src.get('source_name', 'Source')}** — "
                        f"[{src.get('title', 'Untitled')}]({src.get('url', '')})"
                    )

    markdown_file = build_saved_research_markdown(st.session_state.saved_findings)

    st.download_button(
        label="⬇️ Download Saved Research",
        data=markdown_file,
        file_name="ARCA_Saved_Research_Collection.md",
        mime="text/markdown",
        use_container_width=True,
    )


def show_exports():
    st.subheader("📄 Exports")

    if not st.session_state.latest_student_answer:
        st.info("Ask a question first.")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        report_file = generate_word_report(
            question=st.session_state.latest_question,
            answer=st.session_state.latest_student_answer,
            sources=st.session_state.latest_sources,
            user_mode=st.session_state.latest_user_mode,
            analysis_mode=st.session_state.latest_analysis_mode,
            quiz_feedback=st.session_state.latest_quiz_feedback,
        )

        st.download_button(
            "⬇️ Word Report",
            data=report_file,
            file_name="ARCA_Research_Report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    with col2:
        ppt_file = generate_powerpoint_deck(
            question=st.session_state.latest_question,
            answer=st.session_state.latest_student_answer,
            sources=st.session_state.latest_sources,
            user_mode=st.session_state.latest_user_mode,
            analysis_mode=st.session_state.latest_analysis_mode,
            quiz_feedback=st.session_state.latest_quiz_feedback,
        )

        st.download_button(
            "⬇️ PowerPoint Deck",
            data=ppt_file,
            file_name="ARCA_Research_Deck.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )

    with col3:
        pdf_file = generate_pdf_report(
            question=st.session_state.latest_question,
            answer=st.session_state.latest_student_answer,
            sources=st.session_state.latest_sources,
            user_mode=st.session_state.latest_user_mode,
            analysis_mode=st.session_state.latest_analysis_mode,
            quiz_feedback=st.session_state.latest_quiz_feedback,
        )

        st.download_button(
            "⬇️ PDF Report",
            data=pdf_file,
            file_name="ARCA_Research_Report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def show_quiz_section(user_mode):
    if user_mode != "Student Mode":
        return

    if not st.session_state.latest_student_answer:
        return

    st.markdown("### 🎓 Learning Practice")

    with st.expander("Practice with quiz + flashcards", expanded=False):
        col1, col2 = st.columns([0.7, 0.3])

        with col1:
            st.caption("Generate interactive practice from the latest ARCA answer.")

        with col2:
            if st.button("Generate Practice", use_container_width=True):
                with st.spinner("Creating quiz and flashcards..."):
                    activity = generate_learning_activity(
                        st.session_state.latest_student_answer
                    )

                if activity:
                    st.session_state.learning_activity = activity
                    st.session_state.quiz_score = None
                    st.success("Practice created.")
                else:
                    st.warning("Could not create practice right now. Try again.")

        activity = st.session_state.get("learning_activity")

        if not activity:
            st.info("Click **Generate Practice** to create multiple-choice questions and flashcards.")
            return

        mcq_tab, flashcard_tab, tips_tab, free_response_tab = st.tabs(
            [
                "✅ Quiz",
                "🧠 Flashcards",
                "📌 Revision Tips",
                "✍️ Written Feedback",
            ]
        )

        with mcq_tab:
            questions = activity.get("multiple_choice", [])

            if not questions:
                st.info("No quiz questions available.")
            else:
                user_answers = []

                for i, item in enumerate(questions, start=1):
                    st.markdown(f"**{i}. {item.get('question', '')}**")

                    options = item.get("options", [])

                    if options:
                        selected = st.radio(
                            "Choose one",
                            options=list(range(len(options))),
                            format_func=lambda x, opts=options: opts[x],
                            key=f"mcq_{i}",
                            label_visibility="collapsed",
                        )

                        user_answers.append(selected)

                if st.button("Check My Score", use_container_width=True):
                    score = 0
                    feedback_lines = []

                    for i, item in enumerate(questions, start=1):
                        correct_index = item.get("correct_index", 0)
                        explanation = item.get("explanation", "")
                        options = item.get("options", [""])

                        user_choice = user_answers[i - 1]

                        if user_choice == correct_index:
                            score += 1
                            feedback_lines.append(
                                f"✅ **Question {i}: Correct.** {explanation}"
                            )
                        else:
                            correct_option = options[correct_index] if correct_index < len(options) else ""
                            feedback_lines.append(
                                f"❌ **Question {i}: Not quite.** Correct answer: **{correct_option}**. {explanation}"
                            )

                    st.session_state.quiz_score = {
                        "score": score,
                        "total": len(questions),
                        "feedback": feedback_lines,
                    }

                if st.session_state.get("quiz_score"):
                    result = st.session_state.quiz_score
                    score = result["score"]
                    total = result["total"]

                    st.success(f"Score: {score}/{total}")

                    if score == total:
                        st.balloons()
                        st.markdown("Excellent — you understood this very well.")
                    elif score >= max(1, total - 2):
                        st.markdown("Good job — review the missed points once.")
                    else:
                        st.markdown("You may need to revise the key concepts again.")

                    for line in result["feedback"]:
                        st.markdown(line)

        with flashcard_tab:
            flashcards = activity.get("flashcards", [])

            if not flashcards:
                st.info("No flashcards available.")
            else:
                for i, card in enumerate(flashcards, start=1):
                    with st.expander(f"Flashcard {i}: {card.get('front', '')}"):
                        st.markdown(card.get("back", ""))

        with tips_tab:
            tips = activity.get("revision_tips", [])

            if not tips:
                st.info("No revision tips available.")
            else:
                for tip in tips:
                    st.markdown(f"- {tip}")

        with free_response_tab:
            st.caption("Use this if you want ARCA to review your own written answer.")

            student_answers = st.text_area(
                "Write your answer here",
                placeholder="Explain the topic in your own words...",
                height=150,
            )

            if st.button("Get Written Feedback", use_container_width=True):
                if not student_answers.strip():
                    st.warning("Please write your answer first.")
                else:
                    with st.spinner("Checking your understanding..."):
                        feedback = evaluate_quiz_answers(
                            original_answer=st.session_state.latest_student_answer,
                            student_answers=student_answers,
                        )

                    st.session_state.latest_quiz_feedback = feedback

            if st.session_state.latest_quiz_feedback:
                st.markdown("### Feedback")
                st.markdown(st.session_state.latest_quiz_feedback)


def show_followup_box():
    if not st.session_state.latest_student_answer:
        return

    st.markdown("### 💬 Ask More About This Answer")

    followup_question = st.text_area(
        "Ask a follow-up question or give feedback",
        placeholder="Example: Can you explain the second point more simply? Can you turn this into bullets? What should I study next?",
        height=110,
    )

    if st.button("Ask Follow-up", use_container_width=True):
        if not followup_question.strip():
            st.warning("Please type a follow-up question first.")
            return

        followup_prompt = f"""
The user is asking a follow-up question about the latest ARCA answer.

Latest answer:
{st.session_state.latest_student_answer}

User follow-up:
{followup_question}

Answer clearly. If the follow-up asks for a rewrite, formatting, simplification, deeper explanation, or next steps, respond based on the latest answer.
""".strip()

        with st.spinner("Answering follow-up..."):
            result = run_pipeline(
                question=followup_prompt,
                urls=[],
                uploaded_pdfs=[],
                uploaded_docs=[],
                uploaded_ppts=[],
                uploaded_images=[],
                mode="Use my sources",
                user_mode=st.session_state.latest_user_mode or "Student Mode",
                analysis_mode=st.session_state.latest_analysis_mode or "Standard Research",
                previous_context=st.session_state.research_context,
                chat_history=[
                    (item["role"], item["message"])
                    for item in st.session_state.chat_history
                ],
                max_web_results=2,
                prefer_trusted_sources=True,
                research_depth="Fast Research",
            )

        answer = result["answer"]

        st.session_state.latest_student_answer = answer
        st.session_state.latest_sources = result.get("sources", st.session_state.latest_sources)
        st.session_state.latest_metadata = result.get("metadata", st.session_state.latest_metadata)
        st.session_state.learning_activity = None
        st.session_state.quiz_score = None

        st.session_state.chat_history.append(
            {
                "role": "user",
                "message": followup_question,
            }
        )

        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "message": answer,
                "raw_answer": answer,
                "sources": result.get("sources", []),
            }
        )

        st.rerun()


def initialize_session_state():
    defaults = {
        "chat_history": [],
        "research_context": None,
        "latest_student_answer": "",
        "latest_quiz_feedback": "",
        "latest_sources": [],
        "latest_question": "",
        "latest_user_mode": "",
        "latest_analysis_mode": "",
        "latest_metadata": {},
        "saved_findings": [],
        "show_inline_image": True,
        "question_box": "",
        "output_style_widget": "Simple Summary",
        "user_mode_widget": "Student Mode",
        "source_mode_widget": "Use my sources",
        "analysis_mode_widget": "Standard Research",
        "research_depth_widget": "Fast Research",
        "learning_activity": None,
        "quiz_score": None,
        "pending_quick_start": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()
apply_pending_quick_start()
show_hero()


with st.sidebar:
    st.subheader("Setup")

    output_style = st.selectbox(
        "Answer style",
        [
            "Simple Summary",
            "Study Guide",
            "Detailed Research",
            "Presentation Notes",
            "Decision Brief",
        ],
        key="output_style_widget",
    )

    user_mode = st.radio(
        "Mode",
        ["Student Mode", "General Mode"],
        horizontal=True,
        key="user_mode_widget",
    )

    source_mode = st.radio(
        "Sources",
        ["Use my sources", "Search the web", "Use my sources + web search"],
        key="source_mode_widget",
    )

    urls_input = st.text_area(
        "Links",
        placeholder="Paste URLs or YouTube links...",
        height=80,
    )

    uploaded_files = st.file_uploader(
        "Attach files",
        type=["pdf", "docx", "pptx", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        help="PDF, DOCX, PPTX, PNG, JPG, JPEG",
    )

    show_attached_files(uploaded_files)

    with st.expander("Advanced", expanded=False):
        analysis_mode = st.radio(
            "Analysis",
            ["Standard Research", "Compare & Verify"],
            key="analysis_mode_widget",
        )

        research_depth = st.radio(
            "Speed",
            ["Fast Research", "Deep Research"],
            key="research_depth_widget",
        )

        max_web_results = st.slider(
            "Web sources",
            min_value=2,
            max_value=10,
            value=3,
        )

        prefer_trusted_sources = st.checkbox(
            "Prefer trusted sources",
            value=True,
        )

        st.session_state.show_inline_image = st.checkbox(
            "Enable visual snapshot",
            value=st.session_state.show_inline_image,
        )

    if st.button("Clear Session", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.research_context = None
        st.session_state.latest_student_answer = ""
        st.session_state.latest_quiz_feedback = ""
        st.session_state.latest_sources = []
        st.session_state.latest_question = ""
        st.session_state.latest_user_mode = ""
        st.session_state.latest_analysis_mode = ""
        st.session_state.latest_metadata = {}
        st.session_state.question_box = ""
        st.session_state.learning_activity = None
        st.session_state.quiz_score = None
        st.session_state.pending_quick_start = None
        st.rerun()


show_start_cards()
show_example_prompts()

question = render_question_bar()

research_tab, dashboard_tab, workspace_tab, exports_tab = st.tabs(
    ["🔎 Research", "📊 Dashboard", "🗂️ Workspace", "📄 Exports"]
)


with research_tab:
    for item in st.session_state.chat_history:
        role = item["role"]
        message = item["message"]
        sources = item.get("sources", [])

        with st.chat_message(role):
            if role == "assistant":
                render_answer_audio_button(
                    answer=item.get("raw_answer", message),
                    key_prefix=f"history_{abs(hash(message))}",
                )

                st.markdown(message, unsafe_allow_html=True)

                if sources:
                    with st.expander("Sources", expanded=False):
                        for i, src in enumerate(sources, start=1):
                            st.markdown(
                                f"{i}. **{src.get('source_name', 'Source')}** — "
                                f"[{src.get('title', 'Untitled')}]({src.get('url', '')})"
                            )
            else:
                st.markdown(message)

    if question:
        st.session_state.chat_history.append(
            {
                "role": "user",
                "message": question,
            }
        )

        with st.chat_message("user"):
            st.markdown(question)

        urls = [u.strip() for u in urls_input.split("\n") if u.strip()]

        uploaded_pdfs, uploaded_docs, uploaded_ppts, uploaded_images = split_uploaded_files(
            uploaded_files
        )

        effective_question = prepare_effective_question(
            question=question,
            uploaded_files=uploaded_files,
            urls=urls,
        )

        if effective_question == "__ABOUT_ARCA__":
            answer = build_about_arca_answer()
            sources = []
            metadata = {
                "response_time_seconds": 0,
                "input_tokens_estimate": 0,
                "output_tokens_estimate": 0,
                "total_tokens_estimate": 0,
                "estimated_cost_level": "Very low",
                "workflow_type": "About Agent ARCA",
                "research_depth": "N/A",
                "trust_score": 100,
                "trust_label": "Self description",
                "trust_message": "This answer describes Agent ARCA's own capabilities.",
                "source_count": 0,
            }

            with st.chat_message("assistant"):
                show_answer_badges(
                    user_mode=user_mode,
                    analysis_mode=analysis_mode,
                    research_depth=research_depth,
                    source_mode="About ARCA",
                    output_style=output_style,
                )

                top_cols = st.columns([0.85, 0.15])

                with top_cols[0]:
                    st.markdown("### Answer")

                with top_cols[1]:
                    render_answer_audio_button(
                        answer=answer,
                        key_prefix="about_arca",
                    )

                st.markdown('<div class="answer-card">', unsafe_allow_html=True)
                st.markdown(answer, unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            st.session_state.latest_student_answer = answer
            st.session_state.latest_sources = sources
            st.session_state.latest_question = question
            st.session_state.latest_user_mode = user_mode
            st.session_state.latest_analysis_mode = analysis_mode
            st.session_state.latest_metadata = metadata
            st.session_state.learning_activity = None
            st.session_state.quiz_score = None

            st.session_state.chat_history.append(
                {
                    "role": "assistant",
                    "message": answer,
                    "raw_answer": answer,
                    "sources": [],
                }
            )

            st.rerun()

        effective_source_mode = source_mode

        if (uploaded_files or urls) and source_mode == "Search the web":
            effective_source_mode = "Use my sources + web search"

        style_instruction = build_style_instruction(output_style)

        pipeline_question = f"""
User question:
{effective_question}

Output style requested:
{output_style}

Style instruction:
{style_instruction}
""".strip()

        with st.chat_message("assistant"):
            with st.spinner("Researching..."):
                result = run_pipeline(
                    question=pipeline_question,
                    urls=urls,
                    uploaded_pdfs=uploaded_pdfs,
                    uploaded_docs=uploaded_docs,
                    uploaded_ppts=uploaded_ppts,
                    uploaded_images=uploaded_images,
                    mode=effective_source_mode,
                    user_mode=user_mode,
                    analysis_mode=analysis_mode,
                    previous_context=st.session_state.research_context,
                    chat_history=[
                        (item["role"], item["message"])
                        for item in st.session_state.chat_history
                    ],
                    max_web_results=max_web_results,
                    prefer_trusted_sources=prefer_trusted_sources,
                    research_depth=research_depth,
                )

            st.session_state.research_context = result["context"]

            answer = result["answer"]
            sources = result["sources"]
            metadata = result.get("metadata", {})

            clickable_answer = make_clickable_source_markers(answer, sources)

            show_answer_badges(
                user_mode=user_mode,
                analysis_mode=analysis_mode,
                research_depth=research_depth,
                source_mode=effective_source_mode,
                output_style=output_style,
            )

            top_cols = st.columns([0.85, 0.15])

            with top_cols[0]:
                st.markdown("### Answer")

            with top_cols[1]:
                render_answer_audio_button(
                    answer=answer,
                    key_prefix=f"latest_{datetime.now().timestamp()}",
                )

            st.markdown('<div class="answer-card">', unsafe_allow_html=True)
            st.markdown(clickable_answer, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            show_inline_visual_reference(question)

            if sources:
                with st.expander("Sources", expanded=False):
                    for i, src in enumerate(sources, start=1):
                        st.markdown(
                            f"{i}. **Source {i}: {src.get('source_name', 'Source')}** — "
                            f"[{src.get('title', 'Untitled')}]({src.get('url', '')})"
                        )

            st.session_state.latest_student_answer = answer
            st.session_state.latest_sources = sources
            st.session_state.latest_question = question
            st.session_state.latest_user_mode = user_mode
            st.session_state.latest_analysis_mode = analysis_mode
            st.session_state.latest_metadata = metadata
            st.session_state.learning_activity = None
            st.session_state.quiz_score = None

        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "message": clickable_answer,
                "raw_answer": answer,
                "sources": sources,
            }
        )

    if st.session_state.latest_student_answer:
        st.markdown("")

        action_col1, action_col2, action_col3 = st.columns(3)

        with action_col1:
            if st.button("⭐ Save", use_container_width=True):
                st.session_state.saved_findings.append(
                    {
                        "question": st.session_state.latest_question,
                        "answer": st.session_state.latest_student_answer,
                        "sources": st.session_state.latest_sources,
                        "user_mode": st.session_state.latest_user_mode,
                        "analysis_mode": st.session_state.latest_analysis_mode,
                        "metadata": st.session_state.latest_metadata,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                )

                st.success("Saved.")

        with action_col2:
            if st.button("📊 View metrics", use_container_width=True):
                st.info("Open the Dashboard tab.")

        with action_col3:
            if st.button("📄 Export", use_container_width=True):
                st.info("Open the Exports tab.")

        show_followup_box()
        show_quiz_section(user_mode)


with dashboard_tab:
    show_dashboard()


with workspace_tab:
    show_workspace()


with exports_tab:
    show_exports()
