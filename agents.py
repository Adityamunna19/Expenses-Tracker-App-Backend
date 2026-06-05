import os
import json
import requests
from openai import AzureOpenAI
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version=os.getenv("AZURE_OPENAI_VERSION")
)

class SmartGoalAgent:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }

    def fetch_product_data(self, product_name: str):
        try:
            search_query = f"{product_name} official price in India April 2026"
            search_url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
            response = requests.get(search_url, headers=self.headers, timeout=10)
            
            web_text = ""
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                web_text = soup.get_text()[:3000]

            completion = client.chat.completions.create(
                model=os.getenv("AZURE_DEPLOYMENT_NAME"),
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

            ai_data = json.loads(completion.choices[0].message.content)
            price = ai_data.get("price", 0)
            title = ai_data.get("title", product_name).title()
            keyword = ai_data.get("image_keyword", "gadget")

            image_url = f"https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?q=80&w=500&auto=format&fit=crop"
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
            return {
                "title": product_name.title(),
                "target_amount": 50000.0,
                "image_url": "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e?q=80&w=500",
                "status": "fallback"
            }

   # --- UPDATED FUNCTION FOR SMART EXPENSE ADDING ---
    def parse_transaction_text(self, text: str, available_goals: list, merchant_aliases: dict = None, custom_categories: list = None):
        try:
            goal_context = json.dumps(available_goals)
            aliases_context = json.dumps(merchant_aliases) if merchant_aliases else "None"
            categories_context = ", ".join([f'"{c}"' for c in custom_categories]) if custom_categories else '"Food", "Transport", "Bills", "Shopping", "Entertainment", "Savings", "Goals", "Income", "Refund", "Gift", "Other"'

            system_prompt = f"""
            You are a highly accurate financial parsing assistant. Extract transaction details from the user's text.
            Return ONLY a raw JSON object.
            
            Available Goals for 'Goals' category: {goal_context}
            Merchant Aliases (Original Name -> Alias to use): {aliases_context}
            
            Rules:
            1. Categories MUST be one of the following, or inferred from context: {categories_context}.
            2. If the text implies saving GENERAL money (e.g., "put 500 in savings", "transferred to vault"), set category to "Savings" and linked_goal_id to null.
            3. If the text implies saving money for a SPECIFIC item in the Available Goals list (e.g., "save 2000 for macbook"), set category to "Goals" and find the matching goal 'id' for 'linked_goal_id'.
            4. If spending money on food or transport, DO NOT use "Income" or "Salary".
            5. IMPORTANT ALIAS RULE: If the transaction text mentions a name that exists as a key in the Merchant Aliases, you MUST replace the extracted 'title' with its corresponding mapped value (e.g., if 'kukkala Ramesh' maps to 'Rayudu Tiffins', output 'Rayudu Tiffins').
            
            Examples:
            - "590 KFC" -> {{"title": "KFC", "amount": 590, "category": "Food", "linked_goal_id": null}}
            - "put 10000 in my savings" -> {{"title": "General Savings", "amount": 10000, "category": "Savings", "linked_goal_id": null}}
            - "save 2000 for macbook" -> {{"title": "Macbook Fund", "amount": 2000, "category": "Goals", "linked_goal_id": "uuid-here"}}
            
            Required JSON Format:
            {{
                "title": "Clean Merchant/Source Name",
                "amount": (float),
                "category": "String",
                "linked_goal_id": "UUID string or null"
            }}
            """

            completion = client.chat.completions.create(
                model=os.getenv("AZURE_DEPLOYMENT_NAME"), 
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                response_format={"type": "json_object"}
            )

            result = json.loads(completion.choices[0].message.content)
            return result

        except Exception as e:
            print(f"❌ Smart Parse Error: {e}")
            return {"title": text, "amount": 0, "category": "Other", "linked_goal_id": None}

class ReleaseNotesAgent:
    def generate_release_notes(self, commit_messages: list):
        try:
            system_prompt = """
            You are the Release Notes Agent for a personal finance application.
            Your job is to read an array of recent technical git commit messages and summarize them into a user-friendly release announcement.

            You must return a raw JSON object (without markdown formatting or code blocks) containing exactly these fields:
            - "title": A catchy, short title for the update (e.g., "June Feature Drop").
            - "summary": A 1-2 sentence overview of the most impactful changes.
            - "highlights": An array of objects, where each object has a "title" (2-4 words) and a "description" (1 short sentence explaining the benefit).
            - "cta_label": A short call to action button label (e.g., "Explore now", "Got it").
            - "cta_subtext": A short sentence encouraging the user to try the new features.

            Focus on user-facing features (like UI changes, new categories, budgeting tools). Ignore purely technical chores (like updating dependencies or fixing typos) unless they significantly impact performance or user experience.
            """

            commits_text = "\n".join(commit_messages)
            
            completion = client.chat.completions.create(
                model=os.getenv("AZURE_DEPLOYMENT_NAME"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here are the latest commit messages:\n\n{commits_text}"}
                ],
                response_format={"type": "json_object"}
            )
            
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print(f"❌ Release Notes Agent Error: {e}")
            return None

smart_agent = SmartGoalAgent()
release_agent = ReleaseNotesAgent()