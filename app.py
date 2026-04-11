import os
import firebase_admin
from firebase_admin import credentials, firestore
import sys
# Force UTF-8 output to prevent UnicodeEncodeError on Windows with crawl4ai/rich
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
import time
import asyncio
import requests
import traceback
import random
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import google.generativeai as genai
import numpy as np
import io
from pypdf import PdfReader

# ========== Search Import ==========
from ddgs import DDGS

# ========== Lightweight Scraping Imports ==========
from bs4 import BeautifulSoup
import re

# ========== Optional Crawl4AI (requires Playwright browser installed) ==========
CRAWL4AI_AVAILABLE = False
try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    CRAWL4AI_AVAILABLE = True
except ImportError:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ========== Configuration ==========
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDVIAXdCCmDo_k9kbH0DbqcKvGaZHqKnVQ")
MODEL_NAME = "gemini-2.5-flash"
MODEL_NAME_FAST = "gemini-2.5-flash"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:streamGenerateContent?alt=sse&key={GEMINI_API_KEY}"
API_URL_FAST = API_URL
API_URL_NON_STREAM = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"

# Initialize Gemini SDK for Embeddings
genai.configure(api_key=GEMINI_API_KEY)
EMBEDDING_MODEL = "models/gemini-embedding-001"

import collections

class RateLimiter:
    def __init__(self, max_requests: int = 20, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Maps session_id to a deque of timestamps
        self.history = collections.defaultdict(collections.deque)

    def is_allowed(self, session_id: str) -> bool:
        now = time.time()
        # Clean up old timestamps for this session
        while self.history[session_id] and self.history[session_id][0] < now - self.window_seconds:
            self.history[session_id].popleft()
        
        if len(self.history[session_id]) >= self.max_requests:
            return False
        
        self.history[session_id].append(now)
        return True

rate_limiter = RateLimiter(max_requests=20, window_seconds=60)

# Create a global session to reuse Google APIs connections and bypass severe Windows DNS/SSL handshake latency
gemini_session = requests.Session()

# ========== Stateful Config ==========
MAX_HISTORY_TURNS = 10
MAX_SESSIONS = 50
SESSION_TTL_SECONDS = 3600
MAX_SEARCH_RESULTS = 5
MAX_CONTENT_PER_PAGE = 6000

app = FastAPI(title="Perplexity Clone API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== Global Crawler Instance (optional) ==========
crawler_instance = None


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Essential for Firebase Auth Popups on some browsers
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response

@app.on_event("startup")
async def startup_event():
    """Try to initialize Crawl4AI browser. Falls back to requests+BS4 if unavailable."""
    global crawler_instance
    if CRAWL4AI_AVAILABLE:
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
            import logging
            logging.getLogger("crawl4ai").setLevel(logging.ERROR)
            browser_cfg = BrowserConfig(browser_type="chromium", headless=True, verbose=False)
            crawler_instance = AsyncWebCrawler(config=browser_cfg)
            await crawler_instance.start()
            print("[Crawl4AI] Browser started successfully.")
        except Exception as e:
            err_msg = str(e).encode('ascii', errors='replace').decode('ascii')
            print(f"[Crawl4AI] WARNING: Could not start browser: {err_msg}")
            print("[Crawl4AI] Falling back to lightweight HTTP scraper.")
            crawler_instance = None
    else:
        print("[Startup] Crawl4AI not available. Using lightweight HTTP scraper.")
    
    # Pre-warm the HTTPS connection to Gemini API to eliminate cold-start latency
    try:
        gemini_session.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}", timeout=5)
        print("[Startup] Gemini API connection pre-warmed.")
    except Exception as e:
        print(f"[Startup] Gemini pre-warm failed (non-critical): {e}")

    # Initialize Firebase
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate("firebase-auth.json")
            firebase_admin.initialize_app(cred)
            print("[Firebase] Admin SDK initialized successfully.")
    except Exception as e:
        print(f"[Firebase] Initialization error: {e}")
    
    print("[Startup] Server ready - DuckDuckGo search + web scraping enabled.")


# ========== Database Setup (Firebase Firestore) ==========
DB_CLIENT = None

def get_db():
    global DB_CLIENT
    if DB_CLIENT is None:
        DB_CLIENT = firestore.client()
    return DB_CLIENT


# ========== Global Session Cache (to avoid frequent DB reads) ==========
# We still keep an in-memory cache but sync it with SQLite
# rag_embeddings must stay in memory (numpy arrays) for compute speed,
# but can be re-generated from stored chunks if needed.
sessions: dict[str, dict] = {}


def get_session_data(session_id: str) -> dict:
    now = time.time()
    
    # 1. Check cache first
    if session_id in sessions:
        sessions[session_id]["last_access"] = now
        return sessions[session_id]

    # 2. Check Firestore
    try:
        db = get_db()
        doc_ref = db.collection("sessions").document(session_id)
        doc = doc_ref.get()
        
        if doc.exists:
            data = doc.to_dict()
            history = data.get("history", [])
            rag_chunks = data.get("rag_chunks", [])
            
            sessions[session_id] = {
                "history": history,
                "last_access": now,
                "rag_chunks": rag_chunks,
                "rag_embeddings": None # Re-generated if needed
            }
            print(f"[Firebase] Loaded session {session_id} from cloud.")
        else:
            # Create new
            sessions[session_id] = {
                "history": [], 
                "last_access": now,
                "rag_chunks": [],
                "rag_embeddings": None
            }
            # Save to Cloud immediately
            doc_ref.set({
                "history": [],
                "rag_chunks": [],
                "last_access": now,
                "created_at": firestore.SERVER_TIMESTAMP
            })
            print(f"[Firebase] Created new session {session_id} in cloud.")
    except Exception as e:
        print(f"[Firebase] Error reading session {session_id}: {e}")
        # Fallback to local-only for this session if cloud fails
        sessions[session_id] = {
            "history": [], "last_access": now, "rag_chunks": [], "rag_embeddings": None
        }
    
    return sessions[session_id]


def save_session_to_db(session_id: str):
    if session_id not in sessions: return
    sess = sessions[session_id]
    try:
        db = get_db()
        db.collection("sessions").document(session_id).update({
            "history": sess["history"],
            "rag_chunks": sess["rag_chunks"],
            "last_access": sess["last_access"]
        })
    except Exception as e:
        print(f"[Firebase] Error saving session {session_id}: {e}")


def get_session(session_id: str) -> list:
    return get_session_data(session_id)["history"]


# ========== RAG Core Engine ==========
class RAGManager:
    @staticmethod
    def chunk_text(text: str, source: str, url: str = "", chunk_size: int = 1000, overlap: int = 100):
        """Splits text into overlapping chunks for semantic search."""
        if not text: return []
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            if len(chunk_text) > 50: # Skip tiny fragments
                chunks.append({
                    "text": chunk_text,
                    "source": source,
                    "url": url
                })
        return chunks

    @staticmethod
    async def get_embeddings(texts: list[str]):
        """Fetches embeddings from Gemini API in batches."""
        if not texts: return None
        try:
            # Gemini supports batch embedding
            res = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=texts,
                task_type="retrieval_document"
            )
            return np.array(res['embedding'], dtype=np.float32)
        except Exception as e:
            print(f"[RAG] Embedding Error: {e}")
            return None

    @staticmethod
    async def retrieve(query: str, session_id: str, top_k: int = 10):
        """Semantic search: query vs session context."""
        sess = get_session_data(session_id)
        if not sess["rag_chunks"] or sess["rag_embeddings"] is None:
            return []

        try:
            # Get query embedding
            q_res = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=query,
                task_type="retrieval_query"
            )
            q_vec = np.array(q_res['embedding'], dtype=np.float32)

            # Compute Cosine Similarities (Dot product on normalized vectors)
            # Embedding-004 vectors are already normalized
            similarities = np.dot(sess["rag_embeddings"], q_vec)
            
            # Get top-K indices
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                score = float(similarities[idx])
                # Always include chunks if the session has few chunks (like a single uploaded file)
                # Or if the relevance score is somewhat positive.
                if score > 0.05 or len(sess["rag_chunks"]) <= 30:
                    results.append({
                        **sess["rag_chunks"][idx],
                        "score": score
                    })
            return results
        except Exception as e:
            print(f"[RAG] Retrieval Error: {e}")
            return []

    @staticmethod
    async def add_to_session(session_id: str, new_chunks: list[dict]):
        """Embeds and appends new chunks to the session vector store."""
        if not new_chunks: return
        
        texts = [c["text"] for c in new_chunks]
        new_embeddings = await RAGManager.get_embeddings(texts)
        
        if new_embeddings is None: return

        sess = get_session_data(session_id)
        sess["rag_chunks"].extend(new_chunks)
        
        if sess["rag_embeddings"] is None:
            sess["rag_embeddings"] = new_embeddings
        else:
            sess["rag_embeddings"] = np.vstack([sess["rag_embeddings"], new_embeddings])
        
        # PERSIST TO DB
        save_session_to_db(session_id)
        print(f"[RAG] Added {len(new_chunks)} chunks to session {session_id}. Total: {len(sess['rag_chunks'])}")


def trim_history(history: list):
    max_messages = MAX_HISTORY_TURNS * 2
    while len(history) > max_messages:
        history.pop(0)


# ========== Web Search (DuckDuckGo) ==========
def safe_ddgs_call(func, *args, **kwargs):
    """Wrapper to handle DuckDuckGo rate-limiting with retries and exponential backoff."""
    max_retries = 1  # Reduced from 3 to avoid long blocks
    base_delay = 0.5  # Reduced from 1.0
    
    for attempt in range(max_retries):
        try:
            return list(func(*args, **kwargs))
        except Exception as e:
            err_str = str(e).lower()
            if "403" in err_str or "ratelimit" in err_str:
                wait_time = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                print(f"[Search] Rate limited (403). Waiting {wait_time:.2f}s and retrying (Attempt {attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"[Search] Call failed with error: {e}")
                break
    return []

# ========== Configuration & Helpers ==========
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
]

def get_headers(referer="https://www.google.com/"):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referer,
        "Cache-Control": "no-cache"
    }

def is_conversational(query: str) -> bool:
    """Detects greetings or light social conversation to bypass web search with high precision."""
    # Normalize: lowercase, strip punctuation
    q = re.sub(r'[^\w\s]', '', query.lower()).strip()
    
    greetings = {
        "hi", "hello", "hey", "hola", "greetings", "morning", "afternoon", "evening",
        "how are you", "hows it going", "how are you doing", "who are you", "what are you",
        "tell me a joke", "whats up", "yo", "hi there", "hello there", "thanks", "thank you",
        "bye", "goodbye", "help", "what can you do"
    }
    
    # 1. Direct match (normalized)
    if q in greetings:
        return True
        
    # 2. Starts with a greeting (first 2-3 words)
    words = q.split()
    if words:
        # Check first word
        if words[0] in greetings:
            # If it's a very short query (<= 4 words) starting with a greeting, it's likely chat
            if len(words) <= 4:
                return True
        
        # Check first two words (e.g. "hi there")
        if len(words) >= 2:
            two_words = " ".join(words[:2])
            if two_words in greetings and len(words) <= 5:
                return True
                
    return False

def smart_rewrite_query(query: str, broad: bool = False) -> str:
    """Expansion logic with optional broadening to bypass date-specific search failures."""
    now = datetime.now()
    query_lower = query.lower()
    
    if broad:
        # Broad mode: return simplified query
        clean = query_lower.replace("yesterday", "").replace("today", "").replace("'s", "")
        return clean.strip()

    # If it asks for time specific info
    is_timely = any(word in query_lower for word in ["today", "yesterday", "latest", "current", "now"])
    
    if is_timely:
        date_context = now.strftime("%B %d %Y")
        if "yesterday" in query_lower:
            target_date = now - timedelta(days=1)
            date_context = target_date.strftime("%B %d %Y")
        
        # Strip simple fillers
        clean_query = query_lower.replace("?", "").replace("!", "")
        return f"{clean_query} {date_context}".strip()
    
    return query.strip()

def scrape_ddg_lite(query: str) -> list[dict]:
    """Fallback scraper using DuckDuckGo Lite (no JavaScript) to bypass API blocks."""
    url = "https://lite.duckduckgo.com/lite/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://lite.duckduckgo.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    try:
        # Lite version expects a POST with the query 'q'
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        
        # In Lite version, results are in table rows
        # The main results have specific structures
        for row in soup.find_all("tr"):
            link_tag = row.find("a", class_="result-link")
            if not link_tag:
                continue
                
            # Snippet is usually in the following row or div
            snippet_tag = row.find_next_sibling("tr")
            snippet = ""
            if snippet_tag:
                snippet = snippet_tag.get_text(strip=True)
            
            results.append({
                "title": link_tag.get_text(strip=True),
                "url": link_tag.get("href", ""),
                "snippet": snippet
            })
            
            if len(results) >= MAX_SEARCH_RESULTS:
                break
        
        if results:
            print(f"[Search] Lite Fallback success: Found {len(results)} results.")
        return results
    except Exception as e:
        print(f"[Search] Lite Fallback failed: {e}")
        return []

async def scrape_browser_search(query: str) -> list[dict]:
    """Last-resort search using a real browser via Crawl4AI/Playwright."""
    if not CRAWL4AI_AVAILABLE: return []
    try:
        url = f"https://www.google.com/search?q={query}"
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(wait_for="div.g", cache_mode=CacheMode.BYPASS)
            )
            if not result or not result.success: return []
            
            # Simple regex-based extraction of links and titles from the rendered HTML
            html = result.html
            soup = BeautifulSoup(html, "lxml")
            results = []
            for g in soup.select("div.g"):
                link = g.find("a")
                title = g.find("h3")
                if link and title:
                    href = link.get("href")
                    if href and href.startswith("http"):
                        results.append({"title": title.get_text(), "url": href, "snippet": ""})
                if len(results) >= MAX_SEARCH_RESULTS: break
            return results
    except Exception as e:
        print(f"[Browser Search Error] {e}")
        return []

# ========== Web Search (Final Resilient Wrapper) ==========
async def web_search(query: str, max_results: int = MAX_SEARCH_RESULTS) -> list[dict]:
    """Multi-stage search with browser-assisted fallbacks."""
    try:
        now = datetime.now()
        time_keywords = ["today", "yesterday", "latest", "news", "now", "score", "match", "current", "recently", "price", "ipl"]
        is_timely = any(k in query.lower() for k in time_keywords)

        rewritten = smart_rewrite_query(query)
        
        # SEARCH TIER EXECUTION
        results = []
        
        # Phase 1: API (DDG)
        print(f"[Search] Attempt 1 (DDG API): {rewritten}")
        try:
            with DDGS() as ddgs:
                if is_timely: results = safe_ddgs_call(ddgs.news, rewritten, max_results=max_results, timelimit="d")
                if not results: results = safe_ddgs_call(ddgs.text, rewritten, max_results=max_results)
        except: pass

        # Phase 2: Web Scrapers (DDG Lite)
        if not results:
            print(f"[Search] Attempt 2 (Scrapers) for: {rewritten}")
            results = scrape_ddg_lite(rewritten)

        # Phase 3: Browser Fallback (Crawl4AI) - Bypasses bot detection
        if not results and CRAWL4AI_AVAILABLE:
            print(f"[Search] Attempt 3 (Browser) for: {rewritten}")
            results = await scrape_browser_search(rewritten)

        # Phase 4: Extreme Broadening (Ignore dates)
        if not results:
            broad = smart_rewrite_query(query, broad=True)
            if broad != rewritten:
                print(f"[Search] Attempt 4 (Broadening) for: {broad}")
                results = scrape_ddg_lite(broad)
                if not results and CRAWL4AI_AVAILABLE:
                    results = await scrape_browser_search(broad)

        # POST-PROCESSING
        formatted_results = []
        seen_urls = set()
        for r in results:
            url = r.get("url") or r.get("href")
            if not url or url in seen_urls: continue
            
            title = str(r.get("title", "Source")).encode('ascii', 'ignore').decode('ascii').strip()[:100]
            snippet = str(r.get("snippet", "") or r.get("body", "")).encode('ascii', 'ignore').decode('ascii').strip()[:300]
            
            formatted_results.append({"title": title or "Search Result", "url": url, "snippet": snippet})
            seen_urls.add(url)
        
        return formatted_results[:max_results]
    except Exception as e:
        print(f"[Search Global Error] {e}")
        return []


# ========== Lightweight HTTP Scraper (no Playwright needed) ==========
HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-GB,en;q=0.9",
    },
    {
        "User-Agent": "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Accept": "text/html",
    },
]
HEADERS = HEADERS_LIST[0]


def html_to_markdown(html: str) -> str:
    """Convert HTML to simplified markdown text using BeautifulSoup."""
    soup = BeautifulSoup(html, "lxml")

    # Remove script, style, nav, footer, header elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()

    # Try to find the main content area
    main_content = (
        soup.find("main") or
        soup.find("article") or
        soup.find(attrs={"role": "main"}) or
        soup.find("div", class_=re.compile(r"(content|article|post|entry|main)", re.I)) or
        soup.body or
        soup
    )

    lines = []
    for el in main_content.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "blockquote", "pre", "code"]):
        text = el.get_text(separator=" ", strip=True)
        if not text or len(text) < 5:
            continue

        tag = el.name
        if tag == "h1":
            lines.append(f"\n# {text}\n")
        elif tag == "h2":
            lines.append(f"\n## {text}\n")
        elif tag == "h3":
            lines.append(f"\n### {text}\n")
        elif tag == "h4":
            lines.append(f"\n#### {text}\n")
        elif tag == "li":
            lines.append(f"- {text}")
        elif tag in ("pre", "code"):
            lines.append(f"\n```\n{text}\n```\n")
        elif tag == "blockquote":
            lines.append(f"> {text}")
        else:
            lines.append(text)

    return "\n".join(lines)


def scrape_url_lightweight(url: str) -> dict:
    """Scrape a URL using requests + BeautifulSoup with rotating headers to bypass 403 blocks."""
    for headers in HEADERS_LIST:
        try:
            resp = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
            if resp.status_code == 403:
                print(f"[Scrape] 403 with agent '{headers['User-Agent'][:30]}...', trying next")
                continue
            resp.raise_for_status()
            content = html_to_markdown(resp.text)
            if len(content) > MAX_CONTENT_PER_PAGE:
                content = content[:MAX_CONTENT_PER_PAGE] + "\n\n[... content truncated]"
            return {"url": url, "content": content, "success": bool(content.strip())}
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                continue
            print(f"[Scrape] HTTP Error fetching {url}: {e}")
            sys_status = e.response.status_code if e.response else 500
            return {"url": url, "content": "", "success": False, "status_code": sys_status}
        except Exception as e:
            print(f"[Scrape] Error fetching {url}: {e}")
            return {"url": url, "content": "", "success": False, "status_code": 0}
    print(f"[Scrape] All headers exhausted for {url} - site blocks scrapers")
    return {"url": url, "content": "", "success": False, "status_code": 403}


# ========== Crawl4AI Scraper (if available) ==========
async def crawl_urls_crawl4ai(urls: list[str]) -> list[dict]:
    """Use Crawl4AI for high-quality extraction (requires Playwright)."""
    try:
        from crawl4ai import CrawlerRunConfig, CacheMode
    except ImportError:
        return await crawl_urls_lightweight(urls)

    run_cfg = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, word_count_threshold=10, verbose=False)

    async def crawl_single(url: str) -> dict:
        try:
            result = await crawler_instance.arun(url=url, config=run_cfg)
            if result.success and result.markdown:
                content = result.markdown.strip()
                if len(content) > MAX_CONTENT_PER_PAGE:
                    content = content[:MAX_CONTENT_PER_PAGE] + "\n\n[... content truncated]"
                if len(content) > 100:  # Only use if meaningful content
                    return {"url": url, "content": content, "success": True}
            # Browser got nothing useful - fall back to lightweight
            print(f"[Crawl4AI] No content for {url[:60]}, trying lightweight fallback")
            return scrape_url_lightweight(url)
        except Exception as e:
            err_safe = str(e).encode('ascii', errors='replace').decode('ascii')[:80]
            print(f"[Crawl4AI] Error crawling {url[:50]}: {err_safe}")
            return scrape_url_lightweight(url)  # Fallback on error

    tasks = [asyncio.wait_for(crawl_single(url), timeout=8.0) for url in urls]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    for i, item in enumerate(gathered):
        if isinstance(item, dict):
            results.append(item)
        else:
            # Timeout or unhandled error - use lightweight
            results.append(scrape_url_lightweight(urls[i]) if i < len(urls) else {"url": "", "content": "", "success": False})
    return results


async def crawl_urls_lightweight(urls: list[str]) -> list[dict]:
    """Run lightweight scraper concurrently in thread pool."""
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, scrape_url_lightweight, url) for url in urls]
    return list(await asyncio.gather(*tasks))


# ========== Unified Crawler ==========
async def crawl_urls(urls: list[str]) -> list[dict]:
    """Crawl URLs prioritizing lightweight scraper for speed, falling back to real browser if blocked."""
    print(f"[Crawl] Using lightweight scraper for {len(urls)} URLs")
    results = await crawl_urls_lightweight(urls)
    
    # Re-try failed URLs with real browser if available (only handles 403/429 blocks)
    if crawler_instance and CRAWL4AI_AVAILABLE:
        # Only retry if it's a block/empty (403, 429) or connection error (0). Do not retry 404s.
        failed_urls = [r["url"] for r in results if not r.get("success") and r.get("url") and r.get("status_code", 403) in (403, 401, 429, 0)]
        if failed_urls:
            print(f"[Crawl] {len(failed_urls)} URLs failed lightweight due to blocks. Retrying with browser.")
            crawled_heavy = await crawl_urls_crawl4ai(failed_urls)
            heavy_map = {r["url"]: r for r in crawled_heavy}
            for i, res in enumerate(results):
                if not res.get("success") and res.get("url") in heavy_map:
                    results[i] = heavy_map[res["url"]]

    return results


# ========== Build Context Prompt ==========
def build_rag_context_prompt(query: str, retrieved_chunks: list[dict], search_sources: list[dict] = None) -> str:
    """Builds a prompt using retrieved semantic chunks and original search results metadata."""
    context_parts = []
    
    # 1. Add Semantic Context
    if retrieved_chunks:
        for i, chunk in enumerate(retrieved_chunks):
            src_info = f"Source: {chunk['source']}"
            if chunk.get('url'): src_info += f" ({chunk['url']})"
            context_parts.append(f"[Context {i+1}] {src_info}\nContent: {chunk['text']}")
    
    # 2. Preparation for UI source cards (if the model needs to know)
    # The UI handles sources, so we just need text for the AI to summarize
    
    current_date_str = datetime.now().strftime("%B %d, %Y")
    
    if context_parts:
        context_block = "\n\n---\n\n".join(context_parts)
        instruction = "I have retrieved the following relevant snippets from the web and your uploaded documents. Use this information to provide an accurate, comprehensive, and well-structured answer."
    else:
        context_block = "(No specific context found for this query)"
        instruction = f"I searched but couldn't find highly relevant snippets for this query. Please answer based on your internal knowledge, but strictly keep in mind the current date is {current_date_str}."

    return f"""Current Date: {current_date_str}.
You are a highly intelligent AI search agent.

Your primary goal is to synthesize the provided context into a clear, concise, and easy-to-understand answer.

-----------------------------------
TONE AND STYLE
-----------------------------------
1. SIMPLE & ACCESSIBLE: Write in a natural, conversational manner. 
2. DIRECT & CONCISE: Answer the question immediately.
3. INLINE CITATIONS: You MUST cite your claims using bracketed numbers [1], [2], etc., referring to the snippets provided.

-----------------------------------
FORMATTING RULES
-----------------------------------
1. Use paragraphs, bold text, and bullet points.
2. DO NOT include a "Sources" list at the bottom.
3. Provide 3 related questions at the end:

**Related Queries:**
- [Question 1]
- [Question 2]
- [Question 3]

-----------------------------------
USER QUERY:
"{query}"

{instruction}

-----------------------------------
RETRIEVED CONTEXT:
-----------------------------------

{context_block}
"""


# ========== Conversational Prompt ==========
CONVERSATIONAL_SYSTEM_PROMPT = """Current Date: {current_date_str}.
You are a friendly and helpful AI assistant similar to Perplexity's conversational mode.

The user is engaging in general conversation or a greeting. 
Respond naturally, warmly, and concisely. 
You do NOT need to search the web or provide sources for this specific interaction.
Focus on being helpful and inviting for their next search query.

USER QUERY: "{query}"
"""


def generate_fallback_response(query: str, sources: list[dict], error_type: str = "generic") -> str:
    """Generates a best-effort human-readable response using search snippets when LLM fails."""
    if error_type == "quota":
        return "I've reached my daily limit for the Gemini API free tier. Please try again in a little while or check your API quota settings."

    if not sources:
        return "I searched the web but couldn't find definitive information on that right now. Please try a different query."

    # Direct Answer
    top_snippet = sources[0].get('snippet', sources[0].get('title', ''))
    direct_answer = f"Based on the latest available data, {top_snippet}"
    if not direct_answer.endswith('.'):
        direct_answer += "..."

    # Short Explanation
    explanations = []
    for s in sources[1:4]:
        snippet = s.get('snippet', '')
        if snippet and len(snippet) > 20:
            explanations.append(snippet)
    
    explanation_text = " ".join(explanations) if explanations else "Multiple sources corroborate these findings with additional context from the field."

    # Sources (Clean Format)
    sources_list = "\n".join([f"{i+1}. {s['title']} – {s['url']}" for i, s in enumerate(sources[:5])])

    return f"""{direct_answer}

{explanation_text}

Sources:
{sources_list}

Related questions:
- Where can I find more updates on this?
- What are the primary sources for {query}?
- Can you summarize the key points again?"""



# ========== Request Model ==========
class AskRequest(BaseModel):
    query: str
    session_id: str = "default"
    images: list[dict] = None # List of {"data": base64, "mime_type": string}


# ========== API Endpoints ==========
@app.post("/upload")
async def upload_file(session_id: str = Form(...), file: UploadFile = File(...)):
    """Uploads a PDF, TXT, or MD file and adds its content to the RAG session."""
    try:
        filename = file.filename
        content_type = file.content_type
        
        # Fallback for missing/generic content types (common in manual API calls or some browsers)
        if not content_type or content_type == "application/octet-stream":
            import mimetypes
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type and filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                content_type = f"image/{filename.split('.')[-1].replace('jpg', 'jpeg')}"
        
        data = await file.read()
        text = ""

        print(f"[Upload] Processing {filename} ({content_type}) for session {session_id}")

        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            # It's an image - generate a description for semantic RAG
            import base64
            img_b64 = base64.b64encode(data).decode("utf-8")
            
            prompt = "Please provide a detailed description of this image so I can index it for later semantic search and retrieval. Describe objects, text, and overall context."
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": content_type, "data": img_b64}}
                    ]
                }]
            }
            
            print(f"[Upload] Generating description for image: {filename}")
            try:
                r = requests.post(API_URL_NON_STREAM, json=payload, timeout=20)
                if r.status_code == 200:
                    res_data = r.json()
                    # Non-streaming response structure is different
                    try:
                        text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                        text = f"IMAGE DESCRIPTION: {text}"
                    except (KeyError, IndexError):
                        print(f"[Upload] Unexpected JSON structure for image: {res_data}")
                        text = f"Attached image: {filename}"
                else:
                    print(f"[Upload] API Error {r.status_code}: {r.text}")
                    text = f"Attached image: {filename}"
            except Exception as e:
                print(f"[Upload] Image processing failed: {e}")
                text = f"Attached image: {filename}"
        elif filename.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(data))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text: text += page_text + "\n"
        else:
            # Assume text/md
            text = data.decode("utf-8", errors="replace")

        if not text.strip():
            raise HTTPException(status_code=400, detail="No readable content found in file")

        # Chunk and Add to Session
        chunks = RAGManager.chunk_text(text, source=filename)
        await RAGManager.add_to_session(session_id, chunks)

        return {"filename": filename, "chunks": len(chunks), "status": "success"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ask/stream")
async def ask_gemini_stream(request: AskRequest):
    """
    Agentic streaming endpoint:
    1. Search the web for the query
    2. Crawl top results
    3. Inject context into Gemini prompt
    4. Stream the response with source metadata
    """
    if not rate_limiter.is_allowed(request.session_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Maximum 20 requests per minute allowed.")

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    query = request.query.strip()
    history = get_session(request.session_id)

    # ---- Step 1: Determine Search Need & Intent ----
    is_chat = is_conversational(query)
    sources = []
    
    if is_chat:
        print(f"[Chat] Conversational intent detected")
        import datetime as dt
        current_date_str = dt.datetime.now().strftime("%B %d, %Y")
        user_message_text = CONVERSATIONAL_SYSTEM_PROMPT.format(
            current_date_str=current_date_str,
            query=query
        )
    else:
        # ---- Step 2: Semantic Retrieval (Files + Past Web) ----
        # Only call the expensive embedding API if the session actually has uploaded documents
        sess = get_session_data(request.session_id)
        if sess["rag_chunks"] and sess["rag_embeddings"] is not None:
            print(f"[RAG] Checking session context for: {query[:60]}")
            relevant_chunks = await RAGManager.retrieve(query, request.session_id, top_k=20)
        else:
            relevant_chunks = []

        # ---- Step 3: Web Search & Indexing ----
        sources = await web_search(query)
        print(f"[Search] Found {len(sources)} results")
        
        crawled = []
        if sources:
            urls_to_crawl = [s["url"] for s in sources if s["url"]][:5]
            crawled = await crawl_urls(urls_to_crawl)
            
            web_chunks = []
            for c in crawled:
                if c.get("success") and c.get("content"):
                    title = next((s["title"] for s in sources if s["url"] == c["url"]), "Web Source")
                    chunks = RAGManager.chunk_text(c["content"], source=title, url=c["url"])
                    web_chunks.extend(chunks)
            
            if web_chunks:
                # BYPASS slow semantic embedding roundtrips for real-time web results
                # Inject directly into the context window for zero-latency awareness
                relevant_chunks.extend(web_chunks[:20])
        
        user_message_text = build_rag_context_prompt(query, relevant_chunks, search_sources=sources)

    # ---- Step 4: Construct Multimodal Payload ----
    if history and history[-1]["role"] == "user":
        history.pop()

    message_parts = [{"text": user_message_text}]
    
    # Add active images if provided
    if request.images:
        print(f"[Vision] Processing {len(request.images)} attached inline images")
        
        # Explicitly instruct the AI about the attachments in text
        message_parts[0]["text"] += "\n\n[USER ALERT]: I have attached image(s) to this message. Please thoroughly examine and verify the attached image(s) in your response."
        
        for img in request.images:
            message_parts.append({
                "inlineData": {
                    "mimeType": img["mime_type"],
                    "data": img["data"]
                }
            })

    history.append({"role": "user", "parts": message_parts})
    trim_history(history)

    payload = {"contents": history}


    # Meta for UI (all original web searches)
    source_meta = [{"title": s["title"], "url": s["url"]} for s in sources] if sources else []
    collected_text = []

    # Pick the right API URL: fast model for chat, full model for search
    active_api_url = API_URL_FAST if is_chat else API_URL

    def generate_events():
        try:
            if source_meta:
                yield f"__SOURCES__{json.dumps(source_meta)}__END_SOURCES__\n"

            with gemini_session.post(active_api_url, json=payload, stream=True,
                               headers={"Content-Type": "application/json"}) as r:
                if r.status_code != 200:
                    err_type = "quota" if r.status_code in (429, 403) else "generic"
                    print(f"[Backend Error] Gemini API returned {r.status_code} ({err_type}). Triggering fallback.")
                    fallback = generate_fallback_response(query, sources, error_type=err_type)
                    for chunk in fallback.split(" "):
                        yield chunk + " "
                        time.sleep(0.05) # Small delay for "streaming" feel
                    return

                for line in r.iter_lines():
                    if line:
                        decoded = line.decode("utf-8")
                        if decoded.startswith("data: "):
                            json_str = decoded[6:]
                            try:
                                data = json.loads(json_str)
                                if "candidates" in data and len(data["candidates"]) > 0:
                                    part = data["candidates"][0].get("content", {}).get("parts", [{}])[0]
                                    text = part.get("text", "")
                                    if text:
                                        collected_text.append(text)
                                        yield text
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            traceback.print_exc()
            print(f"[Backend Exception] {e}. Triggering fallback.")
            fallback = generate_fallback_response(query, sources)
            for chunk in fallback.split(" "):
                yield chunk + " "
                time.sleep(0.01)
        finally:

            full_response = "".join(collected_text)
            if full_response:
                history.append({"role": "model", "parts": [{"text": full_response}]})
                trim_history(history)
                # PERSIST TO DB
                save_session_to_db(request.session_id)

    return StreamingResponse(generate_events(), media_type="text/plain")


@app.post("/reset")
async def reset_session(session_id: str = "default"):
    if session_id in sessions:
        del sessions[session_id]
    
    # DELETE FROM CLOUD
    try:
        db = get_db()
        db.collection("sessions").document(session_id).delete()
        print(f"[Firebase] Deleted session {session_id} from cloud.")
    except Exception as e:
        print(f"[Firebase] Error deleting session {session_id}: {e}")
    
    return {"status": "ok", "message": f"Session '{session_id}' cleared."}


@app.get("/sessions/stats")
async def session_stats():
    return {
        "active_sessions": len(sessions),
        "crawler_mode": "crawl4ai" if (crawler_instance and CRAWL4AI_AVAILABLE) else "lightweight",
        "sessions": {
            sid: {
                "turns": len(s["history"]) // 2,
                "messages": len(s["history"]),
                "last_access_secs_ago": round(time.time() - s["last_access"])
            }
            for sid, s in sessions.items()
        }
    }


# ========== Static File Serving ==========
@app.get("/")
async def serve_frontend():
    return FileResponse("index.html")

# Mounting static files (css, js, images)
# Note: This is placed after specific routes so it doesn't override them
app.mount("/", StaticFiles(directory="."), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
