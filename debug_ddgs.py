from duckduckgo_search import DDGS
from datetime import datetime, timedelta

def debug_search():
    current_date = datetime.now() # April 8 2026
    yesterday = current_date - timedelta(days=1)
    yesterday_str = yesterday.strftime("%B %d, %Y")
    
    queries = [
        "What was the score of yesterday's IPL match?",
        f"IPL match result {yesterday_str}",
        "IPL match score April 7 2026"
    ]
    
    print(f"Current Date: {current_date.strftime('%B %d, %Y')}")
    print(f"Yesterday: {yesterday_str}")
    print("-" * 50)
    
    with DDGS() as ddgs:
        for q in queries:
            print(f"Testing Query: {q}")
            try:
                # Try News first
                news = list(ddgs.news(q, max_results=3, timelimit='d'))
                print(f"  News Results: {len(news)}")
                for r in news:
                    print(f"    - {r['title']} ({r['url'][:50]}...)")
                
                # Try Text
                text = list(ddgs.text(q, max_results=3))
                print(f"  Text Results: {len(text)}")
                for r in text:
                    print(f"    - {r['title']} ({r['href'][:50]}...)")
            except Exception as e:
                print(f"  ERROR: {e}")
            print("-" * 20)

if __name__ == "__main__":
    debug_search()
