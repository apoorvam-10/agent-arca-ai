from typing import List, Dict, Any
import re
import os
import tempfile
from io import BytesIO

import fitz
import requests
import streamlit as st
from bs4 import BeautifulSoup
import google.generativeai as genai
from tavily import TavilyClient
from youtube_transcript_api import YouTubeTranscriptApi
import webvtt
import yt_dlp

from docx import Document


def get_gemini_model():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY in Streamlit secrets.")

    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-3-flash-preview")


def get_tavily_client():
    api_key = st.secrets.get("TAVILY_API_KEY", "")
    if not api_key:
        raise ValueError("Missing TAVILY_API_KEY in Streamlit secrets.")

    return TavilyClient(api_key=api_key)


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
            "youtube": "YouTube",
            "youtu": "YouTube",
        }

        return known_names.get(name.lower(), name.upper())
    except Exception:
        return title[:20] if title else "Source"


def get_youtube_video_id(url: str) -> str:
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0].split("&")[0]

    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]

    match = re.search(r"embed/([^?&/]+)", url)
    if match:
        return match.group(1)

    return ""


def extract_youtube_transcript(url: str) -> Dict[str, Any]:
    video_id = get_youtube_video_id(url)

    if not video_id:
        return {
            "title": "YouTube Video",
            "source_name": "YouTube",
            "url": url,
            "text": "Could not detect a valid YouTube video ID.",
            "type": "video_error",
        }

    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        text = " ".join([item["text"] for item in transcript])

        if text.strip():
            return {
                "title": f"YouTube Video Transcript ({video_id})",
                "source_name": "YouTube",
                "url": url,
                "text": text[:15000],
                "type": "video",
            }
    except Exception:
        pass

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

            ydl_opts = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en", "en-US"],
                "subtitlesformat": "vtt",
                "outtmpl": output_template,
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", f"YouTube Video ({video_id})")

            transcript_parts = []

            for file_name in os.listdir(temp_dir):
                if file_name.endswith(".vtt"):
                    vtt_path = os.path.join(temp_dir, file_name)

                    for caption in webvtt.read(vtt_path):
                        caption_text = caption.text.replace("\n", " ").strip()
                        if caption_text:
                            transcript_parts.append(caption_text)

            text = " ".join(transcript_parts)

            if text.strip():
                return {
                    "title": title,
                    "source_name": "YouTube",
                    "url": url,
                    "text": text[:15000],
                    "type": "video",
                }

    except Exception as e:
        return {
            "title": "YouTube Video",
            "source_name": "YouTube",
            "url": url,
            "text": (
                "Could not fetch captions/transcript for this YouTube video. "
                f"Technical detail: {str(e)}"
            ),
            "type": "video_error",
        }

    return {
        "title": "YouTube Video",
        "source_name": "YouTube",
        "url": url,
        "text": (
            "No accessible captions or transcript were found for this video. "
            "Try a YouTube video with English captions, or paste the transcript manually."
        ),
        "type": "video_error",
    }


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


def build_prompt(
    question: str,
    sources: List[Dict[str, Any]],
    previous_context: str,
    chat_history: List[Any],
    user_mode: str,
    analysis_mode: str,
) -> str:
    source_blocks = []

    for i, src in enumerate(sources, start=1):
        source_blocks.append(
            f"""
Source {i}
Source name: {src["source_name"]}
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

    if user_mode == "Student Mode":
        mode_instruction = """
You are operating in Student Mode.

Your goals:
- explain concepts clearly and simply
- help users understand and retain information
- simplify technical language
- identify important concepts
- focus on learning and understanding
- provide beginner-friendly explanations

At the end include:
## Quiz
Generate 3 short questions to test understanding.

## Areas to Focus On
Mention concepts the student should revise further.
"""
    else:
        mode_instruction = """
You are operating in General Mode.

Your goals:
- provide professional research synthesis
- focus on insights and decision-making
- keep explanations concise and structured
- highlight actionable findings
- provide executive-style summaries
"""

    if analysis_mode == "Compare & Verify":
        output_format = """
Return this exact format:

## Executive Answer
Give the clearest answer to the user's question.

## Agreements Across Sources
List the main points that multiple sources agree on.

## Conflicting Information
List contradictions, disagreements, or differences between sources. If none are found, say so.

## Strongest Evidence
Explain which sources appear most useful or evidence-backed and why.

## Weak or Missing Evidence
Mention what is unclear, unsupported, missing, or not verified.

## Final Consensus
Give a balanced conclusion based on the sources.

## Confidence Assessment
Rate confidence as Low, Medium, or High and explain why.

## Simple Summary
Explain the conclusion in very simple words.
"""
    else:
        output_format = """
Return this format:

## Answer
Clear answer.

## Key Points
- Point 1
- Point 2
- Point 3

## Simple Summary
Explain in very simple words.

## What I verified from sources
Briefly say what was supported by the sources.

## Limits
Mention anything that was unclear or not available from the sources.
"""

    return f"""
You are Agent ARCA, a trustworthy AI research assistant.

{mode_instruction}

Analysis mode:
{analysis_mode}

Your job:
- Answer the user's question using the provided sources.
- Do not include citations inside the answer.
- Do not include source names or URLs inside the answer body.
- The app will show clickable sources separately below the answer.
- If the sources do not contain enough evidence, say that clearly.
- Be simple enough for non-technical users.
- Do not invent facts.
- Keep the answer structured and easy to read.
- If Compare & Verify mode is active, compare sources against each other instead of only summarizing them.

User question:
{question}

Previous research context:
{previous_context if previous_context else "No previous context yet."}

Recent conversation:
{chat_text if chat_text else "No previous conversation."}

Sources:
{sources_text}

{output_format}
""".strip()


def evaluate_answer(answer: str, source_count: int) -> Dict[str, float]:
    readability = min(1.0, len(answer) / 1500)
    coverage = min(1.0, source_count / 5)
    confidence = round((readability + coverage) / 2, 2)

    return {
        "readability": round(readability, 2),
        "coverage": round(coverage, 2),
        "confidence": confidence,
    }


def evaluate_quiz_answers(original_answer: str, student_answers: str) -> str:
    model = get_gemini_model()

    prompt = f"""
You are Agent ARCA in Student Mode.

The student studied this material:

{original_answer}

The student answered the quiz like this:

{student_answers}

Evaluate the student's understanding.

Return this format:

## Score
Give a score out of 10.

## What You Got Right
List strengths.

## What Needs Improvement
List weak areas.

## Corrected Explanation
Explain the missed concepts in simple words.

## Suggested Revision Plan
Give 3 focused revision steps.
""".strip()

    response = model.generate_content(prompt)
    feedback = getattr(response, "text", "").strip()

    if not feedback:
        feedback = "I could not evaluate the quiz answers."

    return feedback


def generate_word_report(
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
    user_mode: str,
):
    doc = Document()

    doc.add_heading("Agent ARCA Research Report", level=1)

    doc.add_heading("Mode", level=2)
    doc.add_paragraph(user_mode)

    doc.add_heading("Research Question", level=2)
    doc.add_paragraph(question)

    doc.add_heading("Generated Findings", level=2)
    doc.add_paragraph(answer)

    doc.add_heading("Sources Used", level=2)

    for i, src in enumerate(sources, start=1):
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{i}. {src['source_name']} — ").bold = True
        p.add_run(src["title"])
        p.add_run(f"\n{src['url']}")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer


def run_pipeline(
    question: str,
    urls: List[str],
    uploaded_pdfs,
    mode: str,
    user_mode: str,
    analysis_mode: str,
    previous_context: str = None,
    chat_history: List[Any] = None,
) -> Dict[str, Any]:
    all_sources = []

    if mode in ["Use my sources", "Use my sources + web search"]:
        for url in urls:
            if "youtube.com" in url or "youtu.be" in url:
                all_sources.append(extract_youtube_transcript(url))
            else:
                all_sources.append(fetch_url_text(url))

        if uploaded_pdfs:
            for pdf in uploaded_pdfs:
                all_sources.append(extract_pdf_text(pdf))

    should_search_web = (
        mode in ["Search the web", "Use my sources + web search"]
        or len(all_sources) == 0
    )

    if should_search_web:
        web_sources = search_web(question)
        all_sources.extend(web_sources)

    model = get_gemini_model()

    prompt = build_prompt(
        question=question,
        sources=all_sources,
        previous_context=previous_context or "",
        chat_history=chat_history or [],
        user_mode=user_mode,
        analysis_mode=analysis_mode,
    )

    response = model.generate_content(prompt)
    answer = getattr(response, "text", "").strip()

    if not answer:
        answer = "I could not generate an answer from the available sources."

    new_context = f"""
Last question: {question}

Analysis mode: {analysis_mode}

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
