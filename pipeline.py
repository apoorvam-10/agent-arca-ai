import asyncio

# ---- YOUR SIMPLIFIED ARCA PIPELINE ----

def run_pipeline(query, sources):

    # Simulated ingestion + processing (we will upgrade later)
    combined_text = ""

    for s in sources:
        combined_text += f"\nProcessed: {s}"

    synthesis = {
        "summary": f"AI Summary for: {query}\n\nSources processed:\n{combined_text[:300]}"
    }

    evaluation = {
        "readability": 0.95,
        "coverage": 0.90,
        "confidence": 0.92
    }

    return synthesis, evaluation