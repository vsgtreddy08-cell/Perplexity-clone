import time
import requests
import json
import sys
import io

# Force UTF-8 for console output to handle emojis on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        # Fallback for older python or restricted environments
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

API_URL = "http://127.0.0.1:8001/ask/stream"
SESSION_ID = "smoke_test_session"

def print_header(title):
    print(f"\n{'='*50}\n[SMOKE TEST] {title}\n{'='*50}")

def run_test(query, expected_intent):
    print(f"-> Testing Query: '{query}'")
    start = time.time()
    
    payload = {
        "query": query,
        "session_id": SESSION_ID
    }
    
    first_chunk_time = None
    chunks = []
    sources = []
    
    try:
        with requests.post(API_URL, json=payload, stream=True, timeout=30) as r:
            if r.status_code != 200:
                print(f"[ERROR] HTTP {r.status_code}: {r.text}")
                return False

            for line in r.iter_lines():
                if line:
                    if first_chunk_time is None:
                        first_chunk_time = time.time() - start
                    
                    text = line.decode("utf-8")
                    if "__SOURCES__" in text:
                        # Extract basic source info
                        parts = text.split("__SOURCES__")
                        if len(parts) > 1:
                            json_part = parts[1].split("__END_SOURCES__")[0]
                            try:
                                sources = json.loads(json_part)
                            except: pass
                        continue
                    chunks.append(text)
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return False
        
    end_time = time.time() - start
    output = "".join(chunks)
    
    print(f"\n[METRICS]")
    print(f"  Time to First Token: {first_chunk_time:.2f}s" if first_chunk_time else "  Time to First Token: N/A")
    print(f"  Total Response Time: {end_time:.2f}s")
    
    print(f"\n[RESPONSE PREVIEW]")
    print(output[:300] + "..." if len(output) > 300 else output)
    
    if expected_intent == "chat":
        if sources:
            print("[FAIL] Chat query incorrectly generated sources!")
            return False
    elif expected_intent == "search":
        print(f"\n[SOURCES RETRIEVED]: {len(sources)}")
        for i, s in enumerate(sources):
            print(f"  {i+1}. {s.get('title')} ({s.get('url')[:60]}...)")
        if not sources:
            print("[WARN] Search query found no sources (Might be blocked or rate-limited).")
            
    print("\n[PASS] Test completed successfully.")
    return True

if __name__ == "__main__":
    print_header("Initializing Backend Connect")
    # Ping
    try:
        requests.get("http://127.0.0.1:8001/", timeout=2)
        print("Backend is ONLINE.")
    except Exception as e:
        print("Backend is OFFLINE. Cannot run tests.")
        sys.exit(1)
        
    print_header("Test 1: Conversational Intent ('hi')")
    run_test("hi", expected_intent="chat")
    
    print_header("Test 2: Search Intent ('What is the stock price of AAPL')")
    run_test("What is the stock price of AAPL", expected_intent="search")
    
    print("\nAll tests completed.")
