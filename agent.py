"""
LangChain Agent for FinAIssistant
Handles natural language queries and orchestrates expense management
"""
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type

from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

# Import Vanna for improved SQL generation
from vanna_trainer import VannaTrainer

class ParseExpenseInput(BaseModel):
    text: str = Field(description="Text to parse for expense information")

class ClassifyExpenseInput(BaseModel):
    merchant: str = Field(description="Merchant name to classify")

class InsertExpenseInput(BaseModel):
    user_id: int = Field(description="User ID")
    category_id: int = Field(description="Category ID")
    merchant: str = Field(description="Merchant name")
    amount: float = Field(description="Expense amount")
    currency: str = Field(default="MXN", description="Currency code")

class CurrencyConvertInput(BaseModel):
    amount: float = Field(description="Amount to convert")
    from_currency: str = Field(description="Source currency")
    to_currency: str = Field(description="Target currency")

class SqlQueryInput(BaseModel):
    question: str = Field(description="Natural language question about expenses, spending, budgets, or analytics. The tool will intelligently route to predefined templates or generate custom SQL as needed.")
    query_type: Optional[str] = Field(default=None, description="[OPTIONAL] Specific query type if you want to force a particular template. Usually leave this empty to let intelligent routing decide.")
    custom_sql: Optional[str] = Field(default=None, description="Custom SQL query if query_type is 'custom'")
    month: Optional[str] = Field(default=None, description="Month name for custom queries (e.g., 'july')")
    year: Optional[int] = Field(default=None, description="Year for custom queries (e.g., 2025)")

class ParseExpenseTool(BaseTool):
    name: str = "parse_expense"
    description: str = "Parse free text into merchant, amount, currency if it looks like an expense. Returns null if not parsable."
    args_schema: Type[BaseModel] = ParseExpenseInput
    parser: Any = None
    
    def __init__(self, parser, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'parser', parser)
    
    def _run(self, text: str) -> str:
        # Enhanced logic to avoid parsing questions as expenses
        text_lower = text.lower().strip()
        
        # Check if this looks like a question rather than an expense
        question_indicators = [
            'give me', 'show me', 'tell me', 'what', 'how', 'when', 'where', 'why',
            'spending', 'spends', 'spent', 'expenses', 'total', 'breakdown', 'analysis',
            'compare', 'comparison', 'categories', 'category', 'summary', 'report'
        ]
        
        if any(indicator in text_lower for indicator in question_indicators):
            # This looks like a question, return null to indicate no expense parsing
            return json.dumps(None)
        
        # Check for year patterns that suggest analysis (like "july 2025")
        if re.search(r'\\b(20\\d{2})\\b', text_lower):
            return json.dumps(None)
        
        # Check for month names followed by years (common in questions)
        month_year_pattern = r'\\b(january|february|march|april|may|june|july|august|september|october|november|december)\\s+(20\\d{2})\\b'
        if re.search(month_year_pattern, text_lower):
            return json.dumps(None)
        
        # Only parse if it really looks like an expense entry
        result = self.parser.parse_expense_text(text)
        
        # Additional validation - if parsed amount is suspiciously high (like a year), reject
        if result and result.get('amount', 0) > 5000:  # Expenses over $5000 are suspicious
            return json.dumps(None)
            
        return json.dumps(result)

class ClassifyExpenseTool(BaseTool):
    name: str = "classify_expense"
    description: str = "Classify a merchant/description into one of the known categories by name."
    args_schema: Type[BaseModel] = ClassifyExpenseInput
    db_client: Any = None
    classifier: Any = None
    
    def __init__(self, db_client, classifier, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'db_client', db_client)
        object.__setattr__(self, 'classifier', classifier)
    
    async def _arun(self, merchant: str) -> str:
        categories = await self.db_client.get_categories()
        result = await self.classifier.classify_expense(merchant, categories)
        return json.dumps({
            "categoryName": result.get('category_name'),
            "categoryId": result.get('category_id'),
            "confidence": result.get('confidence', 0.0)
        })
    
    def _run(self, merchant: str) -> str:
        # Sync version for compatibility
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(merchant))

class InsertExpenseTool(BaseTool):
    name: str = "insert_expense"
    description: str = "Insert an expense row into the database"
    args_schema: Type[BaseModel] = InsertExpenseInput
    db_client: Any = None
    
    def __init__(self, db_client, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'db_client', db_client)
    
    async def _arun(self, user_id: int, category_id: int, merchant: str, amount: float, currency: str = "MXN") -> str:
        try:
            # Convert Telegram user_id to internal UUID user_id
            user_data = await self.db_client.get_user_by_telegram_id(int(user_id))
            if not user_data:
                raise Exception(f"User not found for Telegram ID: {user_id}")
            
            internal_user_id = user_data['id']  # This is the UUID
            
            # Get all categories to find the UUID for the given category_id (integer)
            categories = await self.db_client.get_categories()
            if not categories:
                raise Exception("No categories found in database")
            
            # Find category by position/index (LangChain agent passes category index as integer)
            if isinstance(category_id, int) and 0 <= category_id < len(categories):
                category_uuid = categories[category_id]['id']  # This is the UUID
            else:
                # Fallback: treat category_id as already a UUID string
                category_uuid = str(category_id)
            
            await self.db_client.insert_expense(
                user_id=internal_user_id,
                category_id=category_uuid,
                merchant=merchant,
                amount=amount,
                currency=currency
            )
            return "ok"
        except Exception as e:
            raise Exception(f"Database error inserting expense: {str(e)}")
    
    def _run(self, user_id: int, category_id: int, merchant: str, amount: float, currency: str = "MXN") -> str:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(user_id, category_id, merchant, amount, currency))

class CurrencyConvertTool(BaseTool):
    name: str = "convert_currency"
    description: str = "Convert an amount between currencies using currency_rates table. If missing, return original."
    args_schema: Type[BaseModel] = CurrencyConvertInput
    db_client: Any = None
    
    def __init__(self, db_client, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'db_client', db_client)
    
    async def _arun(self, amount: float, from_currency: str, to_currency: str) -> str:
        from_curr = (from_currency or 'MXN').upper()
        to_curr = (to_currency or 'MXN').upper()
        
        if from_curr == to_curr:
            return json.dumps({"amount": amount, "rate": 1})
        
        try:
            rate_data = await self.db_client.get_currency_rate(from_curr, to_curr)
            if not rate_data:
                return json.dumps({"amount": amount, "rate": 1, "note": "rate_missing"})
            
            rate = rate_data['rate']
            converted = amount * rate if rate_data['direct'] else amount / rate
            return json.dumps({"amount": converted, "rate": rate})
        except Exception:
            return json.dumps({"amount": amount, "rate": 1, "note": "error"})
    
    def _run(self, amount: float, from_currency: str, to_currency: str) -> str:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(amount, from_currency, to_currency))

class SqlQueryTool(BaseTool):
    name: str = "sql_query" 
    description: str = """Execute predefined SQL queries for expense analytics. Available query types:

TOTALS:
- 'week_total': Total spending in last 7 days 
- 'month_total': Total spending this month (current month)
- 'today_total': Total spending today only
- 'yesterday_total': Total spending yesterday only
- 'total_budget': Total budget amount for current month

CATEGORY BREAKDOWNS:
- 'month_by_category': This month's spending by category with counts and percentages
- 'today_by_category': Today's spending by category
- 'yesterday_by_category': Yesterday's spending by category  
- 'custom_month_category': Specific month/year spending by category (requires month='july', year=2025)

BUDGET ANALYSIS:
- 'budget_vs_spending': Current month budget vs actual spending with progress %
- 'custom_month_budget': Historical month budget vs spending (requires month='july', year=2025)

TRANSACTION HISTORY:
- 'recent_expenses': Last 10 expenses with details, categories, dates, and users

CUSTOM QUERIES:
- 'dynamic_sql': Auto-generate SQL for complex questions not covered above (requires question parameter)
- 'custom': Execute provided custom SQL (requires custom_sql parameter)

Use 'dynamic_sql' for questions that don't match predefined templates. The system will generate appropriate SQL automatically."""
    args_schema: Type[BaseModel] = SqlQueryInput
    db_client: Any = None
    templates: Any = None
    vanna_trainer: Any = None
    
    def __init__(self, db_client, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'db_client', db_client)
        
        # Initialize Vanna AI for improved SQL generation
        import logging
        logger = logging.getLogger(__name__)
        try:
            vanna = VannaTrainer(
                api_key=os.getenv('OPENAI_API_KEY'),
                model='gpt-4o'
            )
            # Train Vanna on database schema and examples
            vanna.train_all()
            object.__setattr__(self, 'vanna_trainer', vanna)
            logger.info("✅ Vanna AI integrated and trained")
        except Exception as e:
            logger.warning(f"⚠️ Vanna initialization failed, falling back to GPT-4: {e}")
            object.__setattr__(self, 'vanna_trainer', None)
        
        # Predefined safe SQL templates (family expense tracking)
        templates = {
            "week_total": """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM expenses e
            WHERE e.expense_date >= (CURRENT_DATE - INTERVAL '7 days')
              AND e.expense_date <= CURRENT_DATE
            """,
            
            "month_total": """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM expenses e
            WHERE DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', CURRENT_DATE)
            """,
            
            "month_by_category": """
            SELECT c.name as category, SUM(e.amount) as total, COUNT(*) as count
            FROM expenses e
            JOIN categories c ON c.id = e.category_id
            WHERE DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY c.name, c.id
            ORDER BY total DESC
            """,
            
            "recent_expenses": """
            SELECT e.expense_detail, e.amount, c.name as category, e.expense_date, u.name as user_name
            FROM expenses e
            JOIN categories c ON c.id = e.category_id
            JOIN users u ON u.id = e.user_id
            ORDER BY e.expense_date DESC, e.created_at DESC
            LIMIT 10
            """,
            
            "today_total": """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM expenses e
            WHERE DATE(e.expense_date) = CURRENT_DATE
            """,
            
            "yesterday_total": """
            SELECT COALESCE(SUM(amount), 0) as total
            FROM expenses e
            WHERE DATE(e.expense_date) = (CURRENT_DATE - INTERVAL '1 day')
            """,
            
            "today_by_category": """
            SELECT c.name as category, SUM(e.amount) as total, COUNT(*) as count
            FROM expenses e
            JOIN categories c ON c.id = e.category_id
            WHERE DATE(e.expense_date) = CURRENT_DATE
            GROUP BY c.name, c.id
            ORDER BY total DESC
            """,
            
            "yesterday_by_category": """
            SELECT c.name as category, SUM(e.amount) as total, COUNT(*) as count
            FROM expenses e
            JOIN categories c ON c.id = e.category_id
            WHERE DATE(e.expense_date) = (CURRENT_DATE - INTERVAL '1 day')
            GROUP BY c.name, c.id
            ORDER BY total DESC
            """,
            
            "total_budget": """
            SELECT COALESCE(SUM(b.amount), 0) as total
            FROM budgets b
            WHERE b.month = EXTRACT(MONTH FROM CURRENT_DATE)
              AND b.year = EXTRACT(YEAR FROM CURRENT_DATE)
            """,
            
            "budget_vs_spending": """
            WITH static_budgets AS (
                SELECT b.category_id, c.name as category_name, b.amount as budget_amount
                FROM budgets b
                JOIN categories c ON c.id = b.category_id
                WHERE b.month = EXTRACT(MONTH FROM CURRENT_DATE)
                  AND b.year = EXTRACT(YEAR FROM CURRENT_DATE)
            ),
            current_month_spending AS (
                SELECT e.category_id, SUM(e.amount) as spent_amount
                FROM expenses e
                WHERE DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', CURRENT_DATE)
                GROUP BY e.category_id
            )
            SELECT 
                sb.category_name,
                COALESCE(sb.budget_amount, 0) as budget,
                COALESCE(cms.spent_amount, 0) as spent,
                COALESCE(sb.budget_amount, 0) - COALESCE(cms.spent_amount, 0) as remaining,
                CASE 
                    WHEN sb.budget_amount > 0 
                    THEN ROUND((COALESCE(cms.spent_amount, 0) / sb.budget_amount * 100), 1) 
                    ELSE 0 
                END as percent_used
            FROM static_budgets sb
            LEFT JOIN current_month_spending cms ON sb.category_id = cms.category_id
            ORDER BY percent_used DESC
            """
        }
        object.__setattr__(self, 'templates', templates)
    
    async def _generate_sql(self, question: str) -> str:
        """
        Generate SQL query using Vanna AI (RAG-based) or fallback to GPT-4
        Vanna provides better accuracy through database-specific training
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # Try Vanna first (preferred method)
        if self.vanna_trainer:
            try:
                logger.info(f"🤖 Using Vanna AI for SQL generation: {question}")
                sql = self.vanna_trainer.generate_sql(question)
                
                # Clean up the SQL
                sql = sql.strip()
                if sql.startswith('```sql'):
                    sql = sql[6:]
                elif sql.startswith('```'):
                    sql = sql[3:]
                if sql.endswith('```'):
                    sql = sql[:-3]
                sql = sql.rstrip(';').strip()
                
                return sql
            except Exception as e:
                logger.warning(f"⚠️ Vanna generation failed, falling back to GPT-4: {e}")
        
        # Fallback to direct GPT-4 prompting
        logger.info("🔄 Falling back to direct GPT-4 SQL generation")
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        schema_info = """
        Database Schema:
        - expenses(id, user_id, category_id, expense_detail, amount, currency, expense_date, paid_by, timestamp)
          * paid_by is TEXT field containing user name, NOT a foreign key  
        - categories(id, name, description)
        - budgets(id, category_id, amount, currency, month, year) - month is INTEGER 1-12, year is INTEGER (e.g., 2025)
        - users(id, name, telegram_id)
        - currency_rates(base_currency, target_currency, rate)
        
        Relations:
        - expenses.category_id → categories.id
        - expenses.user_id → users.id  
        - budgets.category_id → categories.id
        - expenses.paid_by is TEXT (user name), use as-is or LEFT JOIN users ON expenses.paid_by = users.name
        
        Important:
        - When querying budgets, ALWAYS filter by both month AND year
        - Use: WHERE month = EXTRACT(MONTH FROM CURRENT_DATE) AND year = EXTRACT(YEAR FROM CURRENT_DATE)
        """
        
        prompt = f"""Generate a safe PostgreSQL SELECT query for this question: "{question}"

{schema_info}

Requirements:
- Only SELECT statements allowed
- Use proper JOINs for relations
- Include currency formatting (assume MXN)  
- Use proper date filtering with PostgreSQL functions
- Family expense tracking - query all expenses, not user-specific
- Return meaningful column names
- Limit results to reasonable amounts (max 100 rows)
- Return ONLY the SQL query, no code blocks, no semicolons, no explanation

Question: {question}

SQL Query:"""

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300
        )
        
        raw_sql = response.choices[0].message.content.strip()
        
        # Clean up the SQL
        sql = raw_sql
        if sql.startswith('```sql'):
            sql = sql[6:]
        elif sql.startswith('```'):
            sql = sql[3:]
        if sql.endswith('```'):
            sql = sql[:-3]
        sql = sql.rstrip(';').strip()
        
        return sql

    async def _consult_sql_library(self, question: str) -> Dict[str, Any]:
        """Consult the SQL Library Agent to find matching templates"""
        from openai import AsyncOpenAI
        import os
        
        client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Build comprehensive template descriptions
        template_descriptions = []
        for template_name, sql in self.templates.items():
            if template_name == "week_total":
                template_descriptions.append("week_total: Total spending in last 7 days")
            elif template_name == "month_total": 
                template_descriptions.append("month_total: Total spending in current month")
            elif template_name == "today_total":
                template_descriptions.append("today_total: Total spending today")
            elif template_name == "yesterday_total":
                template_descriptions.append("yesterday_total: Total spending yesterday")
            elif template_name == "total_budget":
                template_descriptions.append("total_budget: Total budget amount for current month")
            elif template_name == "month_by_category":
                template_descriptions.append("month_by_category: Spending breakdown by category for current month")
            elif template_name == "today_by_category":
                template_descriptions.append("today_by_category: Today's spending by category")
            elif template_name == "yesterday_by_category":
                template_descriptions.append("yesterday_by_category: Yesterday's spending by category")
            elif template_name == "budget_vs_spending":
                template_descriptions.append("budget_vs_spending: Compare budget vs actual spending for current month")
            elif template_name == "recent_expenses":
                template_descriptions.append("recent_expenses: List recent expenses (individual records)")
            elif template_name == "top_categories_period":
                template_descriptions.append("top_categories_period: Top spending categories for a date range")
        
        templates_list = "\n".join(template_descriptions)
        
        consultant_prompt = f"""You are the SQL Library Consultant. Your job is to determine if a user question can be answered with existing SQL templates.

Available SQL Templates:
{templates_list}

User Question: "{question}"

Analyze the question and determine:
1. Can this be answered with one of the existing templates?
2. If YES, which template should be used?
3. If NO, explain why it needs custom SQL generation

Respond in JSON format:
{{
  "has_template": true/false,
  "template_name": "template_name" or null,
  "reasoning": "explanation of your decision"
}}

Examples:
- "how much did I spend this week" → {{"has_template": true, "template_name": "week_total", "reasoning": "Direct match for weekly spending total"}}
- "top 5 expenses this year" → {{"has_template": false, "template_name": null, "reasoning": "Requires custom SQL for top N with yearly filter and individual records"}}
"""

        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": consultant_prompt}],
            temperature=0.1,
            max_tokens=200
        )
        
        try:
            import json
            result = json.loads(response.choices[0].message.content.strip())
            return result
        except:
            # Fallback if JSON parsing fails
            return {"has_template": False, "template_name": None, "reasoning": "JSON parsing failed"}
    
    async def _arun(self, question: str, query_type: Optional[str] = None, custom_sql: Optional[str] = None, month: Optional[str] = None, year: Optional[int] = None) -> str:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"SqlQueryTool._arun called with: query_type={query_type}, question={question}")
            
            # NEW: Multi-agent consultation system
            if question and not query_type:
                # Step 1: Consult SQL Library Agent
                logger.info(f"Consulting SQL Library Agent for question: {question}")
                consultation = await self._consult_sql_library(question)
                
                logger.info(f"SQL Library consultation result: {consultation}")
                
                if consultation.get("has_template"):
                    # Use the recommended template
                    query_type = consultation["template_name"]
                    logger.info(f"SQL Library Agent recommends template: {query_type}")
                else:
                    # No template found, use dynamic SQL
                    query_type = "dynamic_sql"
                    logger.info(f"No template found, using dynamic SQL. Reason: {consultation.get('reasoning')}")
            
            if query_type == 'dynamic_sql' and question:
                logger.info(f"Generating dynamic SQL for question: {question}")
                # Generate SQL automatically for questions not covered by predefined templates
                sql = await self._generate_sql(question)
                logger.info(f"Generated SQL: {sql}")
                
                # Apply safety checks to generated SQL
                if not sql.strip():
                    logger.error("Empty SQL generated")
                    raise Exception("Failed to generate SQL")
                
                # More precise safety checks - block SQL injection patterns but allow legitimate SQL
                dangerous_patterns = [
                    r';\s*\w',  # Multiple statements (semicolon followed by more SQL)
                    r'--\s',  # SQL comments with space after
                    r'/\*.*\*/',  # Block comments
                    r'\bdrop\b',  # DROP statements
                    r'\bdelete\b',  # DELETE statements
                    r'\bupdate\b',  # UPDATE statements
                    r'\binsert\b',  # INSERT statements
                    r'\balter\b',  # ALTER statements
                    r'\bcreate\b',  # CREATE statements
                ]
                
                # Check each pattern individually for better debugging
                for pattern in dangerous_patterns:
                    if re.search(pattern, sql, re.IGNORECASE):
                        logger.error(f"SQL rejected by pattern '{pattern}': {sql}")
                        raise Exception(f"Generated SQL rejected by guardrails: pattern '{pattern}' matched")
                
                if not re.match(r'^\s*select', sql, re.IGNORECASE):
                    logger.error(f"SQL rejected - not a SELECT statement: {sql}")
                    raise Exception("Generated SQL rejected by guardrails: not a SELECT statement")
                
                logger.info(f"SQL passed safety checks, executing...")
                result = await self.db_client.execute_raw_sql(sql, [], "dynamic_sql", question)
            elif query_type == 'custom' and custom_sql:
                # Safety checks for custom SQL
                if not custom_sql.strip():
                    raise Exception("Empty query")
                # Apply same safety checks as dynamic SQL
                dangerous_patterns = [
                    r';',  # Multiple statements
                    r'--\s',  # SQL comments with space after
                    r'/\*.*\*/',  # Block comments
                    r'\bdrop\b',  # DROP statements
                    r'\bdelete\b',  # DELETE statements
                    r'\bupdate\b',  # UPDATE statements
                    r'\binsert\b',  # INSERT statements
                    r'\balter\b',  # ALTER statements
                    r'\bcreate\b',  # CREATE statements
                ]
                if any(re.search(pattern, custom_sql, re.IGNORECASE) for pattern in dangerous_patterns) or not re.match(r'^\s*select', custom_sql, re.IGNORECASE):
                    raise Exception("Query rejected by guardrails")
                sql = custom_sql
            elif query_type == 'custom_month_category':
                # Handle specific month/year category breakdown
                if not month or not year:
                    raise Exception("Month and year required for custom_month_category")
                
                # Pass month/year info to database via template name
                template_name = f"custom_month_category_{month.lower()}_{year}"
                sql = "-- Custom month category query"
                result = await self.db_client.execute_raw_sql(sql, [month.lower(), year], template_name, None)
            elif query_type == 'custom_month_budget':
                # Handle specific month/year budget vs spending analysis
                if not month or not year:
                    raise Exception("Month and year required for custom_month_budget")
                
                # Pass month/year info to database via template name
                template_name = f"custom_month_budget_{month.lower()}_{year}"
                sql = "-- Custom month budget query"
                result = await self.db_client.execute_raw_sql(sql, [month.lower(), year], template_name, None)
            elif query_type in self.templates:
                sql = self.templates[query_type]
                result = await self.db_client.execute_raw_sql(sql, [], query_type, None)
            else:
                raise Exception(f"Unknown query type: {query_type}")
            
            # Debug: log the SQL being executed (for non-custom queries)
            if query_type not in ['custom_month_category', 'custom_month_budget', 'dynamic_sql']:
                print(f"DEBUG: Executing SQL for {query_type}:")
                print(f"SQL: {sql}")
            elif query_type == 'dynamic_sql':
                print(f"DEBUG: Generated SQL for question '{question}':")
                print(f"SQL: {sql}")
            print(f"DEBUG: Query result: {result}")
            print(f"DEBUG: Result type: {type(result)}, Length: {len(result) if result else 'None'}")
            
            # Format results nicely
            if query_type in ['week_total', 'month_total', 'today_total', 'yesterday_total', 'total_budget']:
                total = result[0].get('total', 0) if result else 0
                
                if query_type == 'total_budget':
                    return f"💰 Total budget for this month: ${total:.2f} MXN"
                
                period_map = {
                    'week_total': 'this week',
                    'month_total': 'this month', 
                    'today_total': 'today',
                    'yesterday_total': 'yesterday'
                }
                period = period_map.get(query_type, 'this period')
                return f"💰 Total spending {period}: ${total:.2f} MXN"
            
            elif query_type in ['month_by_category', 'custom_month_category', 'today_by_category', 'yesterday_by_category']:
                # Determine period label
                period_labels = {
                    'month_by_category': 'This Month',
                    'today_by_category': 'Today',
                    'yesterday_by_category': 'Yesterday'
                }
                
                if query_type == 'custom_month_category':
                    period_label = f"{month.title()} {year}" if month and year else "Period"
                    period_text = f"{month.title()} {year}".lower() if month and year else "that period"
                else:
                    period_label = period_labels.get(query_type, "Period")
                    period_text = period_label.lower()
                
                if not result:
                    return f"✨ No expenses found for {period_text}."
                
                response = f"📊 {period_label}'s Spending by Category:\n\n"
                total_all = sum(float(r.get('total', 0)) for r in result)
                response += f"💵 Grand Total: ${total_all:.2f} MXN\n\n"
                
                for i, r in enumerate(result, 1):  # Show ALL categories, not just top 5
                    name = r.get('category', 'Unknown')
                    amount = float(r.get('total', 0))
                    count = int(r.get('count', 0))
                    percentage = (amount / total_all * 100) if total_all > 0 else 0
                    response += f"{i}. {name}: ${amount:.2f} ({percentage:.1f}%) - {count}x\n"
                
                return response
            
            elif query_type in ['budget_vs_spending', 'custom_month_budget']:
                if not result:
                    return "📊 **Budget Analysis**\n\n✨ No budget data found. Set up budgets to track your spending progress!"
                
                # Calculate totals
                total_budget = sum(float(r.get('budget', 0)) for r in result)
                total_spent = sum(float(r.get('spent', 0)) for r in result)
                total_remaining = total_budget - total_spent
                overall_percent = (total_spent / total_budget * 100) if total_budget > 0 else 0
                
                # Conversational response as requested
                period_text = f"{month.title()} {year}" if query_type == 'custom_month_budget' and month and year else "this month"
                response = f"💰 **Here's how you're doing against your budget for {period_text}:**\n\n"
                response += f"You spent **${total_spent:.2f} MXN** in {period_text}, "
                
                if overall_percent > 100:
                    response += f"which is **{overall_percent:.1f}%** of your budget. 🚨\n"
                    response += f"⚠️ You're **${abs(total_remaining):.2f} MXN over budget!**\n\n"
                elif overall_percent > 80:
                    response += f"which is **{overall_percent:.1f}%** of your budget. ⚠️\n"
                    response += f"💡 You have **${total_remaining:.2f} MXN** left - watch your spending!\n\n"
                else:
                    response += f"which is **{overall_percent:.1f}%** of your budget. ✅\n"
                    response += f"🎉 You have **${total_remaining:.2f} MXN** remaining. You're on track!\n\n"
                
                response += f"📊 **Budget: ${total_budget:.2f} MXN** | **Spent: ${total_spent:.2f} MXN** | **Progress: {overall_percent:.1f}%**\n\n"
                
                # Category breakdown
                response += "📋 **By Category:**\n\n"
                for i, r in enumerate(result[:8], 1):  # Show top 8 categories
                    category = r.get('category_name', 'Unknown')
                    budget = float(r.get('budget', 0))
                    spent = float(r.get('spent', 0))
                    remaining = float(r.get('remaining', 0))
                    percent = float(r.get('percent_used', 0))
                    
                    status_emoji = "🚨" if percent > 100 else "⚠️" if percent > 80 else "✅"
                    
                    response += f"{status_emoji} **{category}**: ${spent:.2f} / ${budget:.2f} ({percent:.1f}%)\n"
                    if remaining > 0:
                        response += f"   💰 ${remaining:.2f} remaining\n"
                    elif remaining < 0:
                        response += f"   🚨 ${abs(remaining):.2f} over budget\n"
                    response += "\n"
                
                return response
            
            elif query_type == 'recent_expenses':
                if not result:
                    return "✨ No recent expenses found."
                
                response = "📝 Recent Expenses:\n\n"
                for i, r in enumerate(result, 1):
                    detail = r.get('expense_detail', 'Unknown')
                    amount = float(r.get('amount', 0))
                    category = r.get('category', 'Unknown')
                    date = r.get('expense_date', 'Unknown')
                    user_name = r.get('user_name', 'Unknown')
                    response += f"{i}. {detail} - ${amount:.2f}\n   🏷️ {category} • 📅 {date} • 👤 {user_name}\n\n"
                
                total_shown = sum(float(r.get('amount', 0)) for r in result)
                response += f"💰 Total shown: ${total_shown:.2f} MXN"
                return response
            
            elif query_type == 'dynamic_sql':
                # Format dynamic SQL results intelligently
                if not result:
                    return "✨ No results found for your query."
                
                response = f"📊 **Query Results for: \"{question}\"**\n\n"
                
                # Try to format results smartly based on content
                if len(result) == 1 and 'total' in str(result[0]).lower():
                    # Single total result
                    total_val = next(iter(result[0].values()))
                    response += f"💰 **Total: ${float(total_val):.2f} MXN**"
                else:
                    # Multiple results - create table format
                    for i, row in enumerate(result[:20], 1):  # Limit to 20 rows
                        row_text = ""
                        for key, value in row.items():
                            if isinstance(value, (int, float)) and 'amount' in key.lower():
                                row_text += f"${float(value):.2f} "
                            else:
                                row_text += f"{value} "
                        response += f"{i}. {row_text.strip()}\n"
                    
                    if len(result) > 20:
                        response += f"\n... and {len(result) - 20} more rows"
                
                return response
            
            else:
                return json.dumps(result)
                
        except Exception as e:
            return f"❌ Query error: {str(e)}"
    
    def _run(self, question: str, query_type: Optional[str] = None, custom_sql: Optional[str] = None, month: Optional[str] = None, year: Optional[int] = None) -> str:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(question, query_type, custom_sql, month, year))

class FinAIAgent:
    def __init__(self, db_client, classifier, parser):
        self.db_client = db_client
        self.classifier = classifier
        self.parser = parser
        
        # Initialize OpenAI LLM - Using GPT-4.1 for better decision making
        self.llm = ChatOpenAI(
            model="gpt-4.1",
            temperature=0
        )
        
        # Conversation memory storage: {chat_id: [(user_msg, assistant_msg), ...]}
        # Keep last 5 message pairs (10 messages total) for context
        self.conversation_history = {}
        self.max_history = 5
        
        # Create tools
        self.tools = [
            ParseExpenseTool(parser),
            ClassifyExpenseTool(db_client, classifier),
            CurrencyConvertTool(db_client),
            InsertExpenseTool(db_client),
            SqlQueryTool(db_client)
        ]
        
        # Create agent
        categories_list = "Rent, Transportation, Groceries, Oxxo, Medicines, Puppies, Telcom, Subscriptions, Restaurants, Clothing, Travel, Entertainment, Gadgets, Home appliances, Others, Finance, Gym, Canada"
        
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """You are FinAIssistant, an expert AI expense tracking assistant on Telegram with advanced natural language processing capabilities.

# YOUR IDENTITY & ROLE
- You're a friendly, conversational AI that helps families track expenses and analyze spending
- You understand natural language and can handle greetings, questions, and expense entries
- You have access to powerful tools for parsing, classification, database operations, and analytics
- You operate in MXN currency primarily, supporting multi-currency transactions

# YOUR AVAILABLE TOOLS & CAPABILITIES

## 🔧 TOOL 1: parse_expense
**Purpose**: Parse natural language text to extract expense information
**Use when**: User provides text that might contain expense data
**Input**: text (string)
**Output**: JSON with merchant, amount, currency, or null if not an expense
**Examples**: "Costco 120.54" → {{"merchant": "Costco", "amount": 120.54, "currency": "MXN"}}

## 🔧 TOOL 2: classify_expense  
**Purpose**: Automatically categorize expenses using AI classification
**Use when**: You have a merchant name that needs categorization
**Input**: merchant (string)
**Output**: JSON with categoryName, categoryId, confidence score
**Categories Available**: """ + categories_list + """

## 🔧 TOOL 3: insert_expense
**Purpose**: Save expense to database with proper user attribution
**Use when**: You have parsed and classified an expense successfully
**Input**: user_id, category_id, merchant, amount, currency
**Output**: Confirmation message or error
**Note**: Handles UUID conversion automatically for user_id and category_id

## 🔧 TOOL 4: convert_currency
**Purpose**: Convert between different currencies using live rates
**Use when**: User provides expenses in non-CAD currencies
**Input**: amount, from_currency, to_currency
**Supported**: MXN, CAD, USD, EUR, GBP
**Output**: JSON with converted amount and rate used

## 🔧 TOOL 5: sql_query (MOST IMPORTANT - READ CAREFULLY)
**Purpose**: Execute sophisticated expense analytics queries
**This tool has TWO modes**: Predefined Templates + Dynamic SQL Generation

### PREDEFINED QUERY TYPES (try these first):

**SPENDING TOTALS:**
- query_type='week_total' → Total spending last 7 days
- query_type='month_total' → Total spending current month  
- query_type='today_total' → Total spending today
- query_type='yesterday_total' → Total spending yesterday
- query_type='total_budget' → Total budget amount for current month

**CATEGORY BREAKDOWNS:**
- query_type='month_by_category' → Current month spending by category with percentages
- query_type='today_by_category' → Today's spending by category
- query_type='yesterday_by_category' → Yesterday's spending by category
- query_type='custom_month_category', month='july', year=2025 → Specific month breakdown

**BUDGET ANALYSIS:**
- query_type='budget_vs_spending' → Current month budget vs actual with progress %
- query_type='custom_month_budget', month='july', year=2025 → Historical budget analysis

**TRANSACTION HISTORY:**
- query_type='recent_expenses' → Last 10 detailed transactions with users and dates

**DYNAMIC SQL (use when no predefined template fits):**
- query_type='dynamic_sql', question='user question' → Auto-generates SQL for complex queries
- Use for: individual expense lists, detailed transactions, specific filtering, multi-condition queries
- Examples: "list each expense", "show individual transactions", "expenses over $X", "details for specific merchant"

# INTELLIGENT DECISION MAKING PROCESS

## STEP 1: MESSAGE CLASSIFICATION
**Greeting/Chat** → Respond naturally without tools
- "hi", "hello", "how are you", casual conversation
- Be warm, friendly, conversational like chatting with a human

**Expense Entry** → Use parse_expense → classify_expense → insert_expense
- "Costco 120.54", "Spent 45 on dinner", "Uber 25 dollars"
- Any text with merchant + amount pattern
- NOT questions about spending (those are analytics)

**Analytics/Questions** → Use sql_query with intelligent routing
- Questions about spending, budgets, categories, totals, breakdowns
- "show me", "how much", "what did I spend", "budget vs actual"

## STEP 2: INTELLIGENT ANALYTICS ROUTING
**NEW: The sql_query tool now has built-in multi-agent intelligence!**

**SIMPLE APPROACH**: Just call sql_query with question parameter only:
- sql_query(question="user's question here")

**The tool will automatically:**
1. **Consult SQL Library Agent** → "Can existing templates handle this question?"
2. **If YES** → Uses appropriate template (week_total, month_by_category, etc.)  
3. **If NO** → **Dynamic SQL Writer Agent** generates custom SQL
4. **Execute** → Returns properly formatted results

**Examples (all use same approach):**
   - "spending this week" → sql_query(question="spending this week")
   - "top 5 expenses this year" → sql_query(question="top 5 expenses this year") 
   - "list each expense under Subscriptions in july 2025" → sql_query(question="list each expense under Subscriptions in july 2025")
   - "budget vs spending" → sql_query(question="budget vs spending")

**CRITICAL**: 
- ✅ **DO**: Always use question parameter only → sql_query(question="user question")
- ❌ **DON'T**: Manually specify query_type unless you're 100% certain
- 🤖 **TRUST**: Let the intelligent agents decide the best approach

## STEP 3: RESPONSE FORMATTING
- **Expense entries**: Confirm with amount, category, merchant
- **Analytics**: Use emojis, formatting, conversational tone
- **Errors**: Provide helpful guidance, never just say "error"
- **Greetings**: Be human-like, warm, mention capabilities briefly

# CRITICAL RULES & SAFEGUARDS

❌ **NEVER confuse questions with expenses**:
- "july 2025" in text = ANALYTICS QUESTION, not $2025 expense
- "give me spends by category" = ANALYTICS, not expense entry
- Years (2024, 2025) = temporal references, not amounts

✅ **Always validate before inserting expenses**:
- Parse first, classify second, insert third
- Check confidence scores, ask for confirmation if needed
- Handle currency conversion properly

⚡ **SQL Query Intelligence**:
- Try predefined templates first (faster, more reliable)
- Use dynamic_sql only for complex questions not covered by templates
- The sql_query tool description contains full details of available options

🎯 **User Context**:
- **CRITICAL**: Each message starts with [SYSTEM: user_id=XXXXX]. Extract this user_id value and use it when calling insert_expense tool.
- Family expense tracking (queries show all family members' expenses)
- Default currency: MXN
- Timezone: America/Vancouver

# PERSONALITY & TONE
- Conversational and friendly like talking to a smart friend
- Use appropriate emojis but don't overdo it  
- Be concise for Telegram but helpful and clear
- When unsure, ask clarifying questions
- Celebrate successes ("Great! Expense saved!") 
- Be empathetic about budget concerns

Remember: You're not just parsing commands - you're having natural conversations about money management with families. Be helpful, intelligent, and personable."""
            ),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad")
        ])
        
        # Create agent using langgraph prebuilt (langchain 1.0+ API)
        # Extract system message from prompt template
        from langchain_core.messages import SystemMessage
        system_message_content = prompt.messages[0].prompt.template.format(userId="{userId}")
        self.agent_executor = create_react_agent(
            self.llm,
            self.tools,
            prompt=SystemMessage(content=system_message_content)
        )
    
    async def process_message(self, message: str, user_id: Optional[int] = None, chat_id: Optional[int] = None) -> str:
        """Process a user message and return response with conversation memory"""
        try:
            from langchain_core.messages import HumanMessage, AIMessage
            
            # Get conversation history for this chat
            chat_key = chat_id or user_id  # Use chat_id if available, fallback to user_id
            if chat_key not in self.conversation_history:
                self.conversation_history[chat_key] = []
            
            history = self.conversation_history[chat_key]
            
            # Build chat_history for the agent (list of alternating Human/AI messages)
            chat_history_messages = []
            for user_msg, assistant_msg in history:
                chat_history_messages.append(HumanMessage(content=user_msg))
                chat_history_messages.append(AIMessage(content=assistant_msg))
            
            # Process current message
            # Inject user_id into the message so the agent knows it when calling tools
            formatted_message = f"[SYSTEM: user_id={user_id}]\n{message}"
            
            # langgraph agents use 'messages' key instead of 'input'
            # Include chat history IN the messages array (history first, then current message)
            all_messages = chat_history_messages + [HumanMessage(content=formatted_message)]
            
            result = await self.agent_executor.ainvoke({
                "messages": all_messages
            })
            
            # Extract the last message from the agent
            response = None
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_message = messages[-1]
                    if hasattr(last_message, 'content'):
                        response = last_message.content
                    elif isinstance(last_message, dict):
                        response = last_message.get("content", "I couldn't process that request.")
            
            if not response:
                response = "I couldn't process that request."
            
            # Update conversation history (keep last N pairs)
            # Store the original message (without SYSTEM prefix) for cleaner history
            history.append((message, response))
            if len(history) > self.max_history:
                history.pop(0)  # Remove oldest message pair
            
            return response
            
        except Exception as e:
            import logging
            logging.error(f"Agent error: {e}", exc_info=True)
            return f"I encountered an error: {str(e)}"
    
    async def get_monthly_budget_summary(self, user_id: int) -> str:
        """Get monthly budget summary using predefined SQL templates"""
        try:
            # Get current month budget summary
            sql = """
            WITH budget AS (
              SELECT b.category_id, b.amount, b.currency
              FROM budgets b
              WHERE b.month = EXTRACT(month FROM NOW() AT TIME ZONE 'America/Vancouver')
                AND b.year = EXTRACT(year FROM NOW() AT TIME ZONE 'America/Vancouver')
            ),
            spent AS (
              SELECT e.category_id, SUM(e.amount) as spent
              FROM expenses e
              WHERE e.user_id = %s
                AND DATE_TRUNC('month', e.expense_date) = DATE_TRUNC('month', NOW() AT TIME ZONE 'America/Vancouver')
              GROUP BY e.category_id
            ),
            today_expenses AS (
              SELECT SUM(e.amount) as today_total, COUNT(*) as today_count
              FROM expenses e
              WHERE e.user_id = %s
                AND e.expense_date = (NOW() AT TIME ZONE 'America/Vancouver')::date
            )
            SELECT 
                c.name,
                COALESCE(s.spent, 0) as spent,
                COALESCE(b.amount, 0) as budget,
                GREATEST(COALESCE(b.amount,0) - COALESCE(s.spent,0), 0) as remaining,
                CASE WHEN b.amount > 0 THEN ROUND((COALESCE(s.spent,0) / b.amount * 100), 1) ELSE 0 END as used_percent,
                te.today_total,
                te.today_count
            FROM categories c
            LEFT JOIN budget b ON b.category_id = c.id
            LEFT JOIN spent s ON s.category_id = c.id
            CROSS JOIN today_expenses te
            WHERE b.amount IS NOT NULL
            ORDER BY c.name
            """
            
            # For now, return a simple summary since we need to implement the SQL execution
            # This would normally call self.db_client.execute_sql(sql, [user_id, user_id])
            
            return """Monthly Budget Summary (Stub):
            
• Spent: $740.27 CAD
• Budget: $5,040.00 CAD  
• Remaining: $4,299.73 CAD
• Used: 14.7%

Today: No expenses yet

(Full implementation pending SQL execution setup)"""
            
        except Exception as e:
            return f"Error generating budget summary: {str(e)}"