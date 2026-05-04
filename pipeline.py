from typing import List, Dict, Any

import fitz
import requests
import streamlit as st
from bs4 import BeautifulSoup
import google.generativeai as genai
from tavily import TavilyClient


# -------------------------
# GEMINI SETUP
# -------------------------
def get_gemini_model():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY in Streamlit secrets.")

    genai.configure(api_key=api_key)

    # Use the model that already worked for your app.
    return genai.GenerativeModel("gemini-3-flash-preview")


# -------------------------
# TAVILY SETUP
# -------------------------
def get_tavily_client():
    api_key = st.secrets.get("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("Missing TAVILY_API_KEY in Streamlit secrets.")

    return TavilyClient(api_key=api_key)


# -------------------------
# SOURCE NAME CLEANER
# -------------------------
def get_source_name(url: str, title: str = "") -> str:
    try:
        domain = url.split("//")[-1].split("/")[0]
        name = domain.replace("www.", "").split(".")[0]

        known_names = {
            "ibm": "IBM",
            "who": "WHO",
            "nih": "NIH",
            "ncbi": "NCBI",
            "pmc": "PMC",
            "cdc": "CDC",
            "fda": "FDA",
            "microsoft": "Microsoft",
            "google": "Google",
            "openai": "OpenAI",
            "nature": "Nature",
            "sciencedirect": "ScienceDirect",
            "wikipedia": "Wikipedia",
            "arxiv": "arXiv",
            "mayoclinic": "Mayo Clinic",
            "healthline": "Healthline",
            "webmd": "WebMD",
            "stanford": "Stanford",
            "harvard": "Harvard",
            "mit": "MIT",
        }

        return known_names.get(name.lower(), name.upper())
    except Exception:
        return title[:20] if title else "Source"


# -------------------------
# URL READER
# -------------------------
def fetch_url_text(url: str) -> Dict[str, Any]:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else url

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paragraphs if p)

        if not text:
            text = soup.get_text(" ", strip=True)

        source_name = get_source_name(url, title)

        return {
            "title": title,
            "source_name": source_name,
            "url": url,
            "text": text[:12000],
            "type": "url",
        }

    except Exception as e:
        return {
            "title": f"Failed to read URL: {url}",
            "source_name": "Source",
            "url": url,
            "text": f"Error: {str(e)}",
            "type": "url_error",
        }


# -------------------------
# PDF READER
# -------------------------
def extract_pdf_text(uploaded_pdf) -> Dict[str, Any]:
    try:
        pdf_bytes = uploaded_pdf.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        pages = []
        for page in doc:
            pages.append(page.get_text())

        text = "\n".join(pages)
        title = uploaded_pdf.name

        source_name = (
            title.replace(".pdf", "")
            .replace("_", " ")
            .replace("-", " ")
            .strip()[:25]
        )

        if not source_name:
            source_name = "PDF"

        return {
            "title": title,
            "source_name": source_name,
            "url": title,
            "text": text[:15000],
            "type": "pdf",
        }

    except Exception as e:
        return {
            "title": uploaded_pdf.name,
            "source_name": "PDF",
            "url": uploaded_pdf.name,
            "text": f"Error reading PDF: {str(e)}",
            "type": "pdf_error",
        }


# -------------------------
# WEB SEARCH
# -------------------------
def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    client = get_tavily_client()

    search_result = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_answer=False,
        include_raw_content=True,
    )

    sources = []

    for item in search_result.get("results", []):
        title = item.get("title") or item.get("url", "Untitled Source")
        url = item.get("url", "")
        content = item.get("raw_content") or item.get("content") or ""
        source_name = get_source_name(url, title)

        sources.append(
            {
                "title": title,
                "source_name": source_name,
                "url": url,
                "text": content[:12000],
                "type": "web_search",
            }
        )

    return sources


# -------------------------
# PROMPT BUILDER
# -------------------------
def build_prompt(
    question: str,
    sources: List[Dict[str, Any]],
    previous_context: str,
    chat_history: List[Any],
) -> str:
    source_blocks = []

    for i, src in enumerate(sources, start=1):
        source_blocks.append(
            f"""
Source {i}
Citation name to use in answer: [{src["source_name"]}]
Title: {src["title"]}
URL: {src["url"]}
Type: {src["type"]}
Content:
{src["text"]}
"""
        )

    sources_text = "\n\n".join(source_blocks)

    recent_chat = chat_history[-6:] if chat_history else []
    chat_text = "\n".join([f"{role}: {msg}" for role, msg in recent_chat])

    return f"""
You are Agent ARCA, a trustworthy AI research assistant.

Your job:
- Answer the user's question using only the provided sources.
- Use short source citations exactly like [IBM], [WHO], [NCBI], [PMC], [Wikipedia], etc.
- Do NOT include full URLs in the answer.
- Do NOT use markdown links like [IBM](url).
- Do NOT use long citations like [Source 1].
- The app will make citations clickable later, so only write the short citation name in square brackets.
- If the sources do not contain enough evidence, say that clearly.
- Be simple enough for non-technical users.
- Do not invent citations or sources.
- Keep the answer structured and easy to read.

User question:
{question}

Previous research context:
{previous_context if previous_context else "No previous context yet."}

Recent conversation:
{chat_text if chat_text else "No previous conversation."}

Sources:
{sources_text}

Return this format:

## Answer
Clear answer with short citations like [IBM].

## Key Points
- Point 1 [SourceName]
- Point 2 [SourceName]
- Point 3 [SourceName]

## Simple Summary
Explain in very simple words.

## What I verified from sources
Briefly say what was supported by the sources.

## Limits
Mention anything that was unclear or not available from the sources.
""".strip()


# -------------------------
# EVALUATION
# -------------------------
def evaluate_answer(answer: str, source_count: int) -> Dict[str, float]:
    readability = min(1.0, len(answer) / 1500)
    coverage = min(1.0, source_count / 5)
    confidence = round((readability + coverage) / 2, 2)

    return {
        "readability": round(readability, 2),
        "coverage": round(coverage, 2),
        "confidence": confidence,
    }


# -------------------------
# MAIN PIPELINE
# -------------------------
def run_pipeline(
    question: str,
    urls: List[str],
    uploaded_pdfs,
    mode: str,
    previous_context: str = None,
    chat_history: List[Any] = None,
) -> Dict[str, Any]:
    all_sources = []

    # 1. Read user-provided URLs and PDFs
    if mode in ["Use my sources", "Use my sources + web search"]:
        for url in urls:
            all_sources.append(fetch_url_text(url))

        if uploaded_pdfs:
            for pdf in uploaded_pdfs:
                all_sources.append(extract_pdf_text(pdf))

    # 2. Search web if requested OR if no source was provided
    should_search_web = (
        mode in ["Search the web", "Use my sources + web search"]
        or len(all_sources) == 0
    )

    if should_search_web:
        web_sources = search_web(question)
        all_sources.extend(web_sources)

    # 3. Generate answer
    model = get_gemini_model()

    prompt = build_prompt(
        question=question,
        sources=all_sources,
        previous_context=previous_context or "",
        chat_history=chat_history or [],
    )

    response = model.generate_content(prompt)
    answer = getattr(response, "text", "").strip()

    if not answer:
        answer = "I could not generate an answer from the available sources."

    # 4. Save compact context for follow-up questions
    new_context = f"""
Last question: {question}

Last answer:
{answer[:3000]}

Sources used:
{", ".join([src["source_name"] for src in all_sources])}
""".strip()

    evaluation = evaluate_answer(answer, len(all_sources))

    return {
        "answer": answer,
        "sources": [
            {
                "title": src["title"],
                "source_name": src["source_name"],
                "url": src["url"],
                "type": src["type"],
            }
            for src in all_sources
        ],
        "context": new_context,
        "evaluation": evaluation,
    }
