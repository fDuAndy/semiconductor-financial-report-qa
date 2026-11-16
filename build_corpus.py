import csv
import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
SOURCES = ROOT / "sources.json"
OUTPUT = ROOT / "corpus" / "chunks.jsonl"
INVENTORY = ROOT / "reports" / "report_inventory.csv"
CHUNK_SIZE = 800
OVERLAP = 120


def split_text(text):
    text = re.sub(r"[\t\xa0 ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind("。", start, end), text.rfind("；", start, end))
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - OVERLAP)
    return chunks


def main():
    source_by_file = {item["file"]: item for item in json.loads(SOURCES.read_text(encoding="utf-8"))}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    inventory = []
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as stream:
        for path in sorted(REPORTS.glob("*.pdf")):
            source = source_by_file[path.name]
            reader = PdfReader(str(path))
            extracted_characters = 0
            empty_pages = 0
            report_chunks = 0
            for page_number, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                extracted_characters += len(text)
                empty_pages += not bool(text.strip())
                for chunk_number, chunk in enumerate(split_text(text), start=1):
                    record = {
                        "id": f"{source['code']}-p{page_number}-c{chunk_number}",
                        "company": source["company"],
                        "code": source["code"],
                        "report_year": 2025,
                        "report_title": source["title"],
                        "source_file": path.name,
                        "source_url": source["url"],
                        "pdf_page": page_number,
                        "printed_page": None,
                        "text": chunk,
                    }
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total += 1
                    report_chunks += 1
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            inventory.append({
                "code": source["code"],
                "company": source["company"],
                "segment": source["segment"],
                "report_title": source["title"],
                "file": path.name,
                "pdf_pages": len(reader.pages),
                "file_bytes": path.stat().st_size,
                "sha256": digest,
                "extracted_characters": extracted_characters,
                "empty_pages": empty_pages,
                "chunks": report_chunks,
                "official_url": source["url"],
            })
    with INVENTORY.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=inventory[0].keys())
        writer.writeheader()
        writer.writerows(inventory)
    print(f"Built {total} chunks from {len(source_by_file)} annual reports: {OUTPUT}")
    print(f"Report inventory with page counts and SHA-256: {INVENTORY}")


if __name__ == "__main__":
    main()
