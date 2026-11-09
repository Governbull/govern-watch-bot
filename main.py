import os
from flask import Flask
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sqlite3
TOKEN = os.environ.get("BOT_TOKEN")
  

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"
DB = "govern.db"
def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, x_handle TEXT)")
    con.commit(); con.close()
def add_user(user_id, username):
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)", (user_id, username))
    con.commit(); con.close()
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    add_user(u.id, u.username or u.first_name)
    kb = [[InlineKeyboardButton("Join Public Community", url="https://t.co/AfwF1RcfZo")],[InlineKeyboardButton("Connect X", callback_data="connect")]]
    await update.message.reply_text(f"Welcome to GOVERN, {u.first_name}!\n\nYour raid command center.\n\nUse /raid to start, /profile to see points, /leaderboard for top raiders.", reply_markup=InlineKeyboardMarkup(kb))
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start - Start\n/raid - Start a raid\n/verify - Verify raid\n/profile - Your points\n/leaderboard - Top users\n/connect - Connect X\n/setx <handle> - Set X handle\n/join - Join community")
async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 NEW RAID!\n\n1. Like + RT + Comment: https://t.co/AfwF1RcfZo\n2. Send /verify after you finish\n\n+50 points per raid!")
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("UPDATE users SET points = points + 50 WHERE user_id=?", (u.id,))
    con.commit(); con.close()
    await update.message.reply_text("✅ Verified! +50 points added. Check /profile")
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("SELECT points, x_handle FROM users WHERE user_id=?", (u.id,))
    row = cur.fetchone(); con.close()
    pts = row[0] if row else 0
    xh = row[1] if row and row[1] else "Not connected"
    await update.message.reply_text(f"👤 {u.first_name}\nX: {xh}\nPoints: {pts}\nRank: Raider")
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = cur.fetchall(); con.close()
    txt = "🏆 LEADERBOARD\n\n" + "\n".join([f"{i+1}. @{r[0]} - {r[1]} pts" for i,r in enumerate(rows)]) if rows else "No users yet"
    await update.message.reply_text(txt)
async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("To connect X, send:\n/setx your_username\nExample: /setx govern_ng")
async def setx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /setx your_username"); return
    handle = context.args[0].replace("@","")
    u = update.effective_user
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("UPDATE users SET x_handle=? WHERE user_id=?", (handle, u.id))
    con.commit(); con.close()
    await update.message.reply_text(f"✅ X connected: @{handle} +20 points")
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("UPDATE users SET points = points + 20 WHERE user_id=?", (u.id,)); con.commit(); con.close()
async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Join here: https://t.co/AfwF1RcfZo")
async def setraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Admin only - Raid set!")
if __name__ == "__main__":
    init_db()
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("raid", raid))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("setx", setx))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("setraid", setraid))
      print("Bot running...")
    threading.Thread(target=run_flask, daemon=True).start()
    app.run_polling()
