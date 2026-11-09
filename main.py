import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask
import threading

# ===== CONFIG =====
TOKEN = os.getenv("BOT_TOKEN")
GROUP_USERNAME = "@governpublic"
GROUP_LINK = "https://t.me/governpublic"
ADMIN_IDS = [1375360019]  # <<<< PUT YOUR TELEGRAM ID HERE

# Points
POINTS_VERIFY = 20
POINTS_REFERRAL = 10
POINTS_REFERRAL_BONUS = 10
POINTS_RAID = 30

logging.basicConfig(level=logging.INFO)

# ===== DATABASE =====
def get_db():
    conn = sqlite3.connect("bot.db")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, referred_by INTEGER, verified INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE IF NOT EXISTS raid (id INTEGER PRIMARY KEY, text TEXT, active INTEGER DEFAULT 0)")
    return conn

def add_points(user_id, amount):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (user_id, points) VALUES (?, 0)", (user_id,))
    conn.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_points(user_id):
    conn = get_db()
    cur = conn.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
            if referrer_id != user.id:
                conn = get_db()
                cur = conn.execute("SELECT referred_by FROM users WHERE user_id = ?", (user.id,))
                row = cur.fetchone()
                if not row:
                    conn.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)", (user.id, user.username or "", referrer_id))
                    conn.commit()
                    add_points(referrer_id, POINTS_REFERRAL)
                    try:
                        await context.bot.send_message(chat_id=referrer_id, text=f"🎉 Someone joined with your link! +{POINTS_REFERRAL} points added. Your points: {get_points(referrer_id)}")
                    except: pass
                conn.close()
        except: pass
    else:
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.username or ""))
        conn.commit()
        conn.close()

    keyboard = [
        [InlineKeyboardButton("✅ Join Community", url=GROUP_LINK)],
    ]
    text = (
        f"Hello {user.first_name}! 👋\n\n"
        f"Welcome to **GovernWatch**.\n\n"
        f"**Step 1:** Join our Community\n"
        f"**Step 2:** Send /verify to get +{POINTS_VERIFY} points\n"
        f"**Step 3:** Invite friends with /referral to get +{POINTS_REFERRAL} each\n\n"
        f"Your points: {get_points(user.id)} ⭐\n\n"
        f"Send /help to see all commands."
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_USERNAME, user_id=user_id)
        if member.status in ["member", "administrator", "creator", "restricted"]:
            conn = get_db()
            cur = conn.execute("SELECT verified, referred_by FROM users WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row and row[0] == 1:
                await update.message.reply_text("✅ You are already verified! Your points: " + str(get_points(user_id)))
                conn.close()
                return
            conn.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            add_points(user_id, POINTS_VERIFY)
            await update.message.reply_text(f"✅ Verified! You joined the Group. +{POINTS_VERIFY} points added! ⭐\nYour points now: {get_points(user_id)}")
            if row and row[1]:
                add_points(row[1], POINTS_REFERRAL_BONUS)
                try:
                    await context.bot.send_message(chat_id=row[1], text=f"🎉 Your invitee just verified! +{POINTS_REFERRAL_BONUS} bonus points added.")
                except: pass
        else:
            await update.message.reply_text(f"❌ You have not joined the Group yet.\n\nJoin here first: {GROUP_LINK}\nThen come back and send /verify again")
    except Exception as e:
        await update.message.reply_text(f"❌ Join the Group first: {GROUP_LINK}\nThen come back and send /verify again\n\nIf you already joined but it still fails, make sure the Bot is Admin in the Group.")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user.id,))
    count = cur.fetchone()[0]
    conn.close()
    await update.message.reply_text(
        f"👥 **Your Referral**\n\n"
        f"Your link:\n`{link}`\n\n"
        f"Share this link with friends. For each person who joins with your link, you get +{POINTS_REFERRAL} points.\n"
        f"If they verify, you get +{POINTS_REFERRAL_BONUS} bonus.\n\n"
        f"People you invited: {count}\n"
        f"Your points: {get_points(user.id)} ⭐",
        parse_mode="Markdown"
    )

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⭐ Your points: {get_points(update.effective_user.id)}\n\nEarn more with /verify, /referral and /raid")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cur = conn.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()
    text = "🏆 **LEADERBOARD - Top 10**\n\n"
    for i, (username, pts) in enumerate(rows, 1):
        name = f"@{username}" if username else "User"
        text += f"{i}. {name} - {pts} ⭐\n"
    if not rows:
        text += "No one yet. Be the first!"
    await update.message.reply_text(text, parse_mode="Markdown")

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cur = conn.execute("SELECT text FROM raid WHERE active = 1 ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        await update.message.reply_text(f"🔥 **ACTIVE RAID**\n\n{row[0]}\n\nAfter you finish, send /done", parse_mode="Markdown")
    else:
        await update.message.reply_text("No active Raid right now. Wait for Admin to post a new one.")

async def setraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not an Admin.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setraid <raid message>")
        return
    text = " ".join(context.args)
    conn = get_db()
    conn.execute("UPDATE raid SET active = 0")
    conn.execute("INSERT INTO raid (text, active) VALUES (?, 1)", (text,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Raid set!\n\n{text}")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    cur = conn.execute("SELECT id FROM raid WHERE active = 1 LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        await update.message.reply_text("No active Raid right now.")
        return
    add_points(update.effective_user.id, POINTS_RAID)
    await update.message.reply_text(f"✅ Received! +{POINTS_RAID} points added. Your points: {get_points(update.effective_user.id)} ⭐")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **Commands**\n\n"
        "/start - Start\n"
        "/verify - Verify you joined the Group (Auto)\n"
        "/referral - Get your invite link\n"
        "/points - See your points\n"
        "/leaderboard - Top 10\n"
        "/raid - See current Raid\n"
        "/done - You finished Raid\n"
        "/help - This list\n\n"
        "Admin: /setraid, /stats",
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*), SUM(points) FROM users")
    count, total = cur.fetchone()
    conn.close()
    await update.message.reply_text(f"📊 Stats:\nUsers: {count}\nTotal Points: {total or 0}")

async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Got it! Send /help to see what I can do. If you joined the Group, send /verify.")

# ===== FLASK KEEP ALIVE (Render) =====
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("verify", verify))
    app_bot.add_handler(CommandHandler("referral", referral))
    app_bot.add_handler(CommandHandler("myref", referral))
    app_bot.add_handler(CommandHandler("points", points))
    app_bot.add_handler(CommandHandler("balance", points))
    app_bot.add_handler(CommandHandler("leaderboard", leaderboard))
    app_bot.add_handler(CommandHandler("raid", raid))
    app_bot.add_handler(CommandHandler("setraid", setraid))
    app_bot.add_handler(CommandHandler("done", done))
    app_bot.add_handler(CommandHandler("help", help_cmd))
    app_bot.add_handler(CommandHandler("stats", stats))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
    print("Bot running...")
    app_bot.run_polling()

if __name__ == "__main__":
    main()
