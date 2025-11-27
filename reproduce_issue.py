import json
import sys
import os

# Mock the parser
class MockParser:
    def parse_expense_text(self, text):
        # Simulate successful parsing of 6182
        if "6182" in text:
            return {
                "merchant": "Costco",
                "amount": 6182.0,
                "currency": "MXN"
            }
        return None

# Mock VannaTrainer to avoid import errors if dependencies are missing
class MockVannaTrainer:
    def __init__(self):
        pass

# Mock modules to avoid heavy imports
import sys
from unittest.mock import MagicMock
sys.modules['vanna_trainer'] = MagicMock()
sys.modules['langchain_openai'] = MagicMock()
sys.modules['langgraph.prebuilt'] = MagicMock()

# Now import the tool class
# We need to manually define the tool class or import it if possible
# But agent.py imports a lot of stuff. 
# Let's try to import agent.py but mock the heavy stuff first.

try:
    from agent import ParseExpenseTool
except ImportError:
    # If import fails, we'll just copy the class logic for reproduction
    # This is safer than dealing with complex dependency chains in a script
    print("Could not import agent.py directly, using copied logic for reproduction")
    
    class ParseExpenseTool:
        def __init__(self, parser):
            self.parser = parser
            
        def _run(self, text: str) -> str:
            # COPY OF THE LOGIC FROM agent.py
            text_lower = text.lower().strip()
            
            # ... (omitting question check for brevity as it's not relevant to this bug)
            
            # Only parse if it really looks like an expense entry
            result = self.parser.parse_expense_text(text)
            
            # Additional validation - if parsed amount is suspiciously high (like a year), reject
            # REMOVED: Limit of 5000 was too low for MXN. Parser has its own 1M limit.
            # if result and result.get('amount', 0) > 5000:  # Expenses over $5000 are suspicious
            #     return json.dumps(None)
                
            return json.dumps(result)

def test_parsing():
    parser = MockParser()
    tool = ParseExpenseTool(parser)
    
    test_input = "I spent 6182 at Costco"
    print(f"Testing input: '{test_input}'")
    
    result = tool._run(test_input)
    print(f"Result: {result}")
    
    parsed = json.loads(result)
    if parsed is None:
        print("FAIL: Result is None (Expected valid JSON)")
        return False
    else:
        print("SUCCESS: Result is valid JSON")
        return True

if __name__ == "__main__":
    success = test_parsing()
    if not success:
        print("Bug reproduced: Expense > 5000 was rejected.")
    else:
        print("Bug NOT reproduced.")
