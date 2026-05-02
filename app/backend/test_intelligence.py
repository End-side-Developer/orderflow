import httpx
import json

r = httpx.post(
    'http://127.0.0.1:8000/api/v1/intelligence/judgment-decisions',
    json={
        'document_id':'1127182f-e525-4048-9b68-7909b2dfd132',
        'page_number':1,
        'full_text':'hello world, the payment of 500 dollars is ordered.',
        'text':'hello world, the payment of 500 dollars is ordered.',
        'extraction_mode':'ai'
    },
    timeout=30
)
print("Decision:", r.status_code, r.text)
