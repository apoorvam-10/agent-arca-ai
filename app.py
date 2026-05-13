import re
import tempfile
from collections import Counter

import streamlit as st
from gtts import gTTS
import google.generativeai as genai

from pipeline import (
    run_pipeline,
    evaluate_quiz_answers,
    generate_word_report,
    generate_powerpoint_deck,
    generate_pdf_report,
)

st.set_page_config(page_title="Agent ARCA", page_icon="🤖", layout="wide")

st.title("🤖 Agent ARCA")
st.caption("AI-powered multimodal research, learning, and decision-intelligence assistant.")


def make_clickable_source_markers(answer, sources):
    """
    Converts [Source 1], [Source 2], etc. into clickable links.
    """
    for i, src in enumerate(sources, start=1):
        url = src.get("url", "")

        if not url:
            continue

        marker = f"[Source {i}]"

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
            suffix=".mp3"
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

        model = genai.GenerativeModel(
            "gemini-3-flash-preview"
        )

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
            st.warning(
                "Gemini voice quota reached. Please type your question or wait 1–2 minutes."
            )
        else:
            st.warning(
                "Voice transcription failed. Please type your question instead."
            )

        return ""


def show_research_dashboard(
    answer,
    sources,
    user_mode,
    analysis_mode,
):
    st.divider()

    st.subheader("📊 Research Dashboard")

    source_count = len(sources)
    word_count = len(answer.split()) if answer else 0

    source_types = Counter(
        [src.get("type", "unknown") for src in sources]
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Sources Used", source_count)
    col2.metric("Answer Length", f"{word_count} words")
    col3.metric("Mode", user_mode.replace(" Mode", ""))
    col4.metric("Analysis", analysis_mode)

    st.markdown("### Source Breakdown")

    if source_types:
        for source_type, count in source_types.items():
            st.write(f"- **{source_type}**: {count}")
    else:
        st.write("No sources available.")

    st.markdown("### Quick Interpretation")

    if source_count >= 4:
        st.success(
            "Strong source coverage for this response."
        )
    elif source_count >= 2:
        st.info(
            "Moderate source coverage. Add more sources for stronger comparison."
        )
    else:
        st.warning(
            "Limited source coverage. Add more PDFs, Word docs, images, URLs, or web search."
        )


if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "research_context" not in st.session_state:
    st.session_state.research_context = None

if "latest_student_answer" not in st.session_state:
    st.session_state.latest_student_answer = ""

if "latest_quiz_feedback" not in st.session_state:
    st.session_state.latest_quiz_feedback = ""

if "latest_sources" not in st.session_state:
    st.session_state.latest_sources = []

if "latest_question" not in st.session_state:
    st.session_state.latest_question = ""

if "latest_user_mode" not in st.session_state:
    st.session_state.latest_user_mode = ""

if "latest_analysis_mode" not in st.session_state:
    st.session_state.latest_analysis_mode = ""


with st.sidebar:
    st.header("Mode")

    user_mode = st.radio(
        "Choose Experience",
        [
            "Student Mode",
            "General Mode",
        ],
    )

    if user_mode == "Student Mode":
        st.success("🎓 Student Mode Active")
        st.caption(
            "Summaries, quizzes, learning guidance, and understanding evaluation."
        )
    else:
        st.info("💼 General Mode Active")
        st.caption(
            "Professional research synthesis and decision intelligence."
        )

    st.divider()

    st.header("Research Workflow")

    analysis_mode = st.radio(
        "Choose analysis type",
        [
            "Standard Research",
            "Compare & Verify",
        ],
    )

    if analysis_mode == "Compare & Verify":
        st.warning("🔍 Compare & Verify Mode Active")
        st.caption(
            "Best for comparing PDFs, docs, videos, images, and web results."
        )

    st.divider()

    st.header("Research Sources")

    source_mode = st.radio(
        "Choose source mode",
        [
            "Use my sources",
            "Search the web",
            "Use my sources + web search",
        ],
    )

    urls_input = st.text_area(
        "Paste URLs or YouTube links",
        placeholder="https://example.com/article\nhttps://youtube.com/watch?v=...",
    )

    uploaded_pdfs = st.file_uploader(
        "Upload PDF files",
        type=["pdf"],
        accept_multiple_files=True,
    )

    uploaded_docs = st.file_uploader(
        "Upload Word documents",
        type=["docx"],
        accept_multiple_files=True,
    )

    uploaded_images = st.file_uploader(
        "Upload images/screenshots",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    st.divider()

    if st.button("Clear Chat"):
        st.session_state.chat_history = []
        st.session_state.research_context = None
        st.session_state.latest_student_answer = ""
        st.session_state.latest_quiz_feedback = ""
        st.session_state.latest_sources = []
        st.session_state.latest_question = ""
        st.session_state.latest_user_mode = ""
        st.session_state.latest_analysis_mode = ""

        st.rerun()


audio_input = st.audio_input("🎤 Ask using voice")

voice_question = ""

if audio_input:
    voice_question = transcribe_voice(audio_input)

    if voice_question:
        st.info(f"🗣️ You said: {voice_question}")


question = st.chat_input(
    "Ask a research or learning question..."
)

if voice_question:
    question = voice_question


for item in st.session_state.chat_history:
    role = item["role"]
    message = item["message"]
    raw_answer = item.get("raw_answer", message)
    sources = item.get("sources", [])

    with st.chat_message(role):
        if role == "assistant":
            st.markdown(
                message,
                unsafe_allow_html=True,
            )

            if not raw_answer.startswith(
                "⚠️ Gemini API quota"
            ):
                audio_file = create_audio_file(
                    raw_answer
                )

                if audio_file:
                    st.audio(
                        audio_file,
                        format="audio/mp3",
                    )

            if sources:
                st.markdown("### Sources used")

                for i, src in enumerate(
                    sources,
                    start=1,
                ):
                    st.markdown(
                        f"{i}. **Source {i}: {src['source_name']}** — [{src['title']}]({src['url']})"
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

    urls = [
        u.strip()
        for u in urls_input.split("\n")
        if u.strip()
    ]

    with st.chat_message("assistant"):
        with st.spinner("ARCA is researching and mapping evidence..."):
            result = run_pipeline(
                question=question,
                urls=urls,
                uploaded_pdfs=uploaded_pdfs,
                uploaded_docs=uploaded_docs,
                uploaded_images=uploaded_images,
                mode=source_mode,
                user_mode=user_mode,
                analysis_mode=analysis_mode,
                previous_context=st.session_state.research_context,
                chat_history=[
                    (
                        item["role"],
                        item["message"],
                    )
                    for item in st.session_state.chat_history
                ],
            )

        st.session_state.research_context = (
            result["context"]
        )

        answer = result["answer"]

        clickable_answer = make_clickable_source_markers(
            answer,
            result["sources"],
        )

        if analysis_mode == "Compare & Verify":
            st.markdown(
                "### 🔍 Compare & Verify Response"
            )
        elif user_mode == "Student Mode":
            st.markdown(
                "### 🎓 Student Learning Response"
            )
        else:
            st.markdown(
                "### 💼 Research Intelligence Response"
            )

        st.markdown(
            clickable_answer,
            unsafe_allow_html=True,
        )

        if not answer.startswith(
            "⚠️ Gemini API quota"
        ):
            audio_file = create_audio_file(answer)

            if audio_file:
                st.audio(
                    audio_file,
                    format="audio/mp3",
                )

        if result["sources"]:
            st.markdown("### Sources used")

            for i, src in enumerate(
                result["sources"],
                start=1,
            ):
                st.markdown(
                    f"{i}. **Source {i}: {src['source_name']}** — [{src['title']}]({src['url']})"
                )

        st.session_state.latest_student_answer = (
            answer
        )

        st.session_state.latest_sources = (
            result["sources"]
        )

        st.session_state.latest_question = question

        st.session_state.latest_user_mode = (
            user_mode
        )

        st.session_state.latest_analysis_mode = (
            analysis_mode
        )

    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "message": clickable_answer,
            "raw_answer": answer,
            "sources": result["sources"],
        }
    )


if st.session_state.latest_student_answer:
    show_research_dashboard(
        answer=st.session_state.latest_student_answer,
        sources=st.session_state.latest_sources,
        user_mode=st.session_state.latest_user_mode,
        analysis_mode=st.session_state.latest_analysis_mode,
    )


if (
    user_mode == "Student Mode"
    and st.session_state.latest_student_answer
):
    st.divider()

    st.subheader("📝 Test Your Understanding")

    st.caption(
        "Answer the quiz questions generated above to evaluate your understanding."
    )

    student_answers = st.text_area(
        "Write your quiz answers here",
        placeholder="1. ...\n2. ...\n3. ...",
        height=180,
    )

    if st.button("Evaluate My Understanding"):
        if not student_answers.strip():
            st.warning(
                "Please write your answers first."
            )
        else:
            with st.spinner(
                "Evaluating your understanding..."
            ):
                feedback = evaluate_quiz_answers(
                    original_answer=st.session_state.latest_student_answer,
                    student_answers=student_answers,
                )

            st.session_state.latest_quiz_feedback = (
                feedback
            )

    if st.session_state.latest_quiz_feedback:
        st.markdown("### 📊 Quiz Feedback")

        st.markdown(
            st.session_state.latest_quiz_feedback
        )


if st.session_state.latest_student_answer:
    st.divider()

    st.subheader("📄 Export Research Outputs")

    st.caption(
        "Download professional reports and presentation decks from ARCA findings."
    )

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
            label="⬇️ Download Word Report",
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
            label="⬇️ Download PowerPoint Deck",
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
            label="⬇️ Download PDF Report",
            data=pdf_file,
            file_name="ARCA_Research_Report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
