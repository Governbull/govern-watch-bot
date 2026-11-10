import os, sqlite3, time, threading, traceback
from datetime import date
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DB = "govern.db"
RAID_FILE = "raid.txt"
GROUP_LINK = "https://t.me/governpublic"
X_LINK = "https://x.com/Governbull"
X_HANDLE = "@Governbull"

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
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_daily TEXT, last_raid TEXT, invited_by INTEGER, x_username TEXT, raid_count INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS raids (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, active INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS claimed_tasks (user_id INTEGER, task_id TEXT, PRIMARY KEY(user_id, task_id))")
    c.execute("CREATE TABLE IF NOT EXISTS pending (user_id INTEGER, photo_id TEXT)")
    try: c.execute("ALTER TABLE users ADD COLUMN x_username TEXT")
    except: pass
    try: c.execute("ALTER TABLE users ADD COLUMN raid_count INTEGER DEFAULT 0")
    except: pass
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

def get_invite_count(uid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE invited_by=?", (uid,))
    n = c.fetchone()[0]; conn.close(); return n

TASKS = [
    {"id": "join_tg", "title": "Join Telegram Group", "points": 20, "desc": f"Join our Group: {GROUP_LINK}", "url": GROUP_LINK, "url_text": "📲 Join Group"},
    {"id": "connect_x", "title": "Connect Your X", "points": 10, "desc": "Use /connect @your_username", "url": None, "url_text": None},
    {"id": "follow_x", "title": f"Follow {X_HANDLE} on X", "points": 20, "desc": f"Follow us: {X_LINK}", "url": X_LINK, "url_text": "🐦 Follow on X"},
    {"id": "first_raid", "title": "Complete First Raid", "points": 50, "desc": "Do 1 raid and get Admin approval", "url": None, "url_text": None},
    {"id": "raid_10", "title": "Complete 10 Raids", "points": 200, "desc": "Do 10 raids with approval", "url": None, "url_text": None},
    {"id": "invite_3", "title": "Invite 3 Friends", "points": 30, "desc": "Share your link from /invite", "url": None, "url_text": None},
    {"id": "daily_7", "title": "7-Day Daily Streak", "points": 50, "desc": "Use /daily 7 days in a row", "url": None, "url_text": None},
]

def is_task_claimed(uid, tid):
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("SELECT 1 FROM claimed_tasks WHERE user_id=? AND task_id=?", (uid, tid))
    r = c.fetchone(); conn.close(); return bool(r)

def check_task(uid, tid, row):
    if tid == "join_tg": return True
    if tid == "connect_x": return bool(row[8])
    if tid == "follow_x": return True
    if tid == "first_raid": return (row[9] or 0) >= 1
    if tid == "raid_10": return (row[9] or 0) >= 10
    if tid == "invite_3": return get_invite_count(uid) >= 3
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
          [InlineKeyboardButton("📲 Join Group", url=GROUP_LINK)],
          [InlineKeyboardButton("🐦 Follow on X", url=X_LINK)],
          [InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")],
          [InlineKeyboardButton("📋 Tasks", callback_data="tasks")]]
    await update.message.reply_text(f"👋 Welcome {user.first_name} to GOVERN!\n\nUse /verify to start earning.\nUse /tasks to see tasks.\nUse /raid for active raid.\nUse /daily for daily bonus.\nUse /join to join our group.", reply_markup=InlineKeyboardMarkup(kb))

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET verified=1 WHERE user_id=?", (user.id,))
    if c.rowcount == 0:
        c.execute("INSERT INTO users (user_id, username, verified) VALUES (?,?,1)", (user.id, user.username or user.first_name))
    conn.commit(); conn.close()
    kb = [[InlineKeyboardButton("📲 Join Group", url=GROUP_LINK)],
          [InlineKeyboardButton("🐦 Follow on X", url=X_LINK)],
          [InlineKeyboardButton("📋 Tasks", callback_data="tasks")]]
    await update.message.reply_text("✅ Verified! You are now a CITIZEN.\n\nNext: Join Group + Follow on X, then do /tasks", reply_markup=InlineKeyboardMarkup(kb))

async def join_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📲 Join GOVERN Group", url=GROUP_LINK)],
          [InlineKeyboardButton("🐦 Follow on X", url=X_LINK)]]
    await update.message.reply_text(f"📲 Join our community:\n\nTelegram Group: {GROUP_LINK}\nX: {X_LINK}\n\nAfter joining, go to /tasks and Claim +20 points!", reply_markup=InlineKeyboardMarkup(kb))

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /connect @your_x_username\nExample: /connect @JohnDoe")
        return
    x_user = context.args[0].replace("@", "")
    user = update.effective_user
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("UPDATE users SET x_username=? WHERE user_id=?", (x_user, user.id))
    if c.rowcount == 0:
        c.execute("INSERT INTO users (user_id, username, x_username) VALUES (?,?,?)", (user.id, user.username or user.first_name, x_user))
    conn.commit(); conn.close()
    await update.message.reply_text(f"✅ X connected: @{x_user}\nNow go to /tasks and Claim Connect Your X (+10 points)!")

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    r = get_active_raid()
    if not r:
        await update.message.reply_text("No active raid yet. Wait for admin to set one with /newraid.")
        return
    kb = [[InlineKeyboardButton("🐦 Open Tweet on X", url=r[1])]]
    await update.message.reply_text(f"⚡ ACTIVE RAID:\n\n{r[1]}\n\n1. Like + RT + Comment on X\n2. Take screenshot\n3. Send screenshot here\nAdmin will approve and give you +10 points.", reply_markup=InlineKeyboardMarkup(kb))

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send your raid screenshot as a photo now. Admin will review it.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO pending VALUES (?,?)", (user.id, photo_id))
    conn.commit(); conn.close()
    await update.message.reply_text("📸 Screenshot received! Waiting for Admin approval. You will get +10 points after approval.")
    try:
        kb = [[InlineKeyboardButton("✅ Approve +10", callback_data=f"approve_{user.id}"),
               InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")]]
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=f"🔍 New Raid Proof\n\nFrom: {user.first_name} (@{user.username})\nID: {user.id}\nX: @{get_user(user.id)[8] or 'not connected'}\n\nApprove?", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        print(f"Could not send to admin: {e}", flush=True)

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
        status = "✅ CLAIMED" if claimed else ("🟢 READY - Click Claim" if done else "🔴 NOT DONE")
        extra = ""
        if t["id"] == "first_raid": extra = f" (Raids: {row[9] or 0}/1)"
        if t["id"] == "raid_10": extra = f" (Raids: {row[9] or 0}/10)"
        if t["id"] == "invite_3": extra = f" (Invited: {get_invite_count(user.id)}/3)"
        if t["id"] == "daily_7": extra = f" (Streak: {row[4] or 0}/7)"
        if t["id"] == "connect_x": extra = f" (X: @{row[8]})" if row[8] else " (Not connected)"
        text += f"{t['title']} - {t['points']} pts - {status}{extra}\n{t['desc']}\n\n"
        if t["url"]:
            kb.append([InlineKeyboardButton(t["url_text"], url=t["url"])])
        if done and not claimed:
            kb.append([InlineKeyboardButton(f"✅ Claim {t['title']} +{t['points']} pts", callback_data=f"claim_{t['id']}")])
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
        if task_id == "first_raid": await reply_func(f"Task not done yet: Do 1 raid first. Raids: {row[9] or 0}/1")
        elif task_id == "raid_10": await reply_func(f"Task not done yet: Do 10 raids. Raids: {row[9] or 0}/10")
        elif task_id == "invite_3": await reply_func(f"Invite 3 friends first. Invited: {get_invite_count(user.id)}/3. Share /invite")
        elif task_id == "daily_7": await reply_func(f"Daily streak not 7 yet. Streak: {row[4] or 0}/7. Use /daily")
        elif task_id == "connect_x": await reply_func("Connect X first: /connect @your_username")
        else: await reply_func(f"Task not completed yet: {task['title']}")
        return
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
    await update.message.reply_text(f"💰 Points: {pts}\n🏅 Badge: {badge}\n🏆 Rank: #{get_rank(update.effective_user.id)}\n⚡ Approved Raids: {row[9] or 0}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first."); return
    pts = row[2]
    badge = "GOVERNOR" if pts >= 500 else "ELITE" if pts >= 200 else "WARRIOR" if pts >= 100 else "CITIZEN"
    bot_username = context.bot.username or "GovernWatchBot"
    kb = [[InlineKeyboardButton("📲 Join Group", url=GROUP_LINK)],
          [InlineKeyboardButton("🐦 Follow on X", url=X_LINK)]]
    await update.message.reply_text(f"👤 {user.first_name}\n@{user.username}\nX: @{row[8] or 'Not connected'}\n\nPoints: {pts}\nBadge: {badge}\nRank: #{get_rank(user.id)}\nStreak: {row[4]} days\nApproved Raids: {row[9] or 0}\nInvited: {get_invite_count(user.id)} friends\n\n🔗 Your Invite Link:\nhttps://t.me/{bot_username}?start={user.id}\n\nShare it, get +10 points per person!", reply_markup=InlineKeyboardMarkup(kb))

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
    txt = "🏆
