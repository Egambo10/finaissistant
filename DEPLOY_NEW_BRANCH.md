# Deploy New Branch to Railway

## Option 1: Change Deployment Branch (Easiest - Test in Production)

1. **Go to Railway Dashboard**: https://railway.app
2. **Select your project**: FinAIssistant
3. **Click on your service** (the one running hybrid_bot.py)
4. **Go to Settings tab**
5. **Scroll to "Source" section**
6. **Find "Branch" setting**
7. **Change from current branch to**: `claude/validate-vanna-ai-integration-011CUSma1UMuxtMqjKxqK3uv`
8. **Railway will auto-deploy** the new branch

**⚠️ Warning**: This changes your production deployment!

---

## Option 2: Create New Railway Service (Safer - Test Separately)

This creates a **parallel deployment** so you can test without affecting production.

### Step 1: In Railway Dashboard

1. Go to your Railway project
2. Click **"+ New Service"**
3. Select **"GitHub Repo"**
4. Choose **"Egambo10/finaissistant"**
5. In **Branch** dropdown, select: `claude/validate-vanna-ai-integration-011CUSma1UMuxtMqjKxqK3uv`
6. Click **"Deploy"**

### Step 2: Configure Environment Variables

Copy all environment variables from your existing service:
- `TELEGRAM_BOT_TOKEN` - ⚠️ **IMPORTANT**: Use a DIFFERENT bot token for testing!
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`

### Step 3: Create a Test Telegram Bot

1. Go to Telegram and message **@BotFather**
2. Send `/newbot`
3. Follow instructions to create **"FinAIssistant Test Bot"**
4. Copy the new bot token
5. Use this token in the new Railway service's `TELEGRAM_BOT_TOKEN`

### Step 4: Test!

- Original bot: Still running on old branch
- Test bot: Running on new Vanna AI branch
- Both use same database (safe - only reads for queries)

---

## Option 3: Railway CLI (For Developers)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Link to your project
railway link

# Deploy specific branch
railway up --branch claude/validate-vanna-ai-integration-011CUSma1UMuxtMqjKxqK3uv
```

---

## Recommended Approach

**For Quick Test (5 minutes)**:
→ **Option 1** - Change branch in settings, test, then switch back

**For Safe Test (10 minutes)**:
→ **Option 2** - Create separate service with test bot

---

## After Testing

If Vanna AI works well:
1. ✅ Merge the branch to main
2. ✅ Switch production back to main branch
3. ✅ Delete test service if you created one

If issues found:
1. ❌ Switch back to original branch
2. ❌ Report issues
3. ❌ Fix and retry
