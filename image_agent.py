import os
import json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version=os.getenv("AZURE_OPENAI_VERSION")
)

class ImageAnalyzerAgent:
    def analyze_screenshot(self, base64_image: str):
        try:
            completion = client.chat.completions.create(
                model=os.getenv("AZURE_DEPLOYMENT_NAME"),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a financial OCR specialist. Analyze the payment screenshot. "
                            "Extract details and return a JSON object with these EXACT keys: "
                            "'title' (the merchant name), 'amount' (number), 'date' (YYYY-MM-DD), "
                            "'payment_method' (UPI or Card), and 'bank_hint' (e.g., sbi, hdfc, kvb)."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract details from this receipt:"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                response_format={"type": "json_object"}
            )
            
            raw_data = json.loads(completion.choices[0].message.content)
            
            # NORMALIZATION: Ensure keys match your Frontend formData state
            return {
                "title": raw_data.get("title", "New Expense"),
                "amount": raw_data.get("amount", 0),
                "date": raw_data.get("date", ""),
                "payment_method": raw_data.get("payment_method", "UPI"),
                "bank_hint": raw_data.get("bank_hint", "").lower()
            }
        except Exception as e:
            print(f"Vision Error: {e}")
            return None
image_agent = ImageAnalyzerAgent()