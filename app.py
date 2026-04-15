import streamlit as st
from pipeline import run_pipeline

st.set_page_config(page_title="Agent ARCA", page_icon="🤖")

st.title("🤖 Agent ARCA - AI Research Assistant")

# Session state for chat history
if "chat" not in st.session_state:
    st.session_state.chat = []

user_input = st.text_input("Ask your research question:")

sources = [
    "https://en.wikipedia.org/wiki/Artificial_intelligence"
]

if st.button("Run Agent") and user_input:
    st.session_state.chat.append(("user", user_input))

    with st.spinner("Running AI agents..."):
        synthesis, evaluation = run_pipeline(user_input, sources)

    response = f"""
📌 **Summary**
{synthesis['summary']}

📊 **Evaluation**
- Readability: {evaluation['readability']}
- Coverage: {evaluation['coverage']}
- Confidence: {evaluation['confidence']}
"""

    st.session_state.chat.append(("ai", response))

# Display chat
for role, msg in st.session_state.chat:
    if role == "user":
        st.markdown(f"**🧑 You:** {msg}")
    else:
        st.markdown(f"**🤖 ARCA:** {msg}")
