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
        Parse expense text into components
        Supports formats like:
        - "Costco 120.54"
        - "120.54 supermarket"
        - "$57.74 supermarket"
        - "57.74 CAD supermarket"
        - "add 971 in gas"
        - "spent 120 on coffee"
        - "paid 50 for lunch"
        """
        if not text or not isinstance(text, str):
            return None

        text = text.strip()
        if not text:
            return None

        # Pattern C: Natural language → "add/spent/paid [amount] in/on/for [merchant/category]"
        # Handles: "add 971 in gas", "spent 120 on coffee", "paid 50 for lunch"
        pattern_c = r'^(?:add|spent|paid|record|gastado?|pague?)\s+(\$?\d+[\d\.,]*)\s+(?:in|on|for|en|de|para)\s+(.+?)(?:\s+categor(?:y|ies|ía|ías))?$'
        match_c = re.match(pattern_c, text, re.IGNORECASE)

        if match_c:
            amount_str = match_c.group(1)
            merchant = match_c.group(2).strip()

            amount = self._parse_amount(amount_str)
            if amount is None:
                return None

            if not merchant:
                return None

            return {
                'merchant': merchant,
                'amount': amount,
                'currency': self._extract_currency_from_amount(amount_str) or 'MXN'
            }

        # Pattern A: merchant first → "Costco 120.54 [CAD]"
        pattern_a = r'^([^\d]+?)\s+(\$?\d[\d\.,]*)\s*([A-Za-z]{3})?$'
        match_a = re.match(pattern_a, text, re.IGNORECASE)
        
        if match_a:
            merchant = match_a.group(1).strip()
            amount_str = match_a.group(2)
            currency = match_a.group(3)
            
            amount = self._parse_amount(amount_str)
            if amount is None:
                return None
                
            return {
                'merchant': merchant,
                'amount': amount,
                'currency': currency or self._extract_currency_from_amount(amount_str) or 'MXN'
            }
        
        # Pattern B: amount first → "120.54 supermarket" or "$57.74 supermarket" or "57.74 CAD supermarket"
        pattern_b = r'^(\$?\d+[\d\.,]*)\s*(?:([A-Za-z]{3})\s+)?(.+)$'
        match_b = re.match(pattern_b, text, re.IGNORECASE)

        if match_b:
            amount_str = match_b.group(1)
            currency = match_b.group(2)
            merchant = match_b.group(3).strip()

            amount = self._parse_amount(amount_str)
            if amount is None:
                return None

            if not merchant:
                return None

            return {
                'merchant': merchant,
                'amount': amount,
                'currency': currency or self._extract_currency_from_amount(amount_str) or 'MXN'
            }

        # FALLBACK: AI-powered parsing for any natural language
        # This makes the parser truly dynamic and conversational
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
  "merchant": "merchant or category name",
  "amount": numeric value,
  "currency": "MXN" (default) or "CAD", "USD", etc.
}

If the text is NOT an expense, return: {"error": "not_an_expense"}

Examples:
- "add 971 in gas categories" → {"merchant": "gas", "amount": 971, "currency": "MXN"}
- "I paid 50 bucks for lunch today" → {"merchant": "lunch", "amount": 50, "currency": "MXN"}
- "compré café por 45 pesos" → {"merchant": "café", "amount": 45, "currency": "MXN"}
- "what's my total spending?" → {"error": "not_an_expense"}"""
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

            return {
                "merchant": str(result["merchant"]).strip(),
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