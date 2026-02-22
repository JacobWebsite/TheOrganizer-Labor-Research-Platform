"""
Proof-of-concept script to extract subsidiary information from an SEC Exhibit 21
filing using an LLM.

This script demonstrates how to use the OpenAI API with a Pydantic schema to
extract structured data from a real-world HTML document.

Usage:
    # This script is a proof-of-concept and requires an OpenAI API key.
    # 1. Set the OPENAI_API_KEY environment variable.
    # 2. Provide the HTML content of an Exhibit 21 filing.
    python scripts/scraper/extract_ex21.py <path_to_exhibit21.html>
"""
import os
import sys
import json
import openai
from pydantic import BaseModel, Field
from typing import List

# --- Pydantic Schemas for Structured Data ---

class Subsidiary(BaseModel):
    """Represents a single subsidiary company."""
    name: str = Field(description="The full legal name of the subsidiary company.")
    jurisdiction: str = Field(description="The state, province, or country of incorporation/organization.")

class SubsidiaryList(BaseModel):
    """A list of all subsidiary companies found in the document."""
    subsidiaries: List[Subsidiary]

# --- Core Extraction Logic ---

def extract_subsidiaries_from_html(html_content: str) -> SubsidiaryList:
    """
    Uses an LLM to extract a list of subsidiaries from the HTML content of an
    Exhibit 21 filing.

    Args:
        html_content: The raw HTML string of the Exhibit 21 document.

    Returns:
        A SubsidiaryList object containing the extracted data.
    """
    # Ensure the OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable not set.")

    client = openai.OpenAI()

    prompt = f"""
    You are an expert at extracting structured data from SEC filings.
    Please analyze the following HTML content of an SEC Exhibit 21 filing and
    extract all subsidiary companies and their respective jurisdictions of
    incorporation.

    The data should be returned as a JSON object that conforms to the provided
    schema. The list of subsidiaries should be complete.

    HTML Content:
    ---
    {html_content}
    ---
    """

    print("Sending request to LLM for extraction...")

    response = client.chat.completions.create(
        model="gpt-4o",  # Using a powerful model for better accuracy
        messages=[
            {"role": "system", "content": "You are an expert at extracting structured information from SEC filings."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object", "schema": SubsidiaryList.model_json_schema()}
    )

    print("Received response from LLM.")

    # The response content is a JSON string that should match our schema
    extracted_data = json.loads(response.choices[0].message.content)

    # Validate the data with the Pydantic model
    return SubsidiaryList(**extracted_data)

# --- Main Execution ---

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/scraper/extract_ex21.py <path_to_exhibit21.html>")
        sys.exit(1)

    file_path = sys.argv[1]

    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        sys.exit(1)

    print(f"Reading HTML content from {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        html = f.read()

    try:
        subsidiary_data = extract_subsidiaries_from_html(html)

        print("\n--- Extracted Subsidiary Information ---")
        if subsidiary_data.subsidiaries:
            for sub in subsidiary_data.subsidiaries:
                print(f"- {sub.name} ({sub.jurisdiction})")
            print(f"\nTotal subsidiaries extracted: {len(subsidiary_data.subsidiaries)}")
        else:
            print("No subsidiaries were extracted.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
