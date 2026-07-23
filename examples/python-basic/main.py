import os

from openai import OpenAI

client = OpenAI(api_key=os.environ["MODELDOCK_API_KEY"], base_url=os.getenv("MODELDOCK_BASE_URL", "http://localhost:8080/v1"))
response = client.chat.completions.create(model="smart-router", messages=[{"role": "user", "content": "Explain fallback routing in one sentence."}])
print(response.choices[0].message.content)
print(response.model_extra.get("modeldock", {}))
