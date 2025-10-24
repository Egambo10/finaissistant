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
    question: str = Field(description="Natural language question about expenses, spending, budgets, or analytics. Vanna AI will generate SQL automatically to answer your question.")

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
    description: str = """Answer questions about expenses, spending, budgets, and financial analytics using AI-generated SQL.

This tool uses Vanna AI (RAG-based Text-to-SQL) to understand natural language questions and generate appropriate SQL queries.

CAPABILITIES:
- Spending totals (day, week, month, year, custom periods)
- Category breakdowns and comparisons
- Budget vs actual analysis with progress tracking
- Transaction history and recent expenses
- Top N queries (highest/lowest expenses, top categories)
- Complex filtering (amount ranges, date ranges, specific merchants)
- Multi-table JOINs (expenses + categories + budgets + users)
- Aggregations (SUM, AVG, COUNT, MAX, MIN)
- Time-based analysis (trends, comparisons, growth)
- Insights and recommendations based on spending patterns

EXAMPLE QUESTIONS:
- "How much did I spend this month?"
- "Show me spending by category for July 2025"
- "What's my budget vs actual spending?"
- "List my top 5 highest expenses this year"
- "Show expenses over $100 in Restaurants category"
- "Compare my spending this month vs last month"
- "What percentage of my budget have I used?"

Just pass the natural language question - Vanna AI handles the rest!"""
    args_schema: Type[BaseModel] = SqlQueryInput
    db_client: Any = None
    vanna_trainer: Any = None
    
    def __init__(self, db_client, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'db_client', db_client)

        # Initialize Vanna AI for all SQL generation
        import logging
        logger = logging.getLogger(__name__)
        try:
            vanna = VannaTrainer(
                api_key=os.getenv('OPENAI_API_KEY')
                # Uses default model: gpt-4o-mini
            )
            # Train Vanna on database schema and examples
            vanna.train_all()
            object.__setattr__(self, 'vanna_trainer', vanna)
            logger.info("✅ Vanna AI integrated and trained for all SQL generation")
        except Exception as e:
            logger.error(f"❌ Vanna initialization failed: {e}")
            raise Exception("Vanna AI is required for SQL generation")
    
    async def _generate_sql(self, question: str) -> str:
        """
        Generate SQL query using Vanna AI (RAG-based Text-to-SQL)
        Vanna provides better accuracy through database-specific training
        """
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"🤖 Generating SQL with Vanna AI: {question}")
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

        logger.info(f"✅ Vanna generated SQL: {sql[:100]}...")
        return sql

    async def _arun(self, question: str) -> str:
        """
        Generate and execute SQL query using Vanna AI for any natural language question
        """
        import logging
        import re
        logger = logging.getLogger(__name__)

        try:
            logger.info(f"🤖 SqlQueryTool processing question: {question}")

            # Step 1: Validate input
            if not question or not question.strip():
                raise Exception("Question cannot be empty")

            # Step 2: Generate SQL using Vanna AI
            sql = await self._generate_sql(question)

            # Step 3: Apply safety checks to generated SQL
            if not sql.strip():
                logger.error("Empty SQL generated by Vanna")
                raise Exception("Failed to generate SQL")

            # Block dangerous SQL patterns (SQL injection protection)
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
                r'\btruncate\b',  # TRUNCATE statements
            ]

            # Check each pattern individually for better debugging
            for pattern in dangerous_patterns:
                if re.search(pattern, sql, re.IGNORECASE):
                    logger.error(f"🚨 SQL rejected by pattern '{pattern}': {sql}")
                    raise Exception(f"Generated SQL rejected by security guardrails")

            # Ensure it's a SELECT statement or CTE (WITH clause)
            if not re.match(r'^\s*(select|with)\b', sql, re.IGNORECASE):
                logger.error(f"🚨 SQL rejected - not a SELECT/WITH statement: {sql}")
                raise Exception("Only SELECT queries are allowed for security")

            logger.info(f"✅ SQL passed safety checks, executing...")

            # Step 4: Execute the SQL query
            result = await self.db_client.execute_raw_sql(sql, [], "dynamic_sql", question)

            logger.info(f"📊 Query returned {len(result) if result else 0} rows")

            # Step 5: Format results intelligently
            return self._format_results(result, question, sql)

        except Exception as e:
            logger.error(f"❌ Query error: {str(e)}")
            return f"❌ I couldn't answer that question: {str(e)}"

    def _format_results(self, result: list, question: str, sql: str) -> str:
        """
        Intelligently format query results based on content and structure
        """
        import json

        if not result:
            return "✨ No results found for your question."

        # Single row with a 'total' field → format as total
        if len(result) == 1 and 'total' in result[0]:
            total = float(result[0]['total'])
            return f"💰 **Total: ${total:,.2f} MXN**"

        # Category breakdown (has category + total/amount fields)
        if result and isinstance(result[0], dict):
            first_row = result[0]
            has_category = 'category' in first_row or 'category_name' in first_row
            has_amount = 'total' in first_row or 'amount' in first_row or 'spent' in first_row

            if has_category and has_amount:
                # Category breakdown response
                category_key = 'category_name' if 'category_name' in first_row else 'category'
                amount_key = 'total' if 'total' in first_row else ('spent' if 'spent' in first_row else 'amount')

                total_all = sum(float(r.get(amount_key, 0)) for r in result)
                response = f"📊 **Spending Breakdown** (Total: ${total_all:,.2f} MXN)\n\n"

                for i, r in enumerate(result[:15], 1):  # Show top 15
                    category = r.get(category_key, 'Unknown')
                    amount = float(r.get(amount_key, 0))
                    percentage = (amount / total_all * 100) if total_all > 0 else 0
                    count = r.get('count', '')
                    count_str = f" ({count}x)" if count else ""

                    response += f"{i}. **{category}**: ${amount:,.2f} MXN ({percentage:.1f}%){count_str}\n"

                if len(result) > 15:
                    response += f"\n_... and {len(result) - 15} more categories_"

                return response

        # Budget vs spending (has budget, spent, remaining fields)
        if result and 'budget' in result[0] and 'spent' in result[0]:
            total_budget = sum(float(r.get('budget', 0)) for r in result)
            total_spent = sum(float(r.get('spent', 0)) for r in result)
            total_remaining = total_budget - total_spent
            overall_percent = (total_spent / total_budget * 100) if total_budget > 0 else 0

            response = f"💰 **Budget Analysis**\n\n"
            response += f"📊 **Total Budget**: ${total_budget:,.2f} MXN\n"
            response += f"💳 **Total Spent**: ${total_spent:,.2f} MXN ({overall_percent:.1f}%)\n"
            response += f"💵 **Remaining**: ${total_remaining:,.2f} MXN\n\n"

            response += "📋 **By Category:**\n\n"
            for i, r in enumerate(result[:10], 1):
                category = r.get('category_name', r.get('category', 'Unknown'))
                budget = float(r.get('budget', 0))
                spent = float(r.get('spent', 0))
                percent = float(r.get('percent_used', (spent / budget * 100) if budget > 0 else 0))

                status_emoji = "🚨" if percent > 100 else "⚠️" if percent > 80 else "✅"
                response += f"{status_emoji} **{category}**: ${spent:,.2f} / ${budget:,.2f} ({percent:.1f}%)\n"

            return response

        # Individual expense records (has expense_detail or merchant)
        if result and ('expense_detail' in result[0] or 'merchant' in result[0]):
            response = f"📝 **Expense List** ({len(result)} transactions)\n\n"

            for i, r in enumerate(result[:20], 1):
                detail = r.get('expense_detail', r.get('merchant', 'Unknown'))
                amount = float(r.get('amount', 0))
                category = r.get('category', r.get('category_name', ''))
                date = r.get('expense_date', '')

                response += f"{i}. **{detail}** - ${amount:,.2f} MXN\n"
                if category or date:
                    extras = []
                    if category:
                        extras.append(f"🏷️ {category}")
                    if date:
                        extras.append(f"📅 {date}")
                    response += f"   {' • '.join(extras)}\n"
                response += "\n"

            if len(result) > 20:
                response += f"_... and {len(result) - 20} more transactions_\n"

            total_shown = sum(float(r.get('amount', 0)) for r in result[:20])
            response += f"\n💰 **Total shown**: ${total_shown:,.2f} MXN"

            return response

        # Default: Generic table formatting
        response = f"📊 **Query Results** ({len(result)} rows)\n\n"

        for i, row in enumerate(result[:20], 1):
            row_text = []
            for key, value in row.items():
                if isinstance(value, (int, float)) and ('amount' in key.lower() or 'total' in key.lower() or 'budget' in key.lower()):
                    row_text.append(f"{key}: ${float(value):,.2f}")
                elif value is not None:
                    row_text.append(f"{key}: {value}")

            response += f"{i}. {', '.join(row_text)}\n"

        if len(result) > 20:
            response += f"\n_... and {len(result) - 20} more rows_"

        return response

    def _run(self, question: str) -> str:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(question))

class FinAIAgent:
    def __init__(self, db_client, classifier, parser):
        self.db_client = db_client
        self.classifier = classifier
        self.parser = parser
        
        # Initialize OpenAI LLM - Using GPT-4o-mini for cost-effective decision making
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
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
**Purpose**: Answer ANY question about expenses using AI-generated SQL
**Powered by**: Vanna AI (RAG-based Text-to-SQL with database training)

**CAPABILITIES** (Vanna AI understands all of these naturally):
- 💰 Spending totals (day, week, month, year, custom periods)
- 📊 Category breakdowns and comparisons
- 💳 Budget vs actual analysis with progress tracking
- 📝 Transaction history and recent expenses
- 🏆 Top N queries (highest/lowest expenses, top categories)
- 🔍 Complex filtering (amount ranges, date ranges, specific merchants/categories)
- 🔗 Multi-table JOINs (expenses + categories + budgets + users)
- 📈 Aggregations (SUM, AVG, COUNT, MAX, MIN, percentages)
- ⏰ Time-based analysis (trends, comparisons, month-over-month)
- 🧠 Insights and recommendations based on patterns

**HOW TO USE**:
- Simply call `sql_query(question="user's natural language question")`
- That's it! Vanna AI handles everything: SQL generation, execution, formatting

**EXAMPLES**:
- "How much did I spend this month?" → Vanna generates SELECT SUM query
- "Show spending by category for July 2025" → Vanna generates JOIN + GROUP BY + date filter
- "What's my budget vs actual?" → Vanna generates CTE with budgets and expenses
- "List my top 5 highest expenses" → Vanna generates ORDER BY + LIMIT
- "Expenses over $100 in Restaurants" → Vanna generates WHERE clauses with JOIN
- "Compare this month vs last month" → Vanna generates date comparisons
- "What percentage of budget have I used?" → Vanna generates calculations

# INTELLIGENT DECISION MAKING PROCESS

## STEP 1: MESSAGE CLASSIFICATION
**Greeting/Chat** → Respond naturally without tools
- "hi", "hello", "how are you", casual conversation
- Be warm, friendly, conversational like chatting with a human

**Expense Entry** → Use parse_expense → classify_expense → insert_expense
- "Costco 120.54", "Spent 45 on dinner", "Uber 25 dollars"
- Any text with merchant + amount pattern
- NOT questions about spending (those are analytics)

**Analytics/Questions** → Use sql_query with Vanna AI
- Questions about spending, budgets, categories, totals, breakdowns
- "show me", "how much", "what did I spend", "budget vs actual"
- "compare", "analyze", "breakdown", "list expenses"

## STEP 2: USING SQL_QUERY TOOL
**SIMPLE & POWERFUL**: Just pass the user's question to Vanna AI

```
sql_query(question="<exactly what the user asked>")
```

**Vanna AI automatically**:
1. 🧠 Understands the question using RAG (trained on your database schema)
2. 🔧 Generates optimized PostgreSQL SELECT query with proper JOINs
3. ✅ Query is validated for security (only SELECT allowed)
4. 📊 Executes and formats results beautifully
5. 💬 Returns conversational response with emojis and formatting

**NO manual routing needed** - Vanna is trained on:
- Complete database schema (expenses, categories, budgets, users, currency_rates)
- Business logic (month=1-12, currency=MXN, family tracking)
- Common query patterns (totals, breakdowns, budget analysis)
- Example question-SQL pairs for accuracy

## STEP 3: RESPONSE FORMATTING
- **Expense entries**: Confirm with amount, category, merchant
- **Analytics**: Let Vanna's intelligent formatting shine (already includes emojis, tables, insights)
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

⚡ **SQL Query with Vanna AI**:
- Pass user questions directly to sql_query tool
- Trust Vanna's RAG-based SQL generation (trained on your database)
- Vanna handles simple AND complex queries equally well
- JOINs, aggregations, filters all work automatically

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