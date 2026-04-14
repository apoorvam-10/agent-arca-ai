import streamlit as st
from pipeline import run_pipeline

st.title("🧠 Agent ARCA - AI Research Assistant")

query = st.text_input("Enter research topic")
source = st.text_area("Paste URL or PDF path")

if st.button("Run ARCA"):
    with st.spinner("Running AI agents..."):

        synthesis, evaluation = run_pipeline(query, [source])

    st.subheader("📌 Summary")
    st.write(synthesis["summary"])

    st.subheader("📊 Evaluation")
    st.json(evaluation)