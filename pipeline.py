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
from pptx import Presentation

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet


def get_gemini_model():
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY in Streamlit secrets.")

    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-3-flash-preview")


def safe_generate_content(prompt: str) -> str:
    try:
        model = get_gemini_model()
        response = model.generate_content(prompt)
        text = getattr(response, "text", "").strip()

        if not text:
            return "I could not generate a response from the available information."

        return text

    except Exception as e:
        error_text = str(e)

        if "429" in error_text or "ResourceExhausted" in error_text or "quota" in error_text.lower():
            return (
                "⚠️ Gemini API quota limit reached. Please wait 1–2 minutes and try again. "
                "This usually happens on the free tier after several requests."
            )

        return f"⚠️ AI generation failed. Please try again. Technical detail: {error_text[:300]}"


def safe_generate_multimodal_content(parts: list) -> str:
    try:
        model = get_gemini_model()
        response = model.generate_content(parts)
        text = getattr(response, "text", "").strip()

        if not text:
            return "I could not extract useful information from this image."

        return text

    except Exception as e:
        error_text = str(e)

        if "429" in error_text or "ResourceExhausted" in error_text or "quota" in error_text.lower():
            return "Gemini quota reached while reading image. Please wait 1–2 minutes and try again."

        return f"Image reading failed. Technical detail: {error_text[:300]}"


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
            "text": f"Could not fetch captions/transcript for this YouTube video. Technical detail: {str(e)}",
            "type": "video_error",
        }

    return {
        "title": "YouTube Video",
        "source_name": "YouTube",
        "url": url,
        "text": "No accessible captions or transcript were found for this video.",
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

        return {
            "title": title,
            "source_name": get_source_name(url, title),
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

        text = "\n".join([page.get_text() for page in doc])
        title = uploaded_pdf.name

        source_name = (
            title.replace(".pdf", "")
            .replace("_", " ")
            .replace("-", " ")
            .strip()[:25]
        ) or "PDF"

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


def extract_docx_text(uploaded_docx) -> Dict[str, Any]:
    try:
        doc = Document(uploaded_docx)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        text = "\n".join(paragraphs)

        title = uploaded_docx.name
        source_name = (
            title.replace(".docx", "")
            .replace("_", " ")
            .replace("-", " ")
            .strip()[:25]
        ) or "DOCX"

        return {
            "title": title,
            "source_name": source_name,
            "url": title,
            "text": text[:15000],
            "type": "docx",
        }

    except Exception as e:
        return {
            "title": uploaded_docx.name,
            "source_name": "DOCX",
            "url": uploaded_docx.name,
            "text": f"Error reading DOCX: {str(e)}",
            "type": "docx_error",
        }


def extract_image_text(uploaded_image) -> Dict[str, Any]:
    try:
        image_bytes = uploaded_image.read()
        mime_type = uploaded_image.type or "image/png"

        prompt = """
You are Agent ARCA's image reading tool.

Read and understand this image. Extract:
- visible text
- key information
- table or chart details if present
- important visual observations
- anything useful for research or studying

Return concise but complete extracted content.
""".strip()

        extracted_text = safe_generate_multimodal_content(
            [
                prompt,
                {
                    "mime_type": mime_type,
                    "data": image_bytes,
                },
            ]
        )

        title = uploaded_image.name
        source_name = (
            title.replace(".png", "")
            .replace(".jpg", "")
            .replace(".jpeg", "")
            .replace("_", " ")
            .replace("-", " ")
            .strip()[:25]
        ) or "IMAGE"

        return {
            "title": title,
            "source_name": source_name,
            "url": title,
            "text": extracted_text[:15000],
            "type": "image",
        }

    except Exception as e:
        return {
            "title": uploaded_image.name,
            "source_name": "IMAGE",
            "url": uploaded_image.name,
            "text": f"Error reading image: {str(e)}",
            "type": "image_error",
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

        sources.append(
            {
                "title": title,
                "source_name": get_source_name(url, title),
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
- explain clearly and simply
- help the user learn and retain information
- identify important concepts
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
- highlight actionable findings
- provide executive-style summaries
"""

    if analysis_mode == "Compare & Verify":
        output_format = """
Return this exact format:

## Key Takeaway
Give one clear sentence that captures the final conclusion.

## Executive Answer
Give the clearest answer to the user's question.

## Agreements Across Sources
List points that multiple sources agree on.

## Conflicting Information
List contradictions or differences between sources. If none are found, say so.

## Strongest Evidence
Explain which sources appear most useful or evidence-backed and why.

## Weak or Missing Evidence
Mention what is unclear, unsupported, missing, or not verified.

## Final Consensus
Give a balanced conclusion.

## Confidence Assessment
Rate confidence as Low, Medium, or High and explain why.

## Simple Summary
Explain the conclusion in very simple words.

## Suggested Follow-Up Questions
Give 3 useful follow-up questions the user can ask next.

## Recommended Next Steps
Give 3 practical next steps based on the findings.
"""
    else:
        output_format = """
Return this format:

## Key Takeaway
Give one clear sentence that captures the most important finding.

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

## Suggested Follow-Up Questions
Give 3 useful follow-up questions the user can ask next.

## Recommended Next Steps
Give 3 practical next steps based on the answer.
"""

    return f"""
You are Agent ARCA, a trustworthy AI research assistant.

{mode_instruction}

Analysis mode:
{analysis_mode}

Your job:
- Answer the user's question using the provided sources.
- Do not include source names or URLs inside the answer body.
- The app will show clickable sources separately below the answer.
- If evidence is insufficient, say so clearly.
- Do not invent facts.
- Keep the answer structured and easy to read.
- If Compare & Verify mode is active, compare sources against each other.

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
Explain missed concepts simply.

## Suggested Revision Plan
Give 3 focused revision steps.
""".strip()

    return safe_generate_content(prompt)


def clean_export_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("##", "")
    text = text.replace("*", "")
    return text.strip()


def make_paragraph_safe(text: str) -> str:
    text = clean_export_text(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def generate_word_report(
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
    user_mode: str,
    analysis_mode: str,
    quiz_feedback: str = "",
):
    clean_answer = clean_export_text(answer)
    clean_feedback = clean_export_text(quiz_feedback) if quiz_feedback else ""

    doc = Document()

    doc.add_heading("Agent ARCA Research Report", level=0)

    doc.add_paragraph(
        "Generated by Agent ARCA — an AI-powered multimodal research, learning, and decision-intelligence assistant."
    )

    doc.add_heading("Report Overview", level=1)
    doc.add_paragraph(f"Mode: {user_mode}")
    doc.add_paragraph(f"Analysis Type: {analysis_mode}")
    doc.add_paragraph(f"Sources Used: {len(sources)}")

    doc.add_heading("Research Question", level=1)
    doc.add_paragraph(question)

    doc.add_heading("Generated Findings", level=1)
    doc.add_paragraph(clean_answer)

    if clean_feedback:
        doc.add_heading("Student Quiz Feedback", level=1)
        doc.add_paragraph(clean_feedback)

    doc.add_heading("Research Dashboard", level=1)
    doc.add_paragraph(f"Source Count: {len(sources)}")
    doc.add_paragraph(f"Answer Length: {len(answer.split())} words")

    source_types = {}
    for src in sources:
        source_types[src["type"]] = source_types.get(src["type"], 0) + 1

    for source_type, count in source_types.items():
        doc.add_paragraph(f"{source_type}: {count}")

    doc.add_heading("Sources Used", level=1)

    for i, src in enumerate(sources, start=1):
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(f"{i}. {src['source_name']} — ").bold = True
        p.add_run(src["title"])
        p.add_run(f"\n{src['url']}")

    doc.add_heading("Suggested Next Steps", level=1)
    doc.add_paragraph("1. Review the generated findings.")
    doc.add_paragraph("2. Open and verify the listed sources.")
    doc.add_paragraph("3. Ask follow-up questions in ARCA.")
    doc.add_paragraph("4. Export a presentation deck if needed.")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer


def generate_pdf_report(
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
    user_mode: str,
    analysis_mode: str,
    quiz_feedback: str = "",
):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)

    styles = getSampleStyleSheet()
    story = []

    clean_answer = make_paragraph_safe(answer)
    clean_feedback = make_paragraph_safe(quiz_feedback) if quiz_feedback else ""

    story.append(Paragraph("Agent ARCA Research Report", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(
        "Generated by Agent ARCA — an AI-powered multimodal research, learning, and decision-intelligence assistant.",
        styles["BodyText"],
    ))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Report Overview", styles["Heading1"]))
    story.append(Paragraph(f"Mode: {user_mode}", styles["BodyText"]))
    story.append(Paragraph(f"Analysis Type: {analysis_mode}", styles["BodyText"]))
    story.append(Paragraph(f"Sources Used: {len(sources)}", styles["BodyText"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Research Question", styles["Heading1"]))
    story.append(Paragraph(make_paragraph_safe(question), styles["BodyText"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Generated Findings", styles["Heading1"]))

    for paragraph in clean_answer.split("\n"):
        if paragraph.strip():
            story.append(Paragraph(paragraph.strip(), styles["BodyText"]))
            story.append(Spacer(1, 6))

    if clean_feedback:
        story.append(PageBreak())
        story.append(Paragraph("Student Quiz Feedback", styles["Heading1"]))
        for paragraph in clean_feedback.split("\n"):
            if paragraph.strip():
                story.append(Paragraph(paragraph.strip(), styles["BodyText"]))
                story.append(Spacer(1, 6))

    story.append(PageBreak())
    story.append(Paragraph("Research Dashboard", styles["Heading1"]))
    story.append(Paragraph(f"Source Count: {len(sources)}", styles["BodyText"]))
    story.append(Paragraph(f"Answer Length: {len(answer.split())} words", styles["BodyText"]))
    story.append(Spacer(1, 12))

    source_types = {}
    for src in sources:
        source_types[src["type"]] = source_types.get(src["type"], 0) + 1

    for source_type, count in source_types.items():
        story.append(Paragraph(f"{source_type}: {count}", styles["BodyText"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Sources Used", styles["Heading1"]))

    for i, src in enumerate(sources, start=1):
        source_text = f"{i}. {src['source_name']} — {src['title']}<br/>{src['url']}"
        story.append(Paragraph(make_paragraph_safe(source_text), styles["BodyText"]))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Suggested Next Steps", styles["Heading1"]))
    story.append(Paragraph("1. Review the generated findings.", styles["BodyText"]))
    story.append(Paragraph("2. Open and verify the listed sources.", styles["BodyText"]))
    story.append(Paragraph("3. Ask follow-up questions in ARCA.", styles["BodyText"]))
    story.append(Paragraph("4. Export a presentation deck if needed.", styles["BodyText"]))

    doc.build(story)
    buffer.seek(0)

    return buffer


def generate_powerpoint_deck(
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
    user_mode: str,
    analysis_mode: str,
    quiz_feedback: str = "",
):
    prs = Presentation()

    title_slide_layout = prs.slide_layouts[0]
    content_slide_layout = prs.slide_layouts[1]

    clean_answer = clean_export_text(answer)
    clean_feedback = clean_export_text(quiz_feedback) if quiz_feedback else ""

    lines = [line.strip() for line in clean_answer.split("\n") if line.strip()]
    summary_lines = lines[:8] if lines else ["No findings available."]

    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = "Agent ARCA Research Deck"
    slide.placeholders[1].text = f"{user_mode} | {analysis_mode}"

    slide = prs.slides.add_slide(content_slide_layout)
    slide.shapes.title.text = "Research Question"
    slide.placeholders[1].text = question

    slide = prs.slides.add_slide(content_slide_layout)
    slide.shapes.title.text = "Key Findings"
    slide.placeholders[1].text = "\n".join(summary_lines[:8])

    slide = prs.slides.add_slide(content_slide_layout)
    slide.shapes.title.text = "Research Dashboard"
    slide.placeholders[1].text = (
        f"Sources used: {len(sources)}\n"
        f"Answer length: {len(answer.split())} words\n"
        f"Mode: {user_mode}\n"
        f"Analysis: {analysis_mode}"
    )

    source_lines = []
    for i, src in enumerate(sources, start=1):
        source_lines.append(f"{i}. {src['source_name']} — {src['title']}")

    slide = prs.slides.add_slide(content_slide_layout)
    slide.shapes.title.text = "Sources Used"
    slide.placeholders[1].text = "\n".join(source_lines[:10]) if source_lines else "No sources available."

    if clean_feedback:
        feedback_lines = [line.strip() for line in clean_feedback.split("\n") if line.strip()]
        slide = prs.slides.add_slide(content_slide_layout)
        slide.shapes.title.text = "Quiz Feedback"
        slide.placeholders[1].text = "\n".join(feedback_lines[:8])

    slide = prs.slides.add_slide(content_slide_layout)
    slide.shapes.title.text = "Next Steps"
    slide.placeholders[1].text = (
        "1. Review findings.\n"
        "2. Verify sources.\n"
        "3. Ask follow-up questions.\n"
        "4. Use report or deck for study/work."
    )

    buffer = BytesIO()
    prs.save(buffer)
    buffer.seek(0)

    return buffer


def run_pipeline(
    question: str,
    urls: List[str],
    uploaded_pdfs,
    uploaded_docs,
    uploaded_images,
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

        if uploaded_docs:
            for docx in uploaded_docs:
                all_sources.append(extract_docx_text(docx))

        if uploaded_images:
            for image in uploaded_images:
                all_sources.append(extract_image_text(image))

    should_search_web = (
        mode in ["Search the web", "Use my sources + web search"]
        or len(all_sources) == 0
    )

    if should_search_web:
        all_sources.extend(search_web(question))

    prompt = build_prompt(
        question=question,
        sources=all_sources,
        previous_context=previous_context or "",
        chat_history=chat_history or [],
        user_mode=user_mode,
        analysis_mode=analysis_mode,
    )

    answer = safe_generate_content(prompt)

    new_context = f"""
Last question: {question}

Analysis mode: {analysis_mode}

Last answer:
{answer[:3000]}

Sources used:
{", ".join([src["source_name"] for src in all_sources])}
""".strip()

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
        "evaluation": evaluate_answer(answer, len(all_sources)),
    }
