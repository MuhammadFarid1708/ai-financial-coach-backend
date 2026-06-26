import os
import json
from openrouter import OpenRouter
from app.models import FinancialProfile

def generate_financial_coaching_insight(user_prompt: str, profile: FinancialProfile) -> dict:
    """
    Asks OpenRouter's Owl Alpha to analyze the financial goal, enforces strict JSON,
    and runs a fallback text generation call if the model leaves 'conversational_response' empty.
    """
    disposable_income = profile.monthly_income - profile.monthly_expenses
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    
    if not api_key:
        return {
            "conversational_response": "System Configuration Error: OPENROUTER_API_KEY is not set.",
            "chart_data": None
        }
        
    system_instructions = (
        "You are an expert AI Financial Coach. Analyze the user's request using their profile metrics "
        "and return a strategy using financial methodologies like 50/30/20 budget allocations, debt compounding, or mutual fund timelines.\n\n"
        f"--- USER PROFILE METRICS ---\n"
        f"- Monthly Net Income: INR {profile.monthly_income}\n"
        f"- Monthly Hard Expenses: INR {profile.monthly_expenses}\n"
        f"- Leftover Disposable Surplus: INR {disposable_income}\n"
        f"- Target Savings Goal: INR {profile.savings_goal}\n"
        f"- Risk Tolerance: {profile.risk_tolerance}\n"
        f"-----------------------------\n\n"
        "CRITICAL RESPONSE REQUIREMENT:\n"
        "You must respond ONLY with a raw JSON object. Do not include markdown code blocks, backticks (```json), or any introductory text. "
        "The JSON object must match this exact schema format:\n"
        "{\n"
        '  "conversational_response": "Write your detailed step-by-step breakdown plan here.",\n'
        '  "chart_data": {\n'
        '    "chart_type": "pie" or "bar" or "line" or null,\n'
        '    "labels": ["Label 1", "Label 2", ...],\n'
        '    "datasets": [\n'
        '      {\n'
        '        "label": "Dataset Title",\n'
        '        "data": [numerical_value_1, numerical_value_2, ...]\n'
        '      }\n'
        '    ]\n'
        '  }\n'
        "}\n\n"
        "Rules for chart_data:\n"
        "- If the user is asking a basic question where a visual breakdown makes no sense, set 'chart_data' to null.\n"
        "- ALWAYS use 'chart_type': 'pie' when breaking down how a user should allocate their monthly budget, surplus, or income percentage across goals, savings, and EMIs.\n"
        "- Use 'chart_type': 'line' only for long-term multi-year compound interest or investment growth projections over time."
    )
    
    with OpenRouter(api_key=api_key) as client:
        # 1. Primary Structured JSON Call
        response = client.chat.send(
            model="openrouter/owl-alpha",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        raw_content = response.choices[0].message.content.strip()
        
        # Clean markdown code wrappers if present
        if raw_content.startswith("```"):
            raw_content = raw_content.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
            if raw_content.startswith("json"):
                raw_content = raw_content[4:].strip()

        try:
            result_json = json.loads(raw_content)
        except Exception:
            result_json = {
                "conversational_response": raw_content,
                "chart_data": None
            }
            
        # ─── 🛡️ THE FAILSAFE HEALING PIPELINE ───
        # If the text string came back completely empty, force a fast fallback text generation call
        if not result_json.get("conversational_response") or result_json["conversational_response"].strip() == "":
            fallback_text_instructions = (
                f"You are an integrated financial analytics platform feature. Write a detailed, professional financial strategy roadmap based on this request: '{user_prompt}'.\n"
                f"Cross reference it with these metrics:\n"
                f"- Monthly Net Income: INR {profile.monthly_income}\n"
                f"- Monthly Hard Expenses: INR {profile.monthly_expenses}\n"
                f"- Disposable Surplus: INR {disposable_income}\n"
                f"- Target Savings Goal: INR {profile.savings_goal}\n"
                f"- Risk Tolerance: {profile.risk_tolerance}\n\n"
                f"CRITICAL CONSTRAINT: Do NOT introduce yourself. Do NOT say 'Hello', 'Hi', 'I am OWL', 'As an AI', or use any greetings. "
                f"Begin your response directly with a markdown heading or the core analytical text strategy immediately. "
                f"Calculate exactly how many months it will take to save up for their goal. Provide actionable milestone steps. Respond with text and markdown only."
            )
            
            fallback_response = client.chat.send(
                model="openrouter/owl-alpha",
                messages=[
                    {"role": "system", "fallback": "financial-coach-engine", "content": fallback_text_instructions},
                    {"role": "user", "content": "Generate the analysis text starting directly with the plan."}
                ]
            )
            
            result_json["conversational_response"] = fallback_response.choices[0].message.content.strip()
        # ─────────────────────────────────────────

        return result_json