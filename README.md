# FinAIssistant v2 - Production AI Expense Tracker

FinAIssistant v2 is a production-ready AI-powered expense tracking Telegram bot built with LangChain and OpenAI. The bot uses intelligent multi-agent communication to provide natural conversation, automatic expense categorization, and comprehensive financial analytics.

## 🏗 Architecture

- **Bot Framework**: Python + python-telegram-bot
- **AI Framework**: LangChain + OpenAI GPT-4.1 with function calling
- **Database**: Supabase PostgreSQL with UUID schema
- **Multi-Agent System**: SQL Library Consultant + Dynamic SQL Writer
- **Tools**: ParseExpense, ClassifyExpense, InsertExpense, SqlQuery, CurrencyConvert

## ✅ Key Features

- **Natural Language Processing**: "compass 107.3" → Automatically saved as $107.30 Transportation
- **Intelligent Query Routing**: Multi-agent system chooses between predefined SQL templates and dynamic SQL generation
- **Family Expense Tracking**: Track and analyze expenses across all family members
- **Multi-Currency Support**: MXN (default), CAD, USD, EUR, GBP with automatic conversion
- **Dynamic SQL Generation**: Ask ANY question about your expenses - the AI generates safe SQL automatically
- **Static Budget Analysis**: Compare spending against fixed budgets with percentage tracking
- **Conversational AI**: Natural greetings and human-like responses

## 🚀 Quick Start

### Local Development

#### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 2. Configure Environment
Set up your `api.env` file with these required variables:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
OPENAI_API_KEY=your_openai_api_key_here
CURRENCY_API_KEY=your_currency_api_key
```

#### 3. Start the Bot
```bash
python3 hybrid_bot.py
```

The bot will start in polling mode and show initialization messages:
```
🚀 FinAIssistant LangChain Agent initialized!
🔧 LangChain tools: ParseExpense, ClassifyExpense, InsertExpense, SqlQuery
🧠 AI-powered decision making between expense parsing and question answering
✅ All components ready
📱 Ready to chat on Telegram!
```

## 🚀 Production Deployment

### Deploy to Railway (Recommended)

For 24/7 cloud hosting with automatic restarts and monitoring:

👉 **See [DEPLOYMENT.md](./DEPLOYMENT.md) for complete Railway deployment guide**

**Why Railway?**
- ✅ Supports long-running bots (polling)
- ✅ Persistent filesystem (ChromaDB/Vanna AI works)
- ✅ Conversation memory persists
- ✅ $5/month with free trial credit
- ✅ Auto-deploys from GitHub
- ✅ Built-in monitoring and logs

**Quick Deploy:**
1. Push code to GitHub
2. Connect repository to Railway
3. Add environment variables
4. Deploy! 🎉

## 🛠 Managing the Bot Process (Local)

### Starting the Bot
```bash
# Start in foreground (shows logs)
python3 hybrid_bot.py

# Start in background
nohup python3 hybrid_bot.py > bot.log 2>&1 &
```

### Stopping the Bot
```bash
# If running in foreground, press Ctrl+C

# If running in background, find and kill the process
ps aux | grep hybrid_bot.py
kill <process_id>

# Or use pkill
pkill -f hybrid_bot.py
```

### Monitoring the Bot
```bash
# View live logs
tail -f bot.log

# Check if bot is running
ps aux | grep hybrid_bot.py

# View recent logs
tail -50 bot.log
```

### Restarting the Bot
```bash
# Kill existing process and restart
pkill -f hybrid_bot.py && python3 hybrid_bot.py
```

## 📋 Core Files

- **`hybrid_bot.py`** - Main Telegram bot with LangChain integration
- **`agent.py`** - LangChain agent with multi-agent SQL routing system
- **`database.py`** - Supabase client with comprehensive SQL execution and dynamic parsing
- **`classifier.py`** - Expense category classification with confidence scoring
- **`parser.py`** - Natural language expense parsing with question detection
- **`currency.py`** - Multi-currency support and conversion
- **`vanna_trainer.py`** - Vanna AI SQL generator with RAG
- **`api.env`** - Environment configuration (API keys, database URLs)
- **`requirements.txt`** - Python dependencies
- **`Procfile`** - Railway deployment configuration
- **`DEPLOYMENT.md`** - Railway deployment guide
- **`prd.md`** - Complete technical specifications

## 💬 Usage Examples

### Expense Entry
```
User: "oxxo 28"
Bot: "💰 Saved expense: $28.00 MXN at Oxxo → Convenience Stores"

User: "costco 120.54"  
Bot: "💰 Saved expense: $120.54 MXN at Costco → Groceries"
```

### Analytics (Dynamic SQL Generation with Vanna AI)
```
User: "What's my total budget for this month?"
Bot: "💰 Your total budget for October 2025 is $37,768.80 MXN"

User: "top 5 expenses this month"
Bot: "🏆 Top 5 expenses for October 2025:
1. Rent - $12,000.00 MXN
2. Groceries at Costco - $3,450.00 MXN
3. Transportation - $2,107.30 MXN
..."

User: "show me expenses under Subscriptions"
Bot: "📊 Subscriptions expenses:
- Netflix: $299.00 MXN
- Spotify: $199.00 MXN
- Total: $498.00 MXN"
```

### Natural Conversation with Memory
```
User: "What's my budget?"
Bot: "💰 Your total budget for October 2025 is $37,768.80 MXN"

User: "How much have I spent?"  # Bot remembers previous context!
Bot: "📊 You've spent $15,234.50 MXN so far this month"

User: "how was budget vs real last month by category"
Bot: "📊 Budget vs Actual for September 2025:
🏠 Housing: $12,400.00 / $12,000.00 (103%)
🛒 Groceries: $2,850.00 / $3,000.00 (95%)
..."
```

## 🔧 Advanced Features

### 🧠 Conversation Memory
- Remembers last **5 message pairs** (10 messages) per chat
- Enables follow-up questions without repeating context
- Separate memory for each chat/user

### 🤖 Multi-Agent Intelligence with Vanna AI
The bot uses a sophisticated multi-agent system:

1. **Main Agent** (GPT-4.1): Decides between expense entry and query handling
2. **Vanna AI SQL Generator**: RAG-powered SQL generation using ChromaDB vector database
3. **SQL Library Consultant**: Checks if predefined templates can answer the question
4. **Dynamic SQL Writer**: Fallback for complex queries when Vanna doesn't have context

### Intelligent SQL Routing
- **Predefined Templates**: Fast execution for common queries (spending totals, category breakdowns)
- **Dynamic SQL Generation**: AI creates safe SQL for any question about your data
- **Full Month Date Ranges**: "this month" queries search the entire month, not just to today
- **Safety Guardrails**: Only SELECT queries allowed, with SQL injection prevention

### Family Expense Tracking
- All queries show expenses from ALL family members
- User attribution in transaction details
- Shared budget tracking and analysis

## 📊 Database Schema

```sql
-- Core Tables
users(id UUID, telegram_id, name, created_at)
categories(id UUID, name, description, created_at)  
expenses(id UUID, user_id UUID, category_id UUID, expense_detail, amount, currency, original_amount, original_currency, expense_date, paid_by, timestamp, notes)
budgets(id UUID, category_id UUID, amount, currency, month, year)  -- Fixed monthly budgets
currency_rates(base_currency, target_currency, rate, updated_at)

-- Relations
expenses.user_id → users.id
expenses.category_id → categories.id
budgets.category_id → categories.id

-- Key Features
- amount is always stored in MXN (default currency)
- original_amount/original_currency preserve the input currency
- month is INTEGER 1-12, year is INTEGER (e.g., 2025)
```

## 🔍 Troubleshooting

### Bot Not Responding
1. Check if process is running: `ps aux | grep hybrid_bot.py`
2. Check logs: `tail -50 bot.log`
3. Restart bot: `pkill -f hybrid_bot.py && python3 hybrid_bot.py`

### Database Connection Issues
1. Verify `api.env` has correct Supabase credentials
2. Check Supabase project status
3. Test connection: `python3 -c "from database import SupabaseClient; SupabaseClient()"`

### Expense Not Saving
1. Check if bot recognized expense vs question
2. Verify category classification in logs
3. Check database permissions and UUID conversion

### Query Not Working
1. Bot will try predefined templates first
2. Falls back to dynamic SQL generation
3. Check logs for SQL generation details
4. Complex queries may need refinement

## 📝 Development

### Project Structure
```
FinAIssistant_v2/
├── hybrid_bot.py          # Main bot entry point
├── agent.py              # LangChain agent with tools
├── database.py           # Supabase database client
├── classifier.py         # Category classification
├── parser.py            # Expense parsing
├── currency.py          # Currency conversion
├── api.env             # Environment configuration
├── requirements.txt    # Python dependencies
├── README.md          # This file
├── prd.md            # Technical specifications
└── .gitignore       # Git ignore patterns
```

### Key Components

**Agent Tools:**
- `ParseExpenseTool`: Extract merchant, amount, currency from natural language
- `ClassifyExpenseTool`: Auto-categorize with confidence scoring
- `InsertExpenseTool`: Save to database with automatic MXN conversion
- `SqlQueryTool`: Execute queries with Vanna AI + multi-agent routing
- `CurrencyConvertTool`: Multi-currency conversion using live exchange rates

**Multi-Agent System:**
- **Main Agent** (GPT-4.1): Orchestrates conversation and tool selection
- **Vanna AI**: RAG-powered SQL generation using trained vector database
- **SQL Library Consultant**: Analyzes questions and selects appropriate templates
- **Dynamic SQL Writer**: Fallback SQL generator for complex queries

**Additional Components:**
- **ChromaDB Vector Store**: Local vector database for Vanna AI training examples
- **Conversation Memory**: In-memory storage for last 5 message pairs per chat

### Testing Queries
The bot can handle various query types:
- Time periods: "today", "this week", "this month", "last month", "July 2025"
- Categories: "expenses under Groceries", "Subscription spending"
- Comparisons: "budget vs actual", "compare May and June"
- Top lists: "top 5 expenses", "highest spending categories"
- Aggregations: "total spent", "average monthly", "count of transactions"

## 📄 License

Private project - All rights reserved.

---

**Status**: ✅ Production Ready  
**Last Updated**: October 2025  
**Version**: 2.1 - Vanna AI + Conversation Memory  
**Deployment**: Railway-ready with persistent storage# Railway deployment ready
