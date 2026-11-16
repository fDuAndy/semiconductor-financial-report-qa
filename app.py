import json
import math
import re
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
CHUNKS_PATH = ROOT / "corpus" / "chunks.jsonl"
PORT = 8765


def tokenize(text):
    tokens = []
    for part in re.findall(r"[a-zA-Z0-9]+|[\u3400-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            if len(part) == 1:
                tokens.append(part)
            else:
                tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
        else:
            tokens.append(part)
    return tokens


def load_chunks():
    if not CHUNKS_PATH.exists():
        raise SystemExit("Corpus not found. Run: python build_corpus.py")
    with CHUNKS_PATH.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


CHUNKS = load_chunks()
COMPANIES = sorted({item["company"] for item in CHUNKS})
DOC_TOKENS = [tokenize(item["text"]) for item in CHUNKS]
AVG_LENGTH = sum(map(len, DOC_TOKENS)) / max(len(DOC_TOKENS), 1)
DOC_FREQ = Counter(token for tokens in DOC_TOKENS for token in set(tokens))
IDF = {token: math.log(1 + (len(CHUNKS) - freq + 0.5) / (freq + 0.5)) for token, freq in DOC_FREQ.items()}
POSTINGS = defaultdict(list)
for index, tokens in enumerate(DOC_TOKENS):
    for term, count in Counter(tokens).items():
        POSTINGS[term].append((index, count))


def requested_companies(query):
    all_companies = any(marker in query for marker in ("10家公司", "全部公司", "所有公司", "上述公司"))
    if all_companies:
        return COMPANIES, True
    return [company for company in COMPANIES if company in query], False


def expanded_terms(query):
    expanded = list(tokenize(query))
    aliases = {
        "营业收入": ("营业收入", "营业总收入", "实现营业收入"),
        "归母净利润": ("归属于上市公司股东的净利润", "归母净利润"),
        "扣非归母净利润": ("归属于上市公司股东的扣除非经常性损益的净利润", "扣非归母净利润"),
        "经营活动现金流": ("经营活动产生的现金流量净额", "经营活动现金流量净额"),
        "研发投入": ("研发投入金额", "研发投入合计", "研发费用"),
        "同比": ("同比增长", "本期比上年同期增减", "较上年增长"),
    }
    for term, phrases in aliases.items():
        if term in query:
            for phrase in phrases:
                expanded.extend(tokenize(phrase))
    for company in COMPANIES:
        if company in query:
            company_tokens = set(tokenize(company))
            expanded = [token for token in expanded if token not in company_tokens]
    return expanded


def retrieve(query, limit=8):
    company_scope, panorama = requested_companies(query)
    years = [int(year) for year in re.findall(r"20\d{2}", query)]
    future_actual = any(word in query for word in ("已经实现", "实际实现", "实际收入"))
    if future_actual and years and max(years) > max(item["report_year"] for item in CHUNKS):
        return []
    terms = expanded_terms(query)
    if not terms:
        return []
    if company_scope:
        allowed = {index for index, item in enumerate(CHUNKS) if item["company"] in company_scope}
    else:
        allowed = set(range(len(CHUNKS)))
    bm25 = defaultdict(float)
    vector = defaultdict(float)
    query_counts = Counter(terms)
    qnorm = math.sqrt(sum((1 + math.log(count)) ** 2 for count in query_counts.values())) or 1
    for term, query_count in query_counts.items():
        idf = IDF.get(term, 0.0)
        qweight = (1 + math.log(query_count)) / qnorm
        for index, frequency in POSTINGS.get(term, []):
            if index not in allowed:
                continue
            length = len(DOC_TOKENS[index])
            bm25[index] += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / max(AVG_LENGTH, 1)))
            vector[index] += qweight * (1 + math.log(frequency)) * idf
    vector_norms = {}
    for index in vector:
        norm = math.sqrt(sum(((1 + math.log(count)) * IDF.get(term, 0.0)) ** 2 for term, count in Counter(DOC_TOKENS[index]).items())) or 1
        vector_norms[index] = norm
    vector = {index: score / vector_norms[index] for index, score in vector.items()}
    bm_order = [index for index, _ in sorted(bm25.items(), key=lambda pair: pair[1], reverse=True)]
    vec_order = [index for index, _ in sorted(vector.items(), key=lambda pair: pair[1], reverse=True)]
    ranks = defaultdict(float)
    for order in (bm_order, vec_order):
        for rank, index in enumerate(order, start=1):
            ranks[index] += 1 / (60 + rank)
    if panorama:
        selected = []
        for company in company_scope:
            company_hits = sorted((index for index in ranks if CHUNKS[index]["company"] == company), key=ranks.get, reverse=True)
            selected.extend(company_hits[:2])
    elif len(company_scope) > 1:
        per_company = min(3, max(1, limit // len(company_scope)))
        selected = []
        for company in company_scope:
            company_hits = sorted((index for index in ranks if CHUNKS[index]["company"] == company), key=ranks.get, reverse=True)
            selected.extend(company_hits[:per_company])
    else:
        selected = sorted(ranks, key=ranks.get, reverse=True)[:limit]
    return [{**CHUNKS[index], "score": round(ranks[index], 5)} for index in selected]


def search_response(query):
    company_scope, panorama = requested_companies(query)
    results = retrieve(query, limit=10)
    found = sorted({item["company"] for item in results})
    missing = [company for company in company_scope if company not in found]
    years = [int(year) for year in re.findall(r"20\d{2}", query)]
    future_actual = any(word in query for word in ("已经实现", "实际实现", "实际收入"))
    if future_actual and years and max(years) > max(item["report_year"] for item in CHUNKS):
        answer = "知识库只收录2025年年度报告，无法提供之后年度已经实现的收入；请以公司后续正式披露为准。"
        company_scope = []
        missing = []
    elif not results:
        answer = "没有检索到可直接支持结论的年报片段，请调整问题或核对报告范围。"
    elif missing:
        answer = f"找到{len(found)}家公司的候选证据，但仍缺少{len(missing)}家公司，不能作为完整全景答案。缺少：{'、'.join(missing)}。"
    elif panorama:
        answer = f"已覆盖{len(found)}家公司。以下是逐家公司召回的原文证据；币种、单位和指标口径须按各报告原文分别核对。"
    else:
        answer = "以下摘录为年报原文证据，可直接核对回答；数值计算和口径判断以报告表头及附注为准。"
    return {"answer": answer, "results": results, "coverage": {"requested": company_scope, "found": found, "missing": missing}}


PAGE = (ROOT / "ui.html").read_text(encoding="utf-8")


LEGACY_PAGE = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>集成电路半导体财报问答库</title><style>
body{font:16px/1.65 system-ui,'Microsoft YaHei',sans-serif;max-width:980px;margin:36px auto;padding:0 18px;color:#192332;background:#f5f7fa}h1{font-size:28px}p{color:#526174}.box,.result{background:white;border:1px solid #dce3ec;border-radius:12px;padding:18px;margin:14px 0}textarea{width:100%;box-sizing:border-box;min-height:82px;padding:12px;border:1px solid #b9c6d5;border-radius:8px;font:inherit}button{margin-top:10px;padding:9px 18px;background:#155eef;color:white;border:0;border-radius:7px;font:inherit;cursor:pointer}.meta{font-size:14px;color:#526174}.quote{white-space:pre-wrap}.tag{color:#155eef}a{color:#155eef}</style>
<h1>集成电路半导体财报问答库</h1><p>基于10家上市公司2025年年度报告全文。输入问题后，系统融合BM25关键词检索与TF-IDF向量相似度，展示可回到原PDF页码的证据片段。</p>
<div class='box'><textarea id='q' placeholder='例如：中芯国际2025年研发投入占营业收入多少？'></textarea><button onclick='ask()'>检索证据</button></div><div id='out'></div>
<script>async function ask(){const q=document.getElementById('q').value.trim(),out=document.getElementById('out');if(!q)return;out.textContent='正在检索…';const r=await fetch('/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});const d=await r.json();out.innerHTML=d.results.length?d.results.map(x=>`<div class="result"><b>${x.company}（${x.code}）</b>　<span class="meta">${x.report_year}年年报 · PDF第${x.pdf_page}页</span><p class="quote">${escapeHtml(x.text)}</p><div class="meta">来源：<a href="${x.source_url}" target="_blank" rel="noopener">巨潮资讯年报原文</a> · ${x.source_file}</div></div>`).join(''):'没有找到相关证据，请换用公司名称、指标名或报告章节提问。'};}function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path != "/":
            self.send_error(404)
            return
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlparse(self.path).path != "/search":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        query = json.loads(self.rfile.read(length)).get("query", "")
        body = json.dumps(search_response(query), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    print(f"Loaded {len(CHUNKS)} passages from 10 reports.")
    print(f"Open http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
