import os, sqlite3, time, threading, traceback
from datetime import date
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DB = "govern.db"
RAID_FILE = "raid.txt"

app = Flask(__name__)
@app.route('/')
def home():
    return "GOVERN Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_daily TEXT, last_raid TEXT, invited_by INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS raids (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, active INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS claimed_tasks (user_id INTEGER, task_id TEXT, PRIMARY KEY(user_id, task_id))")
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone(); conn.close(); return row

def add_points(uid, pts):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET points=points+? WHERE user_id=?", (pts, uid))
    conn.commit(); conn.close()

def get_rank(uid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT user_id FROM users ORDER BY points DESC")
    rows = c.fetchall(); conn.close()
    for i, (u,) in enumerate(rows, 1):
        if u == uid: return i
    return 0

def get_active_raid():
    try:
        with open(RAID_FILE, "r") as f:
            link = f.read().strip()
            if link: return (0, link)
    except: pass
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT id, link FROM raids WHERE active=1 ORDER BY id DESC LIMIT 1")
    row = c.fetchone(); conn.close(); return row

def save_raid(link):
    with open(RAID_FILE, "w") as f: f.write(link)
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE raids SET active=0")
    c.execute("INSERT INTO raids (link, active) VALUES (?,1)", (link,))
    conn.commit(); conn.close()

TASKS = [
    {"id": "join_tg", "title": "Join Telegram Group", "points": 20, "desc": "Join @GovernBull"},
    {"id": "connect_x", "title": "Connect Your X", "points": 10, "desc": "Use /connect"},
    {"id": "follow_x", "title": "Follow @GovernBull on X", "points": 20, "desc": "Follow on X"},
    {"id": "first_raid", "title": "Complete First Raid", "points": 50, "desc": "Do 1 raid"},
    {"id": "raid_10", "title": "Complete 10 Raids", "points": 200, "desc": "Do 10 raids"},
    {"id": "invite_3", "title": "Invite 3 Friends", "points": 30, "desc": "Share your link"},
    {"id": "daily_7", "title": "7-Day Daily Streak", "points": 50, "desc": "Use /daily 7 days"},
]

def is_task_claimed(uid, tid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT 1 FROM claimed_tasks WHERE user_id=? AND task_id=?", (uid, tid))
    r = c.fetchone(); conn.close(); return bool(r)

def check_task(uid, tid, row):
    if tid in ["join_tg", "connect_x", "follow_x", "first_raid"]: return True
    if tid == "daily_7": return (row[4] or 0) >= 7
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    invited_by = int(args[0]) if args and args[0].isdigit() else None
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    exists = c.fetchone()
    if not exists:
        c.execute("INSERT INTO users (user_id, username, invited_by) VALUES (?,?,?)", (user.id, user.username or user.first_name, invited_by))
        conn.commit()
        if invited_by and invited_by != user.id:
            c.execute("UPDATE users SET points=points+10 WHERE user_id=?", (invited_by,))
            conn.commit()
            try:
                await context.bot.send_message(chat_id=invited_by, text=f"🎉 Sabon mutum ya shiga ta link dinka! +10 points! {user.first_name}")
            except: pass
    conn.close()
    kb = [[InlineKeyboardButton("✅ Verify", callback_data="verify")],
          [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
          [InlineKeyboardButton("📋 Tasks", callback_data="tasks")]]
    await update.message.reply_text(f"👋 Welcome {user.first_name} to GOVERN!\n\nUse /verify to start earning.\nUse /tasks to see tasks.\nUse /raid for active raid.\nUse /daily for daily bonus.", reply_markup=InlineKeyboardMarkup(kb))

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET verified=1 WHERE user_id=?", (user.id,))
    if c.rowcount == 0:
        c.execute("INSERT INTO users (user_id, username, verified) VALUES (?,?,1)", (user.id, user.username or user.first_name))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Verified! You are now a CITIZEN.\nUse /raid to join raid, /daily for bonus.")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /connect @your_x_username")
        return
    await update.message.reply_text(f"✅ X connected: {context.args[0]}\n+10 points!")
    add_points(update.effective_user.id, 10)

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = get_active_raid()
    if not r:
        await update.message.reply_text("No active raid. Wait for admin.")
        return
    await update.message.reply_text(f"⚡ ACTIVE RAID:\n\n{r[1]}\n\nLike + RT + Comment, then send screenshot here with /done")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send your raid screenshot as a photo now.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text("📸 Screenshot received! Admin will review. +10 points pending.")
    add_points(user.id, 10)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    today = date.today().isoformat()
    if row[5] == today:
        await update.message.reply_text(f"Already claimed today! Streak: {row[4]} days")
        return
    last = row[5]
    try:
        streak = row[4] + 1 if last and (date.fromisoformat(today) - date.fromisoformat(last)).days == 1 else 1
    except: streak = 1
    bonus = 50 if streak >= 7 else 0
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET points=points+?, last_daily=?, streak=? WHERE user_id=?", (10+bonus, today, streak, user.id))
    conn.commit(); conn.close()
    msg = f"✅ DAILY CHECK-IN!\n+10 Points\nStreak: {streak} days"
    if bonus: msg += "\n🎉 7-DAY BONUS! +50 Points"
    await update.message.reply_text(msg)

async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    text = "📋 GOVERN TASKS:\n\n"
    kb = []
    for t in TASKS:
        claimed = is_task_claimed(user.id, t["id"])
        done = check_task(user.id, t["id"], row)
        status = "CLAIMED" if claimed else ("READY - Click Claim" if done else "NOT DONE")
        text += f"{t['title']} - {t['points']} pts - {status}\n{t['desc']}\n\n"
        if done and not claimed:
            kb.append([InlineKeyboardButton(f"Claim {t['title']}", callback_data=f"claim_{t['id']}")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb) if kb else None)

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /claim <task_id>\nSee /tasks for IDs")
        return
    await handle_claim(update.effective_user, context.args[0], update.message.reply_text)

async def handle_claim(user, task_id, reply_func):
    row = get_user(user.id)
    if not row:
        await reply_func("Type /verify first."); return
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        await reply_func("Invalid task ID."); return
    if is_task_claimed(user.id, task_id):
        await reply_func("Already claimed."); return
    if not check_task(user.id, task_id, row):
        await reply_func(f"Task not completed yet: {task['title']}"); return
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO claimed_tasks VALUES (?,?)", (user.id, task_id))
    conn.commit(); conn.close()
    add_points(user.id, task["points"])
    await reply_func(f"✅ Claimed {task['title']}! +{task['points']} points!")

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_user(update.effective_user.id)
    if not row:
        await update.message.reply_text("Type /verify first."); return
    pts = row[2]
    badge = "GOVERNOR" if pts >= 500 else "ELITE" if pts >= 200 else "WARRIOR" if pts >= 100 else "CITIZEN"
    await update.message.reply_text(f"💰 Points: {pts}\n🏅 Badge: {badge}\n🏆 Rank: #{get_rank(update.effective_user.id)}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first."); return
    pts = row[2]
    badge = "GOVERNOR" if pts >= 500 else "ELITE" if pts >= 200 else "WARRIOR" if pts >= 100 else "CITIZEN"
    bot_username = context.bot.username or "GovernWatchBot"
    await update.message.reply_text(f"👤 {user.first_name}\n@{user.username}\n\nPoints: {pts}\nBadge: {badge}\nRank: #{get_rank(user.id)}\nStreak: {row[4]} days\n\n🔗 Your Invite Link:\nhttps://t.me/{bot_username}?start={user.id}")

async def rank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first."); return
    await update.message.reply_text(f"🏆 Your Rank: #{get_rank(user.id)}\nPoints: {row[2]}")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall(); conn.close()
    if not rows:
        await update.message.reply_text("No citizens yet. /verify")
        return
    txt = "🏆 GOVERN Leaderboard:\n\n"
    for i, (name, pts) in enumerate(rows, 1):
        txt += f"{i}. {name or 'User'} - {pts} pts\n"
    await update.message.reply_text(txt)

async def newraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only."); return
    if not context.args:
        await update.message.reply_text("Usage: /newraid <tweet link>")
        return
    link = " ".join(context.args)
    save_raid(link)
    await update.message.reply_text(f"✅ New Raid Set!\n{link}\n\nEveryone who sends /raid will see this post.")

async def setraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await newraid(update, context)

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("Approved!")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("Rejected.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "verify":
        await verify(update, context)
    elif q.data == "leaderboard":
        await leaderboard(update, context)
    elif q.data == "tasks":
        await tasks_cmd(update, context)
    elif q.data.startswith("claim_"):
        await handle_claim(q.from_user, q.data.replace("claim_", ""), q.message.reply_text)

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        await update.message.reply_text("Use /start to see menu, /raid for raid, /daily for bonus.")

def main():
    print("=== STARTING BOT ===", flush=True)
    print(f"BOT_TOKEN exists? {bool(BOT_TOKEN)}", flush=True)
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN IS MISSING!", flush=True)
        while True: time.sleep(60)
    try:
        init_db()
        threading.Thread(target=run_flask, daemon=True).start()
        print("Flask started, starting Telegram polling...", flush=True)
        b = ApplicationBuilder().token(BOT_TOKEN).build()
        b.add_handler(CommandHandler("start", start))
        b.add_handler(CommandHandler("help", start))
        b.add_handler(CommandHandler("verify", verify))
        b.add_handler(CommandHandler("connect", connect))
        b.add_handler(CommandHandler("raid", raid))
        b.add_handler(CommandHandler("done", done))
        b.add_handler(CommandHandler("myraid", raid))
        b.add_handler(CommandHandler("daily", daily))
        b.add_handler(CommandHandler("tasks", tasks_cmd))
        b.add_handler(CommandHandler("claim", claim))
        b.add_handler(CommandHandler("invite", profile))
        b.add_handler(CommandHandler("points", points))
        b.add_handler(CommandHandler("profile", profile))
        b.add_handler(CommandHandler("rank", rank_cmd))
        b.add_handler(CommandHandler("leaderboard", leaderboard))
        b.add_handler(CommandHandler("newraid", newraid))
        b.add_handler(CommandHandler("setraid", setraid))
        b.add_handler(CommandHandler("approve", approve))
        b.add_handler(CommandHandler("reject", reject))
        b.add_handler(CallbackQueryHandler(button_handler))
        b.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        b.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all))
        print("Bot Started...", flush=True)
        b.run_polling()
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        traceback.print_exc()
        while True: time.sleep(60)

if __name__ == "__main__":
    main()
