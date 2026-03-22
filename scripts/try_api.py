import requests

payload = {
    "question": "ACBA-ում ինչ ավանդային տարբերակներ կան?",
    "bank_id": "acba",
    "top_k": 3,
}

resp = requests.post("http://localhost:8000/ask", json=payload, timeout=20)
print(resp.status_code)
print(resp.json())

