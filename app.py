import re
import tempfile

import streamlit as st
from gtts import gTTS
from pipeline import run_pipeline

st.set_page_config(page_title="Agent ARCA", page_icon="🤖", layout="wide")

st.title("🤖 Agent ARCA")
st.caption("AI research assistant for URLs, PDFs, and web research with source-backed answers.")


def make_clickable_citations(answer, sources):
    for src in sources:
        name = src.get("source_name", "")
        url = src.get("url", "")

        if not name or not url:
            continue

        escaped_name = re.escape(name)

        answer = re.sub(
            rf"\[{escaped_name}\]",
            f'<a href="{url}" target="_blank">[{name}]</a>',
            answer,
        )

    return answer


def create_audio_file(text):
    clean_text = re.sub(r"<[^>]+>", "", text)
    clean_text = re.sub(r"\[|\]|\(|\)", "", clean_text)

    tts = gTTS(clean_text)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tts.save(temp_file.name)

    return temp_file.name


if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "research_context" not in st.session_state:
    st.session_state.research_context = None

with st.sidebar:
    st.header("Research Sources")

    mode = st.radio(
        "Choose mode",
        [
            "Use my sources",
            "Search the web",
            "Use my sources + web search",
        ],
    )

    urls_input = st.text_area(
        "Paste URLs, one per line",
        placeholder="https://example.com/article\nhttps://example.com/paper",
    )

    uploaded_pdfs = st.file_uploader(
        "Upload PDF files",
        type=["pdf"],
        accept_multiple_files=True,
    )

    st.divider()

    if st.button("Clear Chat"):
        st.session_state.chat_history = []
        st.session_state.research_context = None
        st.rerun()


question = st.chat_input("Ask a research question...")

for index, item in enumerate(st.session_state.chat_history):
    role = item["role"]
    message = item["message"]
    raw_answer = item.get("raw_answer", message)

    with st.chat_message(role):
        if role == "assistant":
            st.markdown(message, unsafe_allow_html=True)

            audio_file = create_audio_file(raw_answer)
            st.audio(audio_file, format="audio/mp3")

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
        with st.spinner("ARCA is researching..."):
            result = run_pipeline(
                question=question,
                urls=urls,
                uploaded_pdfs=uploaded_pdfs,
                mode=mode,
                previous_context=st.session_state.research_context,
                chat_history=[
                    (item["role"], item["message"])
                    for item in st.session_state.chat_history
                ],
            )

        st.session_state.research_context = result["context"]

        answer = result["answer"]
        clickable_answer = make_clickable_citations(answer, result["sources"])

        st.markdown(clickable_answer, unsafe_allow_html=True)

        audio_file = create_audio_file(answer)
        st.audio(audio_file, format="audio/mp3")

        if result["sources"]:
            st.divider()
            st.markdown("### Sources used")
            for i, src in enumerate(result["sources"], start=1):
                st.markdown(
                    f"{i}. [{src['source_name']} — {src['title']}]({src['url']})"
                )

    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "message": clickable_answer,
            "raw_answer": answer,
        }
    )
