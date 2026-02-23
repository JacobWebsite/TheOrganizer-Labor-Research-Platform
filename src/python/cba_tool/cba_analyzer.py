import os
import json
import logging
from google import genai
from google.genai import types
import re

logger = logging.getLogger(__name__)

class CBAAnalyzer:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        if not self.api_key:
            logger.error("No GOOGLE_API_KEY found. Using Gemini will fail.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
            self.model_id = "gemini-2.0-flash-001"

        self.system_prompt_path = os.path.join(
            os.path.dirname(__file__), 
            '../../../config/cba_system_prompt.md'
        )
        self.load_system_prompt()

    def load_system_prompt(self):
        try:
            with open(self.system_prompt_path, 'r') as f:
                content = f.read()
                self.system_prompt = content + "\n\nCRITICAL: For every extraction, you MUST include 'exact_quote' which is the verbatim text from the document. This is for legal auditing."
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            self.system_prompt = "Extract CBA provisions with exact_quote in JSON."

    def is_cba(self, text_sample):
        if not self.client: return False
        try:
            prompt = f"Identify if this is a CBA. Respond ONLY with YES or NO.\n\nText: {text_sample[:2000]}"
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return "YES" in response.text.upper()
        except Exception as e:
            logger.error(f"is_cba check failed: {e}")
            return False

    def extract_provisions(self, text_chunk):
        if not self.client: return {"extractions": []}
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=f"{self.system_prompt}\n\nDocument Text:\n{text_chunk}",
                config=types.GenerateContentConfig(
                    response_mime_type='application/json'
                )
            )
            return json.loads(response.text)
        except Exception as e:
            logger.error(f"Gemini extraction failed: {e}")
            return {"extractions": []}

    def find_offsets(self, pages, quote):
        if not quote or len(quote) < 10:
            return None
        clean_quote = re.sub(r'\s+', ' ', quote).strip()
        for p in pages:
            clean_page = re.sub(r'\s+', ' ', p["content"])
            match = re.search(re.escape(clean_quote), clean_page, re.IGNORECASE)
            if match:
                return {
                    "page": p["page"],
                    "char_start": match.start(),
                    "char_end": match.end()
                }
        return None
