import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUESTIONS = ROOT / "questions.json"
sys.path.insert(0, str(ROOT.parent))
from app import retrieve, search_response


def main():
    run_name = sys.argv[1] if len(sys.argv) > 1 else "run"
    question_rows = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    results = []
    for item in question_rows:
        results.append({
            **item,
            "retrieved": retrieve(item["question"], limit=10),
            "response": search_response(item["question"]),
        })
    output = ROOT / f"{run_name}.json"
    payload = {
        "run": run_name,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieval": "BM25 + TF-IDF sparse-vector RRF",
        "question_count": len(results),
        "results": results,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(results)} question runs to {output}")


if __name__ == "__main__":
    main()
