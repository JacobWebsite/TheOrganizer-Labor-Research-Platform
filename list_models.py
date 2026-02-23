import os
from google import genai

api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    # Try to read from .env manually if not in env
    try:
        with open(".env") as f:
            for line in f:
                if "GOOGLE_API_KEY=" in line:
                    api_key = line.split("=")[1].strip()
    except:
        pass

if not api_key:
    print("ERROR: GOOGLE_API_KEY not found in environment or .env")
    exit(1)

client = genai.Client(api_key=api_key)

print(f"Using API Key: {api_key[:10]}...")
print("Available Models:")
try:
    for model in client.models.list():
        print(f"- {model.name}")
except Exception as e:
    print(f"Failed to list models: {e}")
