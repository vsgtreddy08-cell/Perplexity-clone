import requests
import json

def test_perplexity_agent():
    print("Testing Perplexity Agentic Search...")
    print("-" * 50)
    
    url = "http://localhost:8001/ask/stream"
    payload = {
        "query": "What was the score of yesterday's IPL match?",
        "session_id": "final_ipl_verification"
    }
    
    try:
        with requests.post(url, json=payload, stream=True) as r:
            if r.status_code != 200:
                print(f"Error: {r.status_code}")
                print(r.text)
                return

            print("STREAMING RESPONSE:")
            print("-" * 20)
            
            sources_found = False
            for line in r.iter_lines():
                if line:
                    text = line.decode("utf-8")
                    
                    # Check for source metadata
                    if "__SOURCES__" in text:
                        print("\n[SOURCES FOUND]:")
                        try:
                            # Split by markers to get the pure JSON string
                            parts = text.split("__SOURCES__")
                            if len(parts) > 1:
                                json_part = parts[1].split("__END_SOURCES__")[0]
                                sources = json.loads(json_part)
                                for i, s in enumerate(sources):
                                    print(f" {i+1}. {s['title']} ({s['url']})")
                                sources_found = True
                        except Exception as e:
                            print(f" (Failed to parse sources JSON: {e})")
                        print("-" * 20)
                        continue
                    
                    # Normal streaming text
                    print(text, end="", flush=True)
            
            print("\n" + "-" * 20)
            print("TEST COMPLETE.")
            
    except Exception as e:
        print(f"\nConnection Error: {e}")

if __name__ == "__main__":
    test_perplexity_agent()
