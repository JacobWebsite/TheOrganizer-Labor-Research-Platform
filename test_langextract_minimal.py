import os
import logging
from langextract import langextract

# Setup logging to see what's happening inside langextract
logging.basicConfig(level=logging.DEBUG)

def test_minimal():
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    
    # Define 1 simple class
    classes = [
        langextract.ExtractionClass(
            name="test_class",
            description="A test class to verify connectivity.",
            schema=langextract.Schema({"found_word": str})
        )
    ]
    
    print("Initializing Extractor...")
    try:
        # Trying the most common model ID
        extractor = langextract.Extractor(
            classes=classes,
            model_id="gemini-1.5-flash", 
            api_key=api_key
        )
        
        test_text = "The quick brown fox jumps over the lazy dog. The keyword is Apple."
        print("Running minimal extraction...")
        
        results = extractor.extract(test_text)
        print(f"Results: {results}")
        for res in results:
            print(f"Extracted: {res.data} from '{res.verbatim_text}'")
            
    except Exception as e:
        print(f"Minimal test failed: {e}")

if __name__ == "__main__":
    test_minimal()
