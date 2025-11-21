import logging
import pytz
from telegram.ext import ContextTypes
from database import SupabaseClient

logger = logging.getLogger(__name__)

class DailyReminder:
    def __init__(self, db: SupabaseClient):
        self.db = db

    async def send_daily_reminder(self, context: ContextTypes.DEFAULT_TYPE):
        """Send daily reminder to all registered users"""
        logger.info("Running daily reminder job...")
        
        try:
            users = await self.db.get_all_users()
            logger.info(f"Found {len(users)} users to remind")
            
            for user in users:
                telegram_id = user.get('telegram_id')
                name = user.get('name', 'User')
                
                if not telegram_id:
                    continue
                    
                try:
                    message = (
                        f"👋 Hey {name}! Just a friendly reminder to record your expenses for today. 📝\n\n"
                        "If you haven't spent anything, you can ignore this. "
                        "Otherwise, just tell me what you bought! 💸"
                    )
                    
                    await context.bot.send_message(chat_id=telegram_id, text=message)
                    logger.info(f"Sent reminder to {name} ({telegram_id})")
                    
                except Exception as e:
                    logger.error(f"Failed to send reminder to {telegram_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in daily reminder job: {e}")
