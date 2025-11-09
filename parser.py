"""
Expense text parser - hybrid regex + AI-powered parsing
Handles various expense input formats dynamically
"""
import re
import os
from typing import Dict, Optional
from openai import OpenAI

class ExpenseParser:
    def __init__(self):
        # Currency symbols mapping
        self.currency_symbols = {
            '$': 'CAD',  # Default to CAD for dollar symbol
            '€': 'EUR',
            '£': 'GBP',
            '¥': 'JPY',
        }
        # Initialize OpenAI client for AI-powered parsing fallback
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None
    
    def parse_expense_text(self, text: str) -> Optional[Dict]:
        """
        Parse expense text into components using AI-first approach
        Falls back to simple regex only for obvious patterns
        """
        if not text or not isinstance(text, str):
            return None

        text = text.strip()
        if not text:
            return None

        # Quick regex check ONLY for super obvious patterns like "Costco 120"
        # Pattern: merchant + number (most basic case)
        simple_pattern = r'^([a-zA-Z][a-zA-Z\s]{1,30})\s+(\d+(?:\.\d{1,2})?)$'
        simple_match = re.match(simple_pattern, text, re.IGNORECASE)

        if simple_match:
            merchant = simple_match.group(1).strip()
            amount_str = simple_match.group(2)
            amount = self._parse_amount(amount_str)

            if amount and merchant:
                return {
                    'merchant': merchant,
                    'amount': amount,
                    'currency': 'MXN'
                }

        # Everything else goes to AI - this is the PRIMARY parser now
        # This handles:
        # - "And Marissa 155 under restaurants"
        # - "Spent 155 under restaurants, description is Marissa"
        # - "155 for lunch yesterday"
        # - ANY natural language format
        return self._parse_with_ai(text)
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount string to float"""
        if not amount_str:
            return None
            
        try:
            # Remove currency symbols and normalize
            cleaned = amount_str.replace('$', '').replace(',', '.')
            amount = float(cleaned)
            
            # Reasonable bounds check
            if 0 < amount < 1000000:
                return amount
        except (ValueError, TypeError):
            pass
            
        return None
    
    def _extract_currency_from_amount(self, amount_str: str) -> Optional[str]:
        """Extract currency from amount string based on symbols"""
        if not amount_str:
            return None
            
        for symbol, currency in self.currency_symbols.items():
            if symbol in amount_str:
                return currency
                
        return None

    def _parse_with_ai(self, text: str) -> Optional[Dict]:
        """
        AI-powered expense parsing using OpenAI
        Handles ANY natural language format conversationally
        """
        if not self.openai_client:
            return None

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": """You are an expense parser. Extract expense information from natural language.

Output JSON format:
{
  "merchant": "category or merchant name",
  "detail": "description/concept/notes (optional)",
  "amount": numeric value,
  "currency": "MXN" (default) or "CAD", "USD", etc.
}

CRITICAL RULES:
1. Extract the AMOUNT (number) first
2. Look for category hints: "under [category]", "in [category]", "[category]" at the end
3. Common categories: restaurants, groceries, gas, transportation, clothing, entertainment, oxxo, etc.
4. Extract TWO things:
   - "merchant": The CATEGORY name if mentioned (restaurants, groceries, etc.) OR the actual store name if no category
   - "detail": Any description, concept, person name, or notes (this is OPTIONAL, can be null)
5. If text is NOT an expense (like questions or confirmations), return: {"error": "not_an_expense"}

Examples:
- "And Marissa 155 under restaurants" → {"merchant": "restaurants", "detail": "Marissa", "amount": 155, "currency": "MXN"}
- "Spent 155 under restaurants, description is Marissa" → {"merchant": "restaurants", "detail": "Marissa", "amount": 155, "currency": "MXN"}
- "Pan de muerto marisa 60 restaurants" → {"merchant": "restaurants", "detail": "Pan de muerto marisa", "amount": 60, "currency": "MXN"}
- "add 971 in gas categories" → {"merchant": "gas", "detail": null, "amount": 971, "currency": "MXN"}
- "Costco 120 groceries" → {"merchant": "groceries", "detail": "Costco", "amount": 120, "currency": "MXN"}
- "Costco 120" → {"merchant": "Costco", "detail": null, "amount": 120, "currency": "MXN"}
- "I paid 50 bucks for lunch today" → {"merchant": "lunch", "detail": null, "amount": 50, "currency": "MXN"}
- "compré café por 45 pesos" → {"merchant": "café", "detail": null, "amount": 45, "currency": "MXN"}
- "what's my total spending?" → {"error": "not_an_expense"}
- "yes please" → {"error": "not_an_expense"}"""
                }, {
                    "role": "user",
                    "content": text
                }],
                temperature=0.1,
                max_tokens=100,
                response_format={"type": "json_object"}
            )

            import json
            result = json.loads(response.choices[0].message.content)

            # Check if it's an error
            if "error" in result:
                return None

            # Validate required fields
            if "merchant" not in result or "amount" not in result:
                return None

            # Ensure amount is a number
            try:
                amount = float(result["amount"])
                if not (0 < amount < 1000000):
                    return None
            except (ValueError, TypeError):
                return None

            # Extract detail if present
            detail = result.get("detail")
            if detail and detail != "null":
                detail = str(detail).strip()
            else:
                detail = None

            return {
                "merchant": str(result["merchant"]).strip(),
                "detail": detail,
                "amount": amount,
                "currency": result.get("currency", "MXN")
            }

        except Exception as e:
            # If AI parsing fails, return None to avoid breaking the bot
            import logging
            logging.debug(f"AI parsing failed: {e}")
            return None

    def validate_expense_data(self, data: Dict) -> bool:
        """Validate parsed expense data"""
        if not isinstance(data, dict):
            return False
            
        required_fields = ['merchant', 'amount']
        for field in required_fields:
            if field not in data or not data[field]:
                return False
        
        # Check amount is valid number
        try:
            amount = float(data['amount'])
            if not (0 < amount < 1000000):
                return False
        except (ValueError, TypeError):
            return False
        
        # Check merchant is non-empty string
        merchant = data.get('merchant', '').strip()
        if not merchant or len(merchant) < 1:
            return False
            
        return True