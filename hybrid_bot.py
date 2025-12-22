#!/usr/bin/env python3
"""
FinAIssistant - Hybrid Bot with Quick Analysis Buttons + Dynamic SQL
Fast premade queries + flexible AI-generated SQL for complex questions
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from database import SupabaseClient
from classifier import ExpenseClassifier
from parser import ExpenseParser
from currency import CurrencyConverter
from agent import FinAIAgent
from reminders import DailyReminder
from datetime import datetime, time, timedelta
import pytz

# Load environment variables
env_path = Path(__file__).parent / "api.env"
if env_path.exists():
    load_dotenv(env_path, override=True)
else:
    load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global components
db_client = None
classifier = None
parser = None
converter = None
hybrid_agent = None
pending_expenses = {}

async def save_pending_expense(chat_id, category_id, update):
    """Helper to save a pending expense and notify user"""
    if chat_id not in pending_expenses:
        return False
        
    pending = pending_expenses[chat_id]
    
    try:
        # Get user data
        user_data = await db_client.get_user_by_telegram_id(int(pending['user_id']))
        
        # Save expense
        await db_client.insert_expense(
            user_id=user_data['id'],
            category_id=category_id,
            merchant=pending['merchant'],
            amount=pending['amount'],
            currency=pending['currency']
        )
        
        # Get category name for display
        categories = await db_client.get_categories()
        category_name = next((cat['name'] for cat in categories if cat['id'] == category_id), 'Unknown')
        
        formatted_amount = converter.format_amount(pending['amount'], pending['currency'])
        
        del pending_expenses[chat_id]
        
        # Construct success message
        msg = (
            f"✅ **Expense saved!**\n\n"
            f"💳 {pending['merchant']} — {formatted_amount}\n"
            f"🏷 Category: **{category_name}**\n"
            f"🤖 *Confirmed by you*"
        )
        
        # If called from callback query (button click)
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, parse_mode='Markdown')
        else:
            # If called from text message
            await update.message.reply_text(msg, parse_mode='Markdown')
            
        return True
    except Exception as e:
        logger.error(f"Error saving expense: {e}")
        error_msg = "❌ Failed to save expense. Please try again."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return False

async def initialize_components():
    """Initialize all components including hybrid AI agent"""
    global db_client, classifier, parser, converter, hybrid_agent
    
    required_vars = ['TELEGRAM_BOT_TOKEN', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'OPENAI_API_KEY']
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    # Initialize core components
    db_client = SupabaseClient()
    classifier = ExpenseClassifier(db_client)
    parser = ExpenseParser()
    converter = CurrencyConverter(db_client)
    
    # Initialize LangChain AI agent with tools
    hybrid_agent = FinAIAgent(db_client, classifier, parser)
    
    logger.info("🚀 FinAIssistant LangChain Agent initialized!")
    logger.info("🔧 LangChain tools: ParseExpense, ClassifyExpense, InsertExpense, SqlQuery")
    logger.info("🧠 AI-powered decision making between expense parsing and question answering")
    logger.info("✅ All components ready")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced start command with quick analysis"""
    user = update.effective_user
    name = user.first_name or "there"
    
    await db_client.upsert_user(user.id, user.username or str(user.id), 
                               f"{user.first_name or ''} {user.last_name or ''}".strip())
    
    # Main menu keyboard
    keyboard = [
        ['💰 Add Expense', '📊 Quick Analysis'], 
        ['🧠 Ask Question', '💡 Insights']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    welcome_msg = f"""🤖 **Hi {name}! FinAIssistant Hybrid is ready!**

🚀 **NEW: Quick Analysis Buttons!**
⚡ Instant answers for common questions
🧠 Smart SQL for complex analysis

💰 **Log expenses naturally:**
• "I spent 25 dollars on Uber today"
• "Costco 120.54"
• "$45 for dinner at Italian restaurant"

📊 **Quick Analysis (NEW!):**
• Tap "📊 Quick Analysis" for instant insights
• Month totals, category breakdowns, recent expenses
• Top categories, today's spending, and more!

🧠 **Ask complex questions:**
• "Compare my weekend vs weekday spending"
• "Show expenses above $100 this month"
• "What percentage is food vs entertainment?"
• "Rank my categories by spending growth"

**Just chat naturally - I understand everything! 💬**"""
    
    await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode='Markdown')

async def quick_analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process quick analysis request using LangChain agent"""
    user_id = update.effective_user.id
    
    # Use LangChain agent to handle the request
    response = await hybrid_agent.process_message("Show me quick analysis options", user_id)
    
    await update.message.reply_text(
        "📊 **Quick Analysis**\n\n"
        "🤖 Ask me any question about your expenses:\n"
        "• 'Show my spending this month'\n"
        "• 'What did I spend on restaurants?'\n"
        "• 'Break down my expenses by category'\n"
        "• 'Show my recent expenses'\n\n"
        "💬 Just type your question naturally!",
        parse_mode='Markdown'
    )

async def insights_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate AI insights about spending"""
    user_id = update.effective_user.id
    
    await update.message.reply_text("🧠 Analyzing your spending patterns with AI...")
    
    try:
        insights = await hybrid_agent.get_expense_insights(str(user_id))
        await update.message.reply_text(insights, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error generating insights: {e}")
        await update.message.reply_text("❌ Couldn't generate insights right now. Try again later!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced help with hybrid capabilities"""
    help_text = """🤖 **FinAIssistant Hybrid Help**

🚀 **NEW: Quick Analysis System!**

📊 **Quick Analysis Buttons:**
• 💰 Month/Week totals
• 📊 Category breakdowns  
• 📝 Recent expenses
• 🏆 Top categories
• 🌅 Today's expenses
• ⚡ Instant results, no waiting!

💰 **Log expenses naturally:**
• "I bought coffee for $5.50"
• "Spent 120 on groceries at Costco"
• "Uber ride cost me 25 dollars yesterday"

🧠 **Ask complex questions:**
• "Compare my weekend vs weekday spending"
• "Show me expenses above $100 this month" 
• "What percentage is food vs entertainment?"
• "Rank categories by spending growth"
• "Find my highest single expenses"

📊 **Smart commands:**
• `/quick` - Quick analysis menu
• `/insights` - AI analysis of your spending
• `/help` - This help message

💡 **Pro tip:** Use quick analysis for speed, ask custom questions for detailed insights!

🔒 **Security:** All SQL queries are read-only and safe.

Ready to track expenses intelligently? 🚀"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """LangChain AI-powered message handler - routes ALL messages through agent first"""
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Handle button text with quick shortcuts
    if text == '💰 Add Expense':
        await update.message.reply_text(
            '💬 **Just tell me about your expense naturally!**\n\n'
            '🗣 Examples:\n'
            '• "I spent 25 dollars on Uber"\n'
            '• "Bought groceries for $120 at Costco"\n'
            '• "Coffee this morning cost 6.50"\n'
            '• "$45 dinner at the Italian place"'
        )
        return
    elif text == '📊 Quick Analysis':
        # Route through LangChain agent
        text = "Show me my spending analysis"
    elif text == '🧠 Ask Question':
        await update.message.reply_text(
            '🤖 **Ask me anything about your spending!**\n\n'
            '💡 Examples:\n'
            '• "How much did I spend this week?"\n'
            '• "Show my expenses by category"\n'
            '• "What did I spend on restaurants?"\n'
            '• "Show my recent expenses"\n\n'
            '💬 Just type your question naturally!'
        )
        return
    elif text == '💡 Insights':
        return await insights_command(update, context)
    
    # Check for pending expense confirmation (handle text replies like "groceries")
    if chat_id in pending_expenses:
        # Check for cancellation keywords
        normalized_text = classifier.normalize_text(text)
        if normalized_text in ['cancel', 'cancelar', 'no', 'stop']:
            del pending_expenses[chat_id]
            await update.message.reply_text("❌ Cancelled.")
            return

        # Try to match text to a category
        categories = await db_client.get_categories()
        match = await classifier.classify_expense(text, categories, explicit_category=text)
        
        # If high confidence match (user likely typed a category name)
        if match['confidence'] > 1.5:
             await save_pending_expense(chat_id, match['category_id'], update)
             return
        
        # If not a category match, we fall through to normal processing
        # The user might be ignoring the prompt and asking a new question
        # But we should probably keep the pending state unless they explicitly cancel
        # or we could auto-cancel if they start a new expense flow?
        # For now, let's just let it fall through but keep the pending state
    
    # Process with LangChain AI agent
    try:
        # LangChain agent will decide which tool to use (with conversation memory)
        response = await hybrid_agent.process_message(text, user_id=user_id, chat_id=chat_id)
        
        if response and isinstance(response, str):
            # Direct response from agent
            await update.message.reply_text(f"🤖 {response}", parse_mode='Markdown')
        else:
            await update.message.reply_text(
                "🤔 I didn't quite understand that. Try asking:\n"
                "• 'Add expense: Costco 120.54'\n"
                "• 'Show my spending this month'\n"
                "• 'What did I spend on restaurants?'\n"
                "• 'Break down expenses by category'"
            )
            
    except Exception as e:
        logger.error(f"LangChain agent error: {e}")
        await update.message.reply_text(
            "❌ I encountered an error processing that. Try:\n"
            "• Asking a simpler question\n" 
            "• Being more specific about what you want\n"
            "• Or just tell me about an expense like 'Costco 50.25'!"
        )

async def handle_expense_result(update: Update, context: ContextTypes.DEFAULT_TYPE, result: dict, chat_id: int, user_id: str):
    """Handle expense entry from hybrid AI processing"""
    parsed = result['parsed']
    classification = result['classification']
    
    merchant = parsed['merchant']
    amount = parsed['amount']
    currency = parsed.get('currency', 'MXN')
    
    if result['needs_confirmation']:
        # Need category confirmation
        pending_expenses[chat_id] = {
            'merchant': merchant,
            'amount': amount,
            'currency': currency,
            'user_id': user_id
        }
        
        # Get suggested categories
        suggestions = classification.get('suggestions', [])[:6]
        if not suggestions:
            categories = await db_client.get_categories()
            suggestions = categories[:6]
        
        keyboard = []
        for cat in suggestions:
            keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"cat:{cat['id']}")])
        
        keyboard.append([InlineKeyboardButton('❌ Cancel', callback_data='cat:cancel')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f'🏷 **I understood:** {merchant} — ${amount:.2f} {currency}\n\n'
            f'Which category fits best?',
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # Auto-save with high confidence
        user_data = await db_client.get_user_by_telegram_id(int(user_id))
        
        await db_client.insert_expense(
            user_id=user_data['id'],
            category_id=classification['category_id'],
            merchant=merchant,
            amount=amount,
            currency=currency
        )
        
        category_name = classification['category_name']
        formatted_amount = converter.format_amount(amount, currency)
        
        await update.message.reply_text(
            f"✅ **Expense saved!**\n\n"
            f"💳 {merchant} — {formatted_amount}\n"
            f"🏷 Category: **{category_name}**\n"
            f"🤖 *Classified automatically with AI*",
            parse_mode='Markdown'
        )

async def handle_quick_analysis_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quick analysis using LangChain agent"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    if callback_data == "cancel":
        await query.edit_message_text("❌ Cancelled.")
        return
    
    # Convert callback to natural language query for LangChain agent
    if callback_data == "custom_query":
        await query.edit_message_text(
            "🧠 **Ask me anything about your expenses!**\n\n"
            "💡 Examples:\n"
            "• Show my spending this month\n"
            "• What did I spend on restaurants this week?\n"
            "• Break down my expenses by category\n"
            "• Show my recent expenses\n\n"
            "Just type your question in the chat! 💬"
        )
        return
    
    # Process through LangChain agent
    await query.edit_message_text("🤖 Processing with AI agent...")
    
    try:
        response = await hybrid_agent.process_message("Show me spending analysis", user_id)
        if response and isinstance(response, str):
            await query.edit_message_text(f"🤖 {response}", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ Could not process the analysis request.")
    except Exception as e:
        logger.error(f"Error in LangChain analysis: {e}")
        await query.edit_message_text(f"❌ Error running analysis: {str(e)}")

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category selection from expense processing"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    choice = query.data.split(':', 1)[1]
    
    if choice == 'cancel':
        if chat_id in pending_expenses:
            del pending_expenses[chat_id]
        await query.edit_message_text('❌ Cancelled.')
        return
    
    if chat_id not in pending_expenses:
        await query.edit_message_text('⚠️ No pending expense found.')
        return
    
    pending = pending_expenses[chat_id]
    category_id = choice
    
    await save_pending_expense(chat_id, category_id, update)

def main():
    """Run the hybrid AI-powered bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment")
        sys.exit(1)
    
    app = Application.builder().token(token).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("quick", quick_analysis_command))
    app.add_handler(CommandHandler("insights", insights_command))
    app.add_handler(CallbackQueryHandler(handle_category_selection, pattern=r'^cat:'))
    app.add_handler(CallbackQueryHandler(handle_quick_analysis_callback, pattern=r'^(quick:|custom_query|cancel)'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    async def start_bot():
        await initialize_components()
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        logger.info("🚀 FinAIssistant LangChain Bot started!")
        logger.info("🔧 LangChain tools and agent executor ready")
        logger.info("🧠 AI-powered decision making between expense parsing and queries")
        logger.info("🤖 Powered by OpenAI GPT-3.5-turbo with function calling")
        logger.info("💬 Natural language expense tracking enabled")
        logger.info("✅ Database connected with 18+ categories")
        
        # Initialize and schedule daily reminders
        reminder = DailyReminder(db_client)
        job_queue = app.job_queue
        
        # Schedule for 7:00 PM Mexico City time
        mx_tz = pytz.timezone('America/Mexico_City')
        reminder_time = time(hour=19, minute=0, tzinfo=mx_tz)
        
        job_queue.run_daily(reminder.send_daily_reminder, time=reminder_time)
        logger.info(f"⏰ Daily reminder scheduled for {reminder_time} (Mexico City time)")
        
        logger.info("📱 Ready to chat on Telegram!")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping hybrid bot...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
    
    asyncio.run(start_bot())

if __name__ == '__main__':
    main()