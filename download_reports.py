import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
SOURCES = ROOT / "sources.json"


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    for source in sources:
        url = source["url"]
        if urlparse(url).hostname != "static.cninfo.com.cn":
            raise ValueError(f"Unexpected report host: {url}")
        destination = REPORTS / source["file"]
        if destination.exists() and destination.stat().st_size > 0:
            print(f"Keep existing: {destination.name}")
            continue
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=60) as response:
            data = response.read()
        if not data.startswith(b"%PDF-"):
            raise ValueError(f"Downloaded file is not a PDF: {url}")
        destination.write_bytes(data)
        print(f"Downloaded: {destination.name} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
