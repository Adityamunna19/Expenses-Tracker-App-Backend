import os
import json
import requests
from openai import AzureOpenAI
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# 1. Initialize the Azure OpenAI Client
# Ensure these keys match your .env file exactly
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version=os.getenv("AZURE_OPENAI_VERSION")
)

class SmartGoalAgent:
    def __init__(self):
        # Browser headers to prevent being blocked by search engines
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

    def fetch_product_data(self, product_name: str):
        """
        Main entry point: Searches the web, then uses Azure GPT-4o to extract price/image.
        """
        try:
            # STEP 1: Search the web for raw text data
            search_query = f"{product_name} official price in India April 2026"
            search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            
            response = requests.get(search_url, headers=self.headers, timeout=10)
            
            # If search fails, we still want the AI to "guess" based on its training data
            web_text = ""
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # Extract first 3000 chars of text to avoid token limits
                web_text = soup.get_text()[:3000]

            # STEP 2: Use Azure GPT-4o to "think" and extract the price
            # We use a strict System Prompt to prevent the "Zero Price" issue
            completion = client.chat.completions.create(
                model=os.getenv("AZURE_DEPLOYMENT_NAME"), # Usually "gpt-4o"
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            "You are a shopping research specialist. Extract the current market price "
                            "for the requested product. Return ONLY a JSON object. "
                            "If you cannot find a price in the text, use your internal knowledge to provide "
                            "an accurate estimate for 2026 prices in India.\n\n"
                            "REQUIRED JSON FORMAT:\n"
                            "{\n"
                            "  \"price\": (float),\n"
                            "  \"title\": (string),\n"
                            "  \"image_keyword\": (string: 1-2 words describing the item for a photo search)\n"
                            "}"
                        )
                    },
                    {"role": "user", "content": f"Product: {product_name}\nWeb context: {web_text}"}
                ],
                response_format={"type": "json_object"}
            )

            # STEP 3: Parse AI response
            ai_data = json.loads(completion.choices[0].message.content)
            
            price = ai_data.get("price", 0)
            title = ai_data.get("title", product_name).title()
            keyword = ai_data.get("image_keyword", "gadget")

            # STEP 4: Build high-quality Unsplash URL
            # This generates a real photo based on the AI's chosen keyword
            image_url = f"https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=500&auto=format&fit=crop" # Default iPhone
            
            if "iphone" not in product_name.lower():
                image_url = f"https://source.unsplash.com/featured/600x400?{keyword.replace(' ', ',')}"

            return {
                "title": title,
                "target_amount": float(price),
                "image_url": image_url,
                "status": "ai_verified"
            }

        except Exception as e:
            print(f"❌ Smart Agent Error: {e}")
            # Robust Fallback to prevent UI crash
            return {
                "title": product_name.title(),
                "target_amount": 50000.0,
                "image_url": "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e?q=80&w=500",
                "status": "fallback"
            }

# Create a single instance to be used by main.py
smart_agent = SmartGoalAgent()