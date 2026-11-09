import os
import sqlite3
from flask import Flask
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.environ.get("BOT_TOKEN")
DB = "users.db"
ADMIN_USERNAME = "GovernBullFounder"

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, x_handle TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS raids (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, active INTEGER DEFAULT 1)")
    cur.execute("CREATE TABLE IF NOT EXISTS raid_done (user_id INTEGER, raid_id INTEGER, PRIMARY KEY (user_id, raid_id))")
    con.commit()
    con.close()

def add_user(user_id, username):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    con.commit()
    con.close()

def get_user(user_id):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT points, x_handle FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    con.close()
    return row

def get_active_raid():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT id, link FROM raids WHERE active=1 ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    con.close()
    return row

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    add_user(u.id, u.username)
    kb = [[InlineKeyboardButton("Join Community", url="https://t.me/Governpublic")], [InlineKeyboardButton("Connect X", callback_data="connect")]]
    await update.message.reply_text(f"Welcome to GOVERNBULL - {u.first_name}\n\nUse /verify to start raid, /profile to view profile.", reply_markup=InlineKeyboardMarkup(kb))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commands:\n/start - Start\n/verify - Verify raid\n/profile - My profile\n/leaderboard - Top users\n/connect - Connect X\n/setx your_username - Set X handle\n/join - Join raid\n/raid - Show current Raid\n/done - I finished Raid (+50 pts)\n/setraid <link> - Admin only")

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Verify: https://t.me/Governpublic - Send proof after joining.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    row = get_user(u.id)
    pts = row[0] if row else 0
    xh = row[1] if row and row[1] else "Not connected"
    await update.message.reply_text(f"👤 {u.first_name}\nX: @{xh}\nPoints: {pts}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = cur.fetchall()
    con.close()
    txt = "🏆 LEADERBOARD\n\n" + "\n".join([f"{i+1}. @{r[0]} - {r[1]} pts" for i, r in enumerate(rows)]) if rows else "No users yet."
    await update.message.reply_text(txt)

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("To connect X, send:\n/setx your_username\nexample: /setx governbull")

async def setx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /setx your_username")
        return
    handle = context.args[0].replace("@", "")
    u = update.effective_user
    add_user(u.id, u.username)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("UPDATE users SET x_handle=? WHERE user_id=?", (handle, u.id))
    con.commit()
    con.close()
    row = get_user(u.id)
    if row and row[0] == 0:
        con = sqlite3.connect(DB)
        cur = con.cursor()
        cur.execute("UPDATE users SET points = points + 20 WHERE user_id=?", (u.id,))
        con.commit()
        con.close()
        await update.message.reply_text(f"✅ X connected: @{handle} +20 points")
    else:
        await update.message.reply_text(f"✅ X updated: @{handle}")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Join here: https://t.me/AfWfTbcTgFz1")

async def setraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u.username != ADMIN_USERNAME:
        await update.message.reply_text("❌ Admin only! Only the Council Admin can set a Raid.")
        return
    if not context.args:
        await update.message.reply_text("Use: /setraid https://x.com/governbull/status/...")
        return
    link = context.args[0]
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("UPDATE raids SET active=0")
    cur.execute("INSERT INTO raids (link, active) VALUES (?, 1)", (link,))
    con.commit()
    con.close()
    await update.message.reply_text(f"🚨 NEW RAID POSTED!\n\nCouncil members, go and complete it:\n❤️ Like\n🔁 Repost\n💬 Comment\n\nLink: {link}\n\nWhen you finish, send /done")

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    row = get_user(u.id)
    if not row or not row[1]:
        await update.message.reply_text("❌ You are not a Council member yet!\nFirst send: /setx your_username")
        return
    r = get_active_raid()
    if not r:
        await update.message.reply_text("There is no active Raid right now. Please wait for the Admin to post a new one.")
        return
    await update.message.reply_text(f"🔥 CURRENT RAID\n\n1. Open this link:\n{r[1]}\n\n2. Like ❤️\n3. Repost 🔁\n4. Comment 💬\n\nWhen you are done, send:\n/done\n\nYou will earn +50 Points!")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    row = get_user(u.id)
    if not row or not row[1]:
        await update.message.reply_text("❌ First send /setx your_username, then send /raid")
        return
    r = get_active_raid()
    if not r:
        await update.message.reply_text("There is no active Raid right now.")
        return
    raid_id = r[0]
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT * FROM raid_done WHERE user_id=? AND raid_id=?", (u.id, raid_id))
    exists = cur.fetchone()
    if exists:
        con.close()
        await update.message.reply_text("⚠️ You already received points for this Raid! Please wait for the next Raid.")
        return
    cur.execute("INSERT INTO raid_done (user_id, raid_id) VALUES (?, ?)", (u.id, raid_id))
    cur.execute("UPDATE users SET points = points + 50 WHERE user_id=?", (u.id,))
    con.commit()
    con.close()
    await update.message.reply_text("✅ Raid Completed! +50 Points!\n\nCheck /profile - Your points have increased. Check /leaderboard!")

if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("setx", setx))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("setraid", setraid))
    app.add_handler(CommandHandler("raid", raid))
    app.add_handler(CommandHandler("done", done))
    print("Bot running...")
    threading.Thread(target=run_flask, daemon=True).start()
    app.run_polling()
