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
    generate_visual_assets,
)

st.set_page_config(
    page_title="Agent ARCA",
    page_icon="🤖",
    layout="wide",
)

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
            st.warning("Gemini voice quota reached. Please type your question or wait 1–2 minutes.")
        elif "403" in error_text or "leaked" in error_text.lower():
            st.warning("Gemini API key issue detected. Please update your Gemini key in Streamlit secrets.")
        else:
            st.warning("Voice transcription failed. Please type your question instead.")

        return ""


def fetch_image_bytes(image_url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            image_url,
            headers=headers,
            timeout=15,
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

        metadata = item.get("metadata", {})
        if metadata:
            content += "### Performance Metadata\n\n"
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


def show_performance_dashboard(metadata):
    st.subheader("⚙️ Performance & Cost Awareness")

    if not metadata:
        st.info("No performance metadata available yet.")
        return

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Response Time", f"{metadata.get('response_time_seconds', 'N/A')}s")
    col2.metric("Estimated Tokens", metadata.get("total_tokens_estimate", "N/A"))
    col3.metric("Cost Level", metadata.get("estimated_cost_level", "N/A"))
    col4.metric("Sources", metadata.get("source_count", "N/A"))

    st.caption("Token and cost values are rough estimates for portfolio visibility, not exact billing values.")

    with st.expander("View workflow metadata"):
        st.markdown(f"**Workflow:** {metadata.get('workflow_type', 'N/A')}")
        st.markdown(f"**Input Tokens Estimate:** {metadata.get('input_tokens_estimate', 'N/A')}")
        st.markdown(f"**Output Tokens Estimate:** {metadata.get('output_tokens_estimate', 'N/A')}")
        st.markdown(f"**Total Tokens Estimate:** {metadata.get('total_tokens_estimate', 'N/A')}")
        st.markdown(f"**Estimated Cost Level:** {metadata.get('estimated_cost_level', 'N/A')}")


def show_source_reliability_panel(sources, metadata):
    st.subheader("🛡️ Source Reliability Ranking")

    if not sources:
        st.warning("No sources available for reliability ranking.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Overall Trust Score", f"{metadata.get('trust_score', 0)}/100")

    with col2:
        st.metric("Trust Level", metadata.get("trust_label", "N/A"))

    st.caption(metadata.get("trust_message", "Trust metadata unavailable."))

    for i, src in enumerate(sources, start=1):
        with st.expander(
            f"Source {i}: {src.get('source_name', 'Source')} — {src.get('reliability_label', 'Unknown')}"
        ):
            st.markdown(f"**Title:** {src.get('title', 'Untitled')}")
            st.markdown(f"**Domain/File:** {src.get('domain', 'N/A')}")
            st.markdown(f"**Type:** {src.get('type', 'unknown')}")
            st.markdown(f"**Reliability Score:** {src.get('reliability_score', 'N/A')}/100")
            st.markdown(f"**Reason:** {src.get('reliability_reason', 'Not available')}")

            if src.get("url", "").startswith("http"):
                st.markdown(f"[Open source]({src['url']})")


def show_research_dashboard(answer, sources, user_mode, analysis_mode, metadata):
    st.subheader("📊 Research Dashboard")

    source_count = len(sources)
    word_count = len(answer.split()) if answer else 0
    source_types = Counter([src.get("type", "unknown") for src in sources])

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Sources Used", source_count)
    col2.metric("Answer Length", f"{word_count} words")
    col3.metric("Mode", user_mode.replace(" Mode", ""))
    col4.metric("Analysis", analysis_mode)
    col5.metric("Trust", f"{metadata.get('trust_score', 0)}/100")

    st.markdown("### Source Breakdown")
    if source_types:
        for source_type, count in source_types.items():
            st.write(f"- **{source_type}**: {count}")
    else:
        st.write("No sources available.")

    st.markdown("### Quick Interpretation")
    trust_score = metadata.get("trust_score", 0)

    if source_count >= 4 and trust_score >= 75:
        st.success("Strong research coverage with decent source trust.")
    elif source_count >= 2:
        st.info("Moderate coverage. Add more high-quality sources for stronger verification.")
    else:
        st.warning("Limited source coverage. Add more PDFs, Word docs, images, URLs, or web search.")

    show_source_reliability_panel(sources, metadata)
    st.divider()
    show_performance_dashboard(metadata)


def show_saved_research_workspace():
    st.subheader("🗂️ Research Workspace")

    saved_count = len(st.session_state.saved_findings)

    st.caption("Save important ARCA responses here while researching. Download the full collection later.")

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

                metadata = item.get("metadata", {})
                if metadata:
                    st.markdown(f"**Trust Score:** {metadata.get('trust_score', 'N/A')}/100")
                    st.markdown(f"**Response Time:** {metadata.get('response_time_seconds', 'N/A')}s")

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
            label="⬇️ Download Saved Research Collection",
            data=markdown_file,
            file_name="ARCA_Saved_Research_Collection.md",
            mime="text/markdown",
            use_container_width=True,
        )


def show_exports():
    st.subheader("📄 Export Research Outputs")

    if not st.session_state.latest_student_answer:
        st.info("Run a research query first to enable exports.")
        return

    st.caption("Download professional reports and presentation decks from ARCA findings.")

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


def show_visuals_tab():
    st.subheader("🖼️ Visual Research Assistant")

    if not st.session_state.latest_student_answer:
        st.info("Run a research query first to generate visuals.")
        return

    st.caption(
        "Generate learning visuals, reference images, flowcharts, tree diagrams, and image prompts from your research."
    )

    col1, col2 = st.columns(2)

    with col1:
        max_reference_images = st.slider(
            "Reference images to fetch",
            min_value=3,
            max_value=10,
            value=6,
        )

    with col2:
        prefer_visual_trusted_sources = st.checkbox(
            "Prefer trusted image sources",
            value=True,
        )

    if st.button("Generate Visual Research Assets", use_container_width=True):
        with st.spinner("Generating diagrams, image prompts, and reference images..."):
            visuals = generate_visual_assets(
                question=st.session_state.latest_question,
                answer=st.session_state.latest_student_answer,
                user_mode=st.session_state.latest_user_mode,
                analysis_mode=st.session_state.latest_analysis_mode,
                max_reference_images=max_reference_images,
                prefer_trusted_sources=prefer_visual_trusted_sources,
            )

            st.session_state.latest_visuals = visuals

    visuals = st.session_state.latest_visuals

    if visuals:
        st.markdown("### Suggested Visual Search Query")
        st.code(visuals.get("visual_search_query", ""), language="text")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Flowchart")

            try:
                st.graphviz_chart(visuals.get("flowchart_dot", ""))
            except Exception:
                st.code(visuals.get("flowchart_dot", ""), language="dot")

            st.download_button(
                label="⬇️ Download Flowchart DOT",
                data=visuals.get("flowchart_dot", ""),
                file_name="arca_flowchart.dot",
                mime="text/plain",
                use_container_width=True,
            )

        with col2:
            st.markdown("### Tree Diagram")

            try:
                st.graphviz_chart(visuals.get("tree_dot", ""))
            except Exception:
                st.code(visuals.get("tree_dot", ""), language="dot")

            st.download_button(
                label="⬇️ Download Tree Diagram DOT",
                data=visuals.get("tree_dot", ""),
                file_name="arca_tree_diagram.dot",
                mime="text/plain",
                use_container_width=True,
            )

        st.divider()

        st.markdown("### Reference Images from Web")

        st.caption(
            "These are visual reference images found from the web. They are kept separate from written citations, but source links are preserved for credit and verification."
        )

        reference_images = visuals.get("reference_images", [])

        if not reference_images:
            st.info("No reference images found.")
        else:
            for i, image in enumerate(reference_images, start=1):
                image_url = image.get("image_url", "")
                source_url = image.get("source_url", "")
                description = image.get("description", "Reference image")

                with st.expander(f"Reference Image {i}", expanded=i <= 2):
                    st.markdown(f"**Description:** {description}")

                    if image_url:
                        image_bytes, content_type = fetch_image_bytes(image_url)

                        if image_bytes:
                            st.image(
                                image_bytes,
                                caption=description,
                                use_container_width=True,
                            )

                            file_extension = "jpg"

                            if content_type:
                                if "png" in content_type:
                                    file_extension = "png"
                                elif "webp" in content_type:
                                    file_extension = "webp"
                                elif "gif" in content_type:
                                    file_extension = "gif"

                            st.download_button(
                                label="⬇️ Download Image",
                                data=image_bytes,
                                file_name=f"arca_reference_image_{i}.{file_extension}",
                                mime=content_type or "image/jpeg",
                                use_container_width=True,
                            )
                        else:
                            st.warning(
                                "Image preview could not be fetched, but the original image link may still work."
                            )

                        st.markdown(f"[Open original image]({image_url})")

                    if source_url and source_url != image_url:
                        st.markdown(f"[Open source page]({source_url})")

        st.divider()

        st.markdown("### Descriptive AI Image Prompt")

        st.caption(
            "Use this prompt later with an image generation model to create an infographic, concept image, educational visual, or professional slide image."
        )

        st.text_area(
            "Generated image prompt",
            value=visuals.get("image_prompt", ""),
            height=220,
        )

        st.download_button(
            label="⬇️ Download Image Prompt",
            data=visuals.get("image_prompt", ""),
            file_name="arca_image_prompt.txt",
            mime="text/plain",
            use_container_width=True,
        )


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
        "latest_visuals": {},
        "saved_findings": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


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
        st.caption("Summaries, quizzes, learning guidance, and understanding evaluation.")
    else:
        st.info("💼 General Mode Active")
        st.caption("Professional research synthesis and decision intelligence.")

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
        st.caption("Best for comparing PDFs, docs, videos, images, and web results.")

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

    st.header("Web Search Controls")

    max_web_results = st.slider(
        "Number of web sources",
        min_value=2,
        max_value=10,
        value=5,
    )

    prefer_trusted_sources = st.checkbox(
        "Prefer trusted sources",
        value=True,
        help=(
            "Prioritizes sources like .gov, .edu, NIH, NCBI, CDC, WHO, "
            "arXiv, IEEE, ACM, Nature, and ScienceDirect when available."
        ),
    )

    st.caption("Use fewer sources for faster answers. Use more sources for deeper research.")

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
        st.session_state.latest_metadata = {}
        st.session_state.latest_visuals = {}
        st.rerun()


audio_input = st.audio_input("🎤 Ask using voice")
voice_question = ""

if audio_input:
    voice_question = transcribe_voice(audio_input)
    if voice_question:
        st.info(f"🗣️ You said: {voice_question}")

question = st.chat_input("Ask a research or learning question...")

if voice_question:
    question = voice_question


research_tab, dashboard_tab, visuals_tab, workspace_tab, exports_tab = st.tabs(
    [
        "🔎 Research",
        "📊 Dashboard",
        "🖼️ Visuals",
        "🗂️ Workspace",
        "📄 Exports",
    ]
)


with research_tab:
    for item in st.session_state.chat_history:
        role = item["role"]
        message = item["message"]
        raw_answer = item.get("raw_answer", message)
        sources = item.get("sources", [])

        with st.chat_message(role):
            if role == "assistant":
                st.markdown(message, unsafe_allow_html=True)

                if not raw_answer.startswith("⚠️ Gemini API quota"):
                    audio_file = create_audio_file(raw_answer)
                    if audio_file:
                        st.audio(audio_file, format="audio/mp3")

                if sources:
                    st.markdown("### Sources used")
                    for i, src in enumerate(sources, start=1):
                        st.markdown(
                            f"{i}. **Source {i}: {src.get('source_name', 'Source')}** — "
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

        with st.chat_message("assistant"):
            with st.spinner("ARCA is researching, ranking sources, and mapping evidence..."):
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
                        (item["role"], item["message"])
                        for item in st.session_state.chat_history
                    ],
                    max_web_results=max_web_results,
                    prefer_trusted_sources=prefer_trusted_sources,
                )

            st.session_state.research_context = result["context"]

            answer = result["answer"]
            sources = result["sources"]
            metadata = result.get("metadata", {})

            clickable_answer = make_clickable_source_markers(answer, sources)

            if analysis_mode == "Compare & Verify":
                st.markdown("### 🔍 Compare & Verify Response")
            elif user_mode == "Student Mode":
                st.markdown("### 🎓 Student Learning Response")
            else:
                st.markdown("### 💼 Research Intelligence Response")

            st.markdown(clickable_answer, unsafe_allow_html=True)

            if not answer.startswith("⚠️ Gemini API quota"):
                audio_file = create_audio_file(answer)
                if audio_file:
                    st.audio(audio_file, format="audio/mp3")

            if sources:
                st.markdown("### Sources used")
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
            st.session_state.latest_visuals = {}

        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "message": clickable_answer,
                "raw_answer": answer,
                "sources": sources,
            }
        )

    if st.session_state.latest_student_answer:
        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            if st.button("⭐ Save This Finding to Research Workspace", use_container_width=True):
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
                st.success("Saved to Research Workspace.")

        with col2:
            st.info("Use the Dashboard tab for trust score and performance. Use the Visuals tab for diagrams and image references.")

    if user_mode == "Student Mode" and st.session_state.latest_student_answer:
        st.divider()
        st.subheader("📝 Test Your Understanding")
        st.caption("Answer the quiz questions generated above to evaluate your understanding.")

        student_answers = st.text_area(
            "Write your quiz answers here",
            placeholder="1. ...\n2. ...\n3. ...",
            height=180,
        )

        if st.button("Evaluate My Understanding"):
            if not student_answers.strip():
                st.warning("Please write your answers first.")
            else:
                with st.spinner("Evaluating your understanding..."):
                    feedback = evaluate_quiz_answers(
                        original_answer=st.session_state.latest_student_answer,
                        student_answers=student_answers,
                    )
                st.session_state.latest_quiz_feedback = feedback

        if st.session_state.latest_quiz_feedback:
            st.markdown("### 📊 Quiz Feedback")
            st.markdown(st.session_state.latest_quiz_feedback)


with dashboard_tab:
    if st.session_state.latest_student_answer:
        show_research_dashboard(
            answer=st.session_state.latest_student_answer,
            sources=st.session_state.latest_sources,
            user_mode=st.session_state.latest_user_mode,
            analysis_mode=st.session_state.latest_analysis_mode,
            metadata=st.session_state.latest_metadata,
        )
    else:
        st.info("Run a research query first to view dashboard metrics.")


with visuals_tab:
    show_visuals_tab()


with workspace_tab:
    show_saved_research_workspace()


with exports_tab:
    show_exports()
