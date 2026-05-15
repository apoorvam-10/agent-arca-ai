import re
import tempfile
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

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


def get_domain(url):
    try:
        if not url.startswith("http"):
            return "uploaded-file"

        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        return domain

    except Exception:
        return "unknown"


def rate_source_reliability(source):
    source_type = source.get("type", "unknown")
    url = source.get("url", "")
    domain = get_domain(url)

    high_trust_domains = [
        "nih.gov",
        "ncbi.nlm.nih.gov",
        "pmc.ncbi.nlm.nih.gov",
        "cdc.gov",
        "who.int",
        "fda.gov",
        "nature.com",
        "sciencedirect.com",
        "springer.com",
        "ieee.org",
        "acm.org",
        "arxiv.org",
        "edu",
        "gov",
    ]

    medium_trust_domains = [
        "ibm.com",
        "microsoft.com",
        "google.com",
        "aws.amazon.com",
        "cloud.google.com",
        "openai.com",
        "wikipedia.org",
        "youtube.com",
        "youtu.be",
    ]

    if source_type in ["pdf", "docx", "image"]:
        return {
            "label": "User-provided source",
            "score": 80,
            "reason": "Uploaded directly by the user; useful but should be checked for origin and accuracy.",
        }

    if any(domain.endswith(d) or d in domain for d in high_trust_domains):
        return {
            "label": "High trust",
            "score": 95,
            "reason": "Academic, government, medical, or research-oriented source.",
        }

    if any(d in domain for d in medium_trust_domains):
        return {
            "label": "Moderate trust",
            "score": 75,
            "reason": "Recognized organization or platform, but claims should still be verified.",
        }

    if source_type == "web_search":
        return {
            "label": "Needs review",
            "score": 60,
            "reason": "Web result source; reliability depends on publisher and evidence quality.",
        }

    if source_type == "url":
        return {
            "label": "Needs review",
            "score": 60,
            "reason": "URL source; reliability depends on domain, author, and citations.",
        }

    return {
        "label": "Unknown",
        "score": 50,
        "reason": "Reliability could not be determined automatically.",
    }


def compute_overall_trust_score(sources):
    if not sources:
        return {
            "score": 0,
            "label": "No sources",
            "message": "No sources available for trust scoring.",
        }

    scores = [
        rate_source_reliability(src)["score"]
        for src in sources
    ]

    avg_score = round(sum(scores) / len(scores))

    if avg_score >= 85:
        label = "Strong"
        message = "The response is supported by generally strong sources."
    elif avg_score >= 70:
        label = "Moderate"
        message = "The response has decent support, but some claims should be verified."
    elif avg_score >= 50:
        label = "Limited"
        message = "The response uses sources that need careful review."
    else:
        label = "Weak"
        message = "The response has weak or insufficient source support."

    return {
        "score": avg_score,
        "label": label,
        "message": message,
    }


def show_source_reliability_panel(sources):
    st.markdown("### 🛡️ Source Reliability Ranking")

    if not sources:
        st.warning("No sources available for reliability ranking.")
        return

    trust = compute_overall_trust_score(sources)

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Overall Trust Score", f"{trust['score']}/100")

    with col2:
        st.metric("Trust Level", trust["label"])

    st.caption(trust["message"])

    for i, src in enumerate(sources, start=1):
        rating = rate_source_reliability(src)
        domain = get_domain(src.get("url", ""))

        with st.expander(
            f"Source {i}: {src.get('source_name', 'Source')} — {rating['label']}"
        ):
            st.markdown(f"**Title:** {src.get('title', 'Untitled')}")
            st.markdown(f"**Domain/File:** {domain}")
            st.markdown(f"**Type:** {src.get('type', 'unknown')}")
            st.markdown(f"**Reliability Score:** {rating['score']}/100")
            st.markdown(f"**Reason:** {rating['reason']}")

            if src.get("url", "").startswith("http"):
                st.markdown(f"[Open source]({src['url']})")


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
    trust = compute_overall_trust_score(sources)

    source_types = Counter(
        [src.get("type", "unknown") for src in sources]
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Sources Used", source_count)
    col2.metric("Answer Length", f"{word_count} words")
    col3.metric("Mode", user_mode.replace(" Mode", ""))
    col4.metric("Analysis", analysis_mode)
    col5.metric("Trust", f"{trust['score']}/100")

    st.markdown("### Source Breakdown")

    if source_types:
        for source_type, count in source_types.items():
            st.write(f"- **{source_type}**: {count}")
    else:
        st.write("No sources available.")

    st.markdown("### Quick Interpretation")

    if source_count >= 4 and trust["score"] >= 75:
        st.success(
            "Strong research coverage with decent source trust."
        )
    elif source_count >= 2:
        st.info(
            "Moderate coverage. Add more high-quality sources for stronger verification."
        )
    else:
        st.warning(
            "Limited source coverage. Add more PDFs, Word docs, images, URLs, or web search."
        )

    show_source_reliability_panel(sources)


def build_saved_research_markdown(saved_findings):
    content = "# Agent ARCA Saved Research Collection\n\n"

    if not saved_findings:
        content += "No saved findings yet.\n"
        return content

    for i, item in enumerate(saved_findings, start=1):
        content += f"## Finding {i}: {item['question']}\n\n"
        content += f"**Mode:** {item['user_mode']}\n\n"
        content += f"**Analysis Type:** {item['analysis_mode']}\n\n"
        content += f"**Saved At:** {item['timestamp']}\n\n"
        content += "### Answer\n\n"
        content += f"{item['answer']}\n\n"

        if item["sources"]:
            content += "### Sources\n\n"
            for j, src in enumerate(item["sources"], start=1):
                content += f"{j}. **Source {j}: {src['source_name']}** — {src['title']}  \n"
                content += f"   {src['url']}\n"

        content += "\n---\n\n"

    return content


def show_saved_research_workspace():
    st.divider()
    st.subheader("🗂️ Research Workspace")

    saved_count = len(st.session_state.saved_findings)

    st.caption(
        "Save important ARCA responses here while researching. You can download the full collection later."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Saved Findings", saved_count)

    with col2:
        if st.button("Clear Saved Findings", use_container_width=True):
            st.session_state.saved_findings = []
            st.rerun()

    if saved_count == 0:
        st.info("No saved findings yet. After ARCA generates an answer, click **Save This Finding**.")
    else:
        for i, item in enumerate(st.session_state.saved_findings, start=1):
            with st.expander(f"Finding {i}: {item['question']}"):
                st.markdown(f"**Mode:** {item['user_mode']}")
                st.markdown(f"**Analysis:** {item['analysis_mode']}")
                st.markdown(f"**Saved:** {item['timestamp']}")
                st.markdown("### Answer")
                st.markdown(item["answer"])

                if item["sources"]:
                    st.markdown("### Sources")
                    for j, src in enumerate(item["sources"], start=1):
                        st.markdown(
                            f"{j}. **Source {j}: {src['source_name']}** — [{src['title']}]({src['url']})"
                        )

        markdown_file = build_saved_research_markdown(
            st.session_state.saved_findings
        )

        st.download_button(
            label="⬇️ Download Saved Research Collection",
            data=markdown_file,
            file_name="ARCA_Saved_Research_Collection.md",
            mime="text/markdown",
            use_container_width=True,
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

if "saved_findings" not in st.session_state:
    st.session_state.saved_findings = []


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
    if st.button("⭐ Save This Finding to Research Workspace"):
        st.session_state.saved_findings.append(
            {
                "question": st.session_state.latest_question,
                "answer": st.session_state.latest_student_answer,
                "sources": st.session_state.latest_sources,
                "user_mode": st.session_state.latest_user_mode,
                "analysis_mode": st.session_state.latest_analysis_mode,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )

        st.success("Saved to Research Workspace.")


if st.session_state.latest_student_answer:
    show_research_dashboard(
        answer=st.session_state.latest_student_answer,
        sources=st.session_state.latest_sources,
        user_mode=st.session_state.latest_user_mode,
        analysis_mode=st.session_state.latest_analysis_mode,
    )


show_saved_research_workspace()


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
