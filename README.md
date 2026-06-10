# Agent ARCA — Multimodal GenAI Research & Learning Assistant

Agent ARCA is a multimodal AI research assistant that helps students and professionals turn documents, web sources, videos, and images into trusted summaries, study guides, decision briefs, reports, and presentation decks.

It combines document processing, web retrieval, LLM workflows, source reliability scoring, interactive learning tools, and export generation inside a simple research workspace.

---

## Overview

Research and learning often require users to work across many formats: PDFs, Word documents, PowerPoint decks, screenshots, YouTube videos, web articles, and search results. Manually reading, comparing, summarizing, and converting this information into usable outputs can take hours.

Agent ARCA solves this by giving users a single AI-powered workspace where they can upload files, paste links, ask questions, compare sources, generate structured answers, evaluate source credibility, and export professional outputs.

---

## Key Features

### Multimodal Input

Agent ARCA supports:

* PDF files
* Word documents
* PowerPoint decks
* screenshots and images
* URLs and article links
* YouTube transcripts
* web search
* voice input

### AI Research Workflows

Users can generate:

* simple summaries
* detailed research answers
* study guides
* decision briefs
* presentation notes
* source comparisons
* evidence maps
* follow-up answers

### Student Learning Mode

Student Mode helps users understand and retain information through:

* beginner-friendly explanations
* quiz generation
* multiple-choice practice
* flashcards
* revision tips
* written answer feedback
* audio playback of answers

### Professional Research Mode

General Mode supports work and decision-making use cases through:

* executive summaries
* decision briefs
* source-backed analysis
* reliability scoring
* dashboard metrics
* exportable reports and decks

### Source Reliability & Trust Scoring

Agent ARCA ranks sources using reliability signals and displays:

* source trust score
* evidence mapping
* citation-style source markers
* source breakdown
* response time
* estimated token usage
* cost level estimate

### Export Options

Agent ARCA can generate:

* Word research reports
* PDF reports
* PowerPoint decks
* saved research collections

---

## Tech Stack

### Core

* Python
* Streamlit
* Google Gemini API
* Tavily Search API

### Document Processing

* PyMuPDF
* python-docx
* python-pptx

### Export Generation

* ReportLab
* python-docx
* python-pptx

### Video & Audio

* youtube-transcript-api
* yt-dlp
* webvtt-py
* gTTS

### Other

* BeautifulSoup
* Requests
* Streamlit session state
* Streamlit caching

---

## Architecture

```text
User
 |
 | Upload files / paste links / ask questions
 v
Streamlit UI
 |
 | User mode, source mode, output style, attachments
 v
Agent ARCA Pipeline
 |
 |-- PDF Reader
 |-- DOCX Reader
 |-- PPTX Reader
 |-- Image Reader
 |-- URL Reader
 |-- YouTube Transcript Reader
 |-- Web Search Retriever
 |-- Source Reliability Ranker
 |-- Prompt Builder
 |-- Gemini Response Generator
 |-- Export Generator
 |
 v
Research Output
 |
 |-- Source-backed answer
 |-- Trust dashboard
 |-- Follow-up Q&A
 |-- Quiz and flashcards
 |-- Audio playback
 |-- Word/PDF/PPT exports
```

---

## How It Works

1. The user chooses an answer style such as Simple Summary, Study Guide, Detailed Research, Presentation Notes, or Decision Brief.
2. The user uploads files, pastes URLs, or enables web search.
3. Agent ARCA extracts text from uploaded files, URLs, videos, and images.
4. The pipeline retrieves additional web sources if needed.
5. Sources are ranked using reliability heuristics.
6. Gemini generates a structured, source-backed answer.
7. The app displays the answer with source markers and dashboard metrics.
8. Users can ask follow-up questions, generate quizzes, create flashcards, listen to the answer, save findings, or export reports.

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/apoorvam-10/agent-arca-ai.git
cd agent-arca-ai
```

### 2. Create a virtual environment

```bash
python3 -m venv arca
source arca/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Add API keys

Create a Streamlit secrets file:

```bash
mkdir -p .streamlit
nano .streamlit/secrets.toml
```

Add:

```toml
GEMINI_API_KEY = "your_gemini_api_key_here"
TAVILY_API_KEY = "your_tavily_api_key_here"
```

### 5. Run the app

```bash
streamlit run app.py
```

---

## Environment Variables

The app requires:

```text
GEMINI_API_KEY
TAVILY_API_KEY
```

These should be stored in:

```text
.streamlit/secrets.toml
```

Do not commit secrets to GitHub.

---

## Screenshots

Add screenshots in a `screenshots/` folder.

Recommended screenshots:

```text
screenshots/landing.png
screenshots/research-response.png
screenshots/dashboard.png
screenshots/learning-practice.png
screenshots/exports.png
```

Example markdown:

```markdown
![Landing Page](screenshots/landing.png)
![Research Response](screenshots/research-response.png)
![Dashboard](screenshots/dashboard.png)
![Learning Practice](screenshots/learning-practice.png)
![Exports](screenshots/exports.png)
```

---

## Example Use Cases

### Student

A student can upload lecture notes or a PDF and ask:

```text
Summarize this in simple terms and create quiz questions.
```

Agent ARCA returns a study guide, quiz, flashcards, and revision tips.

### Professional

A professional can paste multiple sources and ask:

```text
Compare these sources and create a decision brief.
```

Agent ARCA returns source-backed analysis, evidence mapping, trust scores, and exportable reports.

### Research Workflow

A user can ask:

```text
Research this topic using reliable sources and create presentation notes.
```

Agent ARCA retrieves sources, ranks reliability, generates structured notes, and exports a PowerPoint deck.

---

## Current Version

### Agent ARCA v1

This version focuses on:

* multimodal document and web research
* source-grounded generation
* student and professional workflows
* source reliability scoring
* export-ready reports and decks
* production-style Streamlit UX

---

## Future Roadmap

Planned improvements for Agent ARCA v2:

* Next.js frontend
* FastAPI backend
* real-time streaming responses
* persistent user accounts
* saved cloud sessions
* vector search over uploaded documents
* stronger agent orchestration
* advanced PowerPoint design
* cloud file storage
* background processing for long documents

Target production architecture:

```text
Frontend: Next.js + Tailwind
Backend: FastAPI
Database: PostgreSQL / Supabase
Storage: Supabase Storage / S3
Async Jobs: Redis + Celery or RQ
AI Layer: Gemini / OpenAI-compatible LLM APIs
Search: Tavily
Deployment: Vercel + Render/Fly.io/AWS
```

---

## What I Learned

This project helped strengthen skills in:

* AI application design
* multimodal GenAI workflows
* prompt orchestration
* document processing
* source-grounded generation
* API integration
* Streamlit product UX
* export generation
* reliability and latency optimization
* GitHub project deployment

---

## Project Status

Agent ARCA v1 is complete as a portfolio-ready prototype.

Current version includes:
- multimodal file and web ingestion
- source-backed AI responses
- trust scoring and dashboard metrics
- interactive learning practice
- follow-up Q&A
- Word, PDF, and PowerPoint exports

Next milestone: Agent ARCA v2 with a Next.js frontend, FastAPI backend, streaming responses, persistent sessions, and cloud storage.

---

## Impact

Agent ARCA demonstrates how multimodal GenAI can support research, learning, and decision-making by combining document processing, web retrieval, source-grounded generation, trust scoring, and export-ready outputs in one workflow.

Key outcomes:
- Reduced manual research effort by converting long-form sources into structured summaries and study outputs.
- Improved transparency with source markers, evidence maps, and trust scoring.
- Supported multiple user workflows including studying, professional research, presentations, and report generation.
- Improved usability with quick-start actions, unified uploads, follow-up Q&A, audio playback, and interactive learning practice.
