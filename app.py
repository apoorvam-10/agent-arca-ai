import streamlit as st
from pipeline import run_pipeline

st.set_page_config(page_title="Agent ARCA", page_icon="🤖", layout="centered")

st.title("🤖 Agent ARCA - AI Research Assistant")
st.caption("Research topics from URLs with AI-generated summaries and evaluation metrics.")

if "chat" not in st.session_state:
    st.session_state.chat = []

user_input = st.text_input("Ask your research question:")
sources_input = st.text_area(
    "Paste URLs (one per line):",
    placeholder="https://en.wikipedia.org/wiki/Artificial_intelligence\nhttps://example.com/article",
)

sources = [s.strip() for s in sources_input.split("\n") if s.strip()]

col1, col2 = st.columns([1, 1])
with col1:
    run_clicked = st.button("Run Agent", use_container_width=True)
with col2:
    clear_clicked = st.button("Clear Chat", use_container_width=True)

if clear_clicked:
    st.session_state.chat = []
    st.rerun()

if run_clicked:
    if not user_input.strip():
        st.warning("Please enter a research question.")
    elif not sources:
        st.warning("Please add at least one URL.")
    else:
        st.session_state.chat.append(("user", user_input.strip()))

        with st.spinner("Running AI agents..."):
            synthesis, evaluation = run_pipeline(user_input.strip(), sources)

        response = f"""
### 📌 Summary
{synthesis["summary"]}

### 📊 Evaluation
- **Readability:** {evaluation["readability"]}
- **Coverage:** {evaluation["coverage"]}
- **Confidence:** {evaluation["confidence"]}
"""

        st.session_state.chat.append(("ai", response))
        st.rerun()

st.divider()

for role, msg in st.session_state.chat:
    if role == "user":
        with st.chat_message("user"):
            st.markdown(msg)
    else:
        with st.chat_message("assistant"):
            st.markdown(msg)
