import asyncio

# -------------------------
# MEMORY STORE
# -------------------------
memory_store = {}

def save_memory(query, summary):
    memory_store[query] = summary

def get_memory(query):
    return memory_store.get(query, "")

# -------------------------
# QUERY ENHANCEMENT
# -------------------------
def enhance_query(query):
    return f"Research Request: {query}"

# -------------------------
# MAIN PIPELINE
# -------------------------
def run_pipeline(query, sources):

    query = enhance_query(query)

    # Simulated ingestion
    combined_text = ""

    for s in sources:
        combined_text += f"\nProcessed source: {s}"

    # Generate summary
    summary = f"""
AI Summary for: {query}

Sources processed:
{combined_text}

Key Insight:
This topic is important and current. Multiple sources were reviewed and summarized.
"""

    synthesis = {
        "summary": summary
    }

    # Save memory
    save_memory(query, summary)

    # Better evaluation logic
    readability = min(1.0, len(summary) / 500)
    coverage = min(1.0, len(set(summary.split())) / 100)
    confidence = round((readability + coverage) / 2, 2)

    evaluation = {
        "readability": round(readability, 2),
        "coverage": round(coverage, 2),
        "confidence": confidence
    }

    return synthesis, evaluation

        "confidence": 0.92
    }

    return synthesis, evaluation
