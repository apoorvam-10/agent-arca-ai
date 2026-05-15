import re
import tempfile
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
        padding-top: 1.1rem;
        padding-bottom: 1rem;
        max-width: 1180px;
    }

    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem;
    }

    div[data-testid="stVerticalBlock"] {
        gap: 0.5rem;
    }

    .arca-hero {
        padding: 1rem 1.2rem;
        border: 1px solid rgba(120,120,120,0.25);
        border-radius: 18px;
        background: linear-gradient(135deg, rgba(120,120,255,0.08), rgba(120,255,220,0.05));
        margin-bottom: 0.8rem;
    }

    .arca-title {
        font-size: 2rem;
        font-weight: 750;
        margin-bottom: 0.15rem;
    }

    .arca-subtitle {
        color: rgba(120,120,120,0.95);
        font-size: 1rem;
    }

    .arca-card {
        padding: 0.85rem 1rem;
        border: 1px solid rgba(120,120,120,0.22);
        border-radius: 16px;
        background: rgba(250,250,250,0.03);
        min-height: 105px;
    }

    .arca-card-title {
        font-weight: 700;
        font-size: 1rem;
        margin-bottom: 0.25rem;
    }

    .arca-card-text {
        color: rgba(120,120,120,0.95);
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

    .small-muted {
        color: rgba(120,120,120,0.95);
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
        margin-top: 0.3rem;
        margin-bottom: 0.35rem;
    }

    hr {
        margin-top: 0.7rem;
        margin-bottom: 0.7rem;
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
    return text[:2500]


def create_audio_file(text):
    try:
        clean_text = clean_text_for_audio(text)

        if not clean_text:
            return None

        tts = gTTS(clean_text)

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp3",
        )

        tts.save(temp_file.name)
        return temp_file.name

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

    with col3:
        st.markdown(
            """
            <div class="arca-card">
                <div class="arca-card-title">🔍 Research the web</div>
                <div class="arca-card-text">Use trusted sources, citations, evidence maps, and exportable outputs.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
                st.session_state.pending_prompt = example
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


def show_audio_section():
    if not st.session_state.latest_student_answer:
        return

    with st.expander("🔊 Audio", expanded=False):
        if st.button("Generate Audio", use_container_width=True):
            with st.spinner("Generating audio..."):
                audio_file = create_audio_file(st.session_state.latest_student_answer)

            if audio_file:
                st.audio(audio_file, format="audio/mp3")
            else:
                st.warning("Audio could not be generated.")


def show_quiz_section(user_mode):
    if user_mode != "Student Mode":
        return

    if not st.session_state.latest_student_answer:
        return

    with st.expander("📝 Test Your Understanding", expanded=False):
        student_answers = st.text_area(
            "Your answers",
            placeholder="1. ...\n2. ...\n3. ...",
            height=160,
        )

        if st.button("Evaluate", use_container_width=True):
            if not student_answers.strip():
                st.warning("Please write your answers first.")
            else:
                with st.spinner("Evaluating..."):
                    feedback = evaluate_quiz_answers(
                        original_answer=st.session_state.latest_student_answer,
                        student_answers=student_answers,
                    )

                st.session_state.latest_quiz_feedback = feedback

        if st.session_state.latest_quiz_feedback:
            st.markdown(st.session_state.latest_quiz_feedback)


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
        "pending_prompt": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


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
        index=0,
    )

    user_mode = st.radio(
        "Mode",
        ["Student Mode", "General Mode"],
        horizontal=True,
    )

    source_mode = st.radio(
        "Sources",
        ["Use my sources", "Search the web", "Use my sources + web search"],
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
        )

        research_depth = st.radio(
            "Speed",
            ["Fast Research", "Deep Research"],
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
        st.session_state.pending_prompt = ""
        st.rerun()


with st.expander("🎤 Voice input", expanded=False):
    audio_input = st.audio_input("Record your question")


voice_question = ""

if audio_input:
    voice_question = transcribe_voice(audio_input)

    if voice_question:
        st.info(f"🗣️ {voice_question}")


show_start_cards()
show_example_prompts()


question = st.chat_input("Ask a question, paste a task, or upload files and ask what you need...")

if st.session_state.pending_prompt:
    question = st.session_state.pending_prompt
    st.session_state.pending_prompt = ""

if voice_question:
    question = voice_question


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

        style_instruction = build_style_instruction(output_style)

        pipeline_question = f"""
User question:
{question}

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
                    mode=source_mode,
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
                source_mode=source_mode,
                output_style=output_style,
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
            st.link_button(
                "📊 Dashboard",
                "#dashboard",
                use_container_width=True,
            )

        with action_col3:
            st.link_button(
                "📄 Exports",
                "#exports",
                use_container_width=True,
            )

        show_audio_section()
        show_quiz_section(user_mode)


with dashboard_tab:
    st.markdown('<span id="dashboard"></span>', unsafe_allow_html=True)
    show_dashboard()


with workspace_tab:
    show_workspace()


with exports_tab:
    st.markdown('<span id="exports"></span>', unsafe_allow_html=True)
    show_exports()
