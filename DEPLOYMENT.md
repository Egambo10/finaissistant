# 🚀 Deployment Guide - Railway

This guide will help you deploy your FinAIssistant Telegram bot to Railway.

## ✅ Prerequisites

1. **Railway Account** - Sign up at [railway.app](https://railway.app)
2. **GitHub Repository** - Push your code to GitHub
3. **Environment Variables** - Have your API keys ready

## 📦 What's Included

Your project is already configured for Railway with:
- ✅ `Procfile` - Tells Railway how to start the bot
- ✅ `requirements.txt` - Python dependencies
- ✅ `runtime.txt` - Python version specification
- ✅ `.railwayignore` - Files to exclude from deployment
- ✅ `.gitignore` - Files to exclude from Git

## 🔧 Step-by-Step Deployment

### 1. Push to GitHub

```bash
cd /Users/erikgamboa/Documents/FinAIssistant_v2

# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - FinAIssistant v2"

# Add your GitHub remote
git remote add origin https://github.com/YOUR_USERNAME/FinAIssistant_v2.git

# Push to GitHub
git push -u origin main
```

### 2. Deploy to Railway

1. **Go to** [railway.app](https://railway.app) and login
2. **Click** "New Project"
3. **Select** "Deploy from GitHub repo"
4. **Choose** your `FinAIssistant_v2` repository
5. Railway will automatically detect your Python app

### 3. Configure Environment Variables

In Railway dashboard, go to **Variables** tab and add:

#### Required Variables:

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# Supabase
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Currency API (ExchangeRate-API or similar)
CURRENCY_API_KEY=your_currency_api_key

# Python (optional - for better performance)
PYTHONUNBUFFERED=1
```

#### Get Your Variables:

- **Telegram Bot Token**: Get from [@BotFather](https://t.me/botfather) on Telegram
- **Supabase**: From your [Supabase Dashboard](https://supabase.com/dashboard)
  - URL: Project Settings → API → URL
  - Key: Project Settings → API → service_role key
- **OpenAI**: From [platform.openai.com](https://platform.openai.com/api-keys)
- **Currency API**: From [exchangerate-api.com](https://www.exchangerate-api.com/) or similar

### 4. Deploy!

Railway will automatically:
1. ✅ Install dependencies from `requirements.txt`
2. ✅ Run `python3 hybrid_bot.py` (from `Procfile`)
3. ✅ Keep your bot running 24/7
4. ✅ Restart automatically if it crashes

## 🔍 Monitor Your Deployment

### View Logs
In Railway dashboard:
- Click on your deployment
- Go to **"Logs"** tab
- Look for: `🚀 FinAIssistant LangChain Bot started!`

### Check Bot Status
1. Open Telegram
2. Send `/start` to your bot
3. Try: "What's my budget for this month?"

## 💡 Important Notes

### ChromaDB/Vanna AI Data
- **First deployment**: Vanna will train from scratch (takes ~30 seconds)
- **Subsequent deployments**: Vanna data persists in Railway's filesystem
- If you redeploy, Vanna will retrain automatically

### Conversation Memory
- ✅ Works perfectly on Railway (persistent RAM)
- ✅ Remembers last 5 messages per chat
- ⚠️ Will reset if Railway restarts the service (rare)

### Railway Pricing
- **Starter Plan**: $5/month (500 hours included)
- **Free Trial**: $5 credit to start
- Your bot uses minimal resources (~100MB RAM)

## 🐛 Troubleshooting

### Bot doesn't respond
1. Check Railway logs for errors
2. Verify environment variables are set correctly
3. Ensure TELEGRAM_BOT_TOKEN is correct

### "Module not found" error
- Railway should auto-install from `requirements.txt`
- Check logs to confirm packages installed

### Database connection error
- Verify SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
- Check Supabase project is active

## 🔄 Updating Your Bot

After making code changes:

```bash
# Commit changes
git add .
git commit -m "Description of changes"

# Push to GitHub
git push

# Railway auto-deploys! 🎉
```

Railway automatically detects the push and redeploys.

## 📊 What Works on Railway

✅ **Long-running bot** (polling)
✅ **Conversation memory** (in-memory)
✅ **ChromaDB/Vanna AI** (local filesystem)
✅ **Supabase database**
✅ **OpenAI API calls**
✅ **Currency conversion**
✅ **24/7 uptime**

## 🎯 Next Steps

1. Push your code to GitHub
2. Deploy to Railway
3. Set environment variables
4. Start chatting with your bot!

Need help? Check Railway's [documentation](https://docs.railway.app/) or ping me! 🚀

