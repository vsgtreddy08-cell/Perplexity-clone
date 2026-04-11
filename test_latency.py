import time
import requests

start = time.time()
print("Sending request 'hi'...")
try:
    with requests.post("http://127.0.0.1:8001/ask/stream", json={"query": "hi"}, stream=True) as r:
        print(f"Headers received in {time.time()-start:.2f}s")
        for line in r.iter_lines():
            if line:
                print(line.decode('utf-8'))
except Exception as e:
    print("Error:", e)
print(f"Total time: {time.time()-start:.2f}s")
