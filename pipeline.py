from typing import Dict, List

import requests
import streamlit as st
from bs4 import BeautifulSoup
import google.generativeai as genai


# -------------------------
# MEMORY STORE
# -------------------------
memory_store: Dict[str, str] = {}


def save_memory(query: str, summary: str) -> None:
    memory_store[query] = summary


def get_memory(query: str) -> str:
    return memory_store.get(query, "")


# -------------------------
# GEMINI SETUP
# -------------------------
def get_model():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError(
            "Missing GEMINI_API_KEY in Streamlit secrets. "
            "Add it in your app settings under Secrets."
        )

    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-3-flash-preview")


# -------------------------
# HELPERS
# -------------------------
def enhance_query(query: str) -> str:
    return f"Research Request: {query}"


def fetch_web_text(url: str) -> str:
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paragraphs if p)

        if not text.strip():
            text = soup.get_text(" ", strip=True)

        return text[:12000]
    except Exception as exc:
        return f"Error fetching {url}: {exc}"


def build_prompt(query: str, combined_text: str, sources: List[str], memory: str) -> str:
    sources_block = "\n".join(f"- {src}" for src in sources)

    return f"""
You are Agent ARCA, an AI research assistant.

Task:
- Summarize the research topic clearly and accurately
- Extract the most important insights
- Keep the answer structured and concise
- Mention patterns or themes across sources when possible
- If content is weak or incomplete, say so honestly

User Query:
{query}

Sources:
{sources_block}

Previous memory for this exact query:
{memory if memory else "No previous memory."}

Source content:
{combined_text}

Return this format:
1. Short overview
2. Key insights (3 to 5 bullets)
3. Final takeaway
""".strip()


# -------------------------
# MAIN PIPELINE
# -------------------------
def run_pipeline(query: str, sources: List[str]):
    enhanced_query = enhance_query(query)
    previous_memory = get_memory(enhanced_query)

    collected_chunks = []
    processed_sources = []

    for source in sources:
        text = fetch_web_text(source)
        collected_chunks.append(f"\nSOURCE: {source}\n{text}\n")
        processed_sources.append(source)

    combined_text = "\n".join(collected_chunks)[:20000]

    model = get_model()
    prompt = build_prompt(enhanced_query, combined_text, processed_sources, previous_memory)
    response = model.generate_content(prompt)
    summary = getattr(response, "text", "").strip()

    if not summary:
        summary = "No summary was generated."

    save_memory(enhanced_query, summary)

    summary_words = summary.split()
    readability = min(1.0, len(summary) / 1200)
    coverage = min(1.0, len(set(summary_words)) / 120) if summary_words else 0.0
    confidence = round((readability + coverage) / 2, 2)

    synthesis = {
        "summary": summary
    }

    evaluation = {
        "readability": round(readability, 2),
        "coverage": round(coverage, 2),
        "confidence": confidence
    }

    return synthesis, evaluation
