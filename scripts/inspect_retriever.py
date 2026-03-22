import requests

health = requests.get("http://localhost:8000/health", timeout=10)
print("health:", health.status_code, health.json())

payload = {
    "question": "որքան է ameriabank-ում սպառողական վարկի տոկոսադրույքը",
    "bank_id": "ameriabank",
    "top_k": 5,
}
resp = requests.post("http://localhost:8000/ask", json=payload, timeout=20)
print("ask:", resp.status_code)
print(resp.json())

