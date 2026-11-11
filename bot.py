import os
import sqlite3
import threading
from datetime import date
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Persistent DB - survives Render restarts if Disk /data exists
DATA_DIR = "/data" if os.path.exists("/data") else "."
DB = os.path.join(DATA_DIR, "govern.db")
RAID_FILE = os.path.join(DATA_DIR, "raid.txt")

GROUP_LINK = "https://t.me/governpublic"
X_LINK = "https://x.com/Governbull"
X_HANDLE = "@Governbull"

app = Flask(__name__)

@app.route("/")
def home():
    return "GOVERN Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ===== DATABASE =====
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        points INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_daily TEXT,
        last_raid TEXT,
        invited_by INTEGER,
        x_username TEXT,
        raid_count INTEGER DEFAULT 0,
        joined_group INTEGER DEFAULT 0
    )""")
    c.execute("CREATE TABLE IF NOT EXISTS raids (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, active INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS claimed_tasks (user_id INTEGER, task_id TEXT, PRIMARY KEY(user_id, task_id))")
    c.execute("CREATE TABLE IF NOT EXISTS pending (user_id INTEGER, photo_id TEXT)")
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    conn.close()
    return row

def add_points(uid, pts):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET points=points+? WHERE user_id=?", (pts, uid))
    conn.commit()
    conn.close()

def get_rank(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users ORDER BY points DESC")
    rows = c.fetchall()
    conn.close()
    for i, r in enumerate(rows, 1):
        if r[0] == uid:
            return i
    return 0

def get_active_raid():
    try:
        with open(RAID_FILE, "r") as f:
            link = f.read().strip()
            if link:
                return (0, link)
    except:
        pass
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, link FROM raids WHERE active=1 ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def save_raid(link):
    with open(RAID_FILE, "w") as f:
        f.write(link)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE raids SET active=0")
    c.execute("INSERT INTO raids (link, active) VALUES (?,1)", (link,))
    conn.commit()
    conn.close()

def get_invite_count(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE invited_by=?", (uid,))
    n = c.fetchone()[0]
    conn.close()
    return n

def get_badge(pts):
    if pts >= 500:
        return "GOVERNOR"
    if pts >= 200:
        return "ELITE"
    if pts >= 100:
        return "WARRIOR"
    return "CITIZEN"

async def check_group(update):
    if update.effective_chat.type in ["group", "supergroup"]:
        txt = "Please use DM for all bot commands.\nGo to @GovernWatchBot and send your command there."
        try:
            await update.message.reply_text(txt)
        except:
            pass
        return True
    return False

# ===== TASKS =====
TASKS = [
    {"id": "join_tg", "title": "Join Telegram Group", "points": 20, "desc": "Join our community group"},
    {"id": "connect_x", "title": "Connect Your X", "points": 10, "desc": "Use /connect @your_username"},
    {"id": "follow_x", "title": "Follow on X", "points": 20, "desc": "Follow @Governbull on X"},
    {"id": "first_raid", "title": "Complete First Raid", "points": 50, "desc": "Do 1 raid and get approval"},
    {"id": "raid_10", "title": "Complete 10 Raids", "points": 200, "desc": "Do 10 raids with approval"},
    {"id": "invite_3", "title": "Invite 3 Friends", "points": 30, "desc": "Share your link from /profile"},
    {"id": "daily_7", "title": "7-Day Daily Streak", "points": 50, "desc": "Use /daily 7 days in a row"},
]

def is_task_claimed(uid, tid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM claimed_tasks WHERE user_id=? AND task_id=?", (uid, tid))
    r = c.fetchone()
    conn.close()
    return bool(r)

def check_task(uid, tid, row):
    # row indexes: 0=id,1=username,2=points,3=verified,4=streak,5=last_daily,6=last_raid,7=invited_by,8=x_username,9=raid_count,10=joined_group
    if tid == "join_tg":
        return bool(row[3]) or bool(row[10])
    if tid == "connect_x":
        return bool(row[8])
    if tid == "follow_x":
        return bool(row[3])
    if tid == "first_raid":
        return (row[9] or 0) >= 1
    if tid == "raid_10":
        return (row[9] or 0) >= 10
    if tid == "invite_3":
        return get_invite_count(uid) >= 3
    if tid == "daily_7":
        return (row[4] or 0) >= 7
    return False

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    user = update.effective_user
    args = context.args
    invited_by = None
    if args and args[0].isdigit():
        invited_by = int(args[0])

    existing = get_user(user.id)
    if existing:
        # RETURNING USER - Never create again, never reset points
        kb = []
        kb.append([InlineKeyboardButton("📋 My Profile", callback_data="profile")])
        kb.append([InlineKeyboardButton("🎯 Tasks", callback_data="tasks")])
        kb.append([InlineKeyboardButton("🔥 Active Raid", callback_data="raid")])
        kb.append([InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")])
        txt = f"Welcome back, {user.first_name}! 👋\n\n"
        txt += f"Points: {existing[2]} ⭐\n"
        txt += f"Badge: {get_badge(existing[2])}\n"
        txt += f"Rank: #{get_rank(user.id)}\n\n"
        txt += "You are already part of GOVERN. No need to join again.\n"
        txt += "Use /tasks to continue earning."
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
        return

    # NEW USER ONLY
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO users (user_id, username, invited_by) VALUES (?,?,?)", (user.id, user.username or user.first_name, invited_by))
    conn.commit()
    if invited_by and invited_by != user.id:
        c.execute("UPDATE users SET points=points+10 WHERE user_id=?", (invited_by,))
        conn.commit()
        try:
            await context.bot.send_message(chat_id=invited_by, text="New user joined with your link! +10 points!")
        except:
            pass
    conn.close()

    kb = []
    kb.append([InlineKeyboardButton("✅ Verify", callback_data="verify")])
    kb.append([InlineKeyboardButton("👥 Join Group", url=GROUP_LINK)])
    kb.append([InlineKeyboardButton("𝕏 Follow on X", url=X_LINK)])
    txt = f"Welcome to GOVERN, {user.first_name}! 👑\n\n"
    txt += "We build together. We win together.\n\n"
    txt += "Step 1: Tap Verify below\n"
    txt += "Step 2: Complete Tasks\n"
    txt += "Step 3: Join Raids & Earn\n\n"
    txt += "Use /verify to start."
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

# ===== VERIFY - NEVER RESETS =====
async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_callback = bool(update.callback_query)
    if is_callback:
        if update.effective_chat.type in ["group", "supergroup"]:
            await update.callback_query.answer("Please use DM @GovernWatchBot", show_alert=True)
            return
    else:
        if await check_group(update):
            return
    user = update.effective_user
    existing = get_user(user.id)

    if existing and existing[3] == 1:
        # ALREADY VERIFIED - Show status, do NOT reset, do NOT show join again
        kb = []
        kb.append([InlineKeyboardButton("📋 My Profile", callback_data="profile")])
        kb.append([InlineKeyboardButton("🎯 Tasks", callback_data="tasks")])
        txt = f"You are already verified, {user.first_name}! ✅\n\n"
        txt += f"Points: {existing[2]} ⭐\n"
        txt += f"Badge: {get_badge(existing[2])}\n"
        txt += f"Rank: #{get_rank(user.id)}\n\n"
        txt += "You already joined the community. No need to join again."
        if is_callback:
            await update.callback_query.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
        return

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if existing:
        c.execute("UPDATE users SET verified=1, joined_group=1, username=? WHERE user_id=?", (user.username or user.first_name, user.id))
    else:
        c.execute("INSERT INTO users (user_id, username, verified, joined_group) VALUES (?,?,1,1)", (user.id, user.username or user.first_name))
    conn.commit()
    conn.close()

    kb = []
    kb.append([InlineKeyboardButton("🎯 View Tasks", callback_data="tasks")])
    kb.append([InlineKeyboardButton("👥 Join Group", url=GROUP_LINK)])
    txt = "Verified! You are now a CITIZEN. ✅\n\n"
    txt += "Welcome to GOVERN.\n"
    txt += "Next: Go to Tasks and Claim your points."
    if is_callback:
        await update.callback_query.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def join_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    user = update.effective_user
    row = get_user(user.id)
    # If already joined/verified, don't show join again
    if row and (row[3] == 1 or row[10] == 1):
        await update.message.reply_text(f"You already joined, {user.first_name}! ✅\nYou are part of GOVERN.\nUse /tasks to continue earning.")
        return
    kb = [[InlineKeyboardButton("Join GOVERN Group", url=GROUP_LINK)], [InlineKeyboardButton("Follow on X", url=X_LINK)]]
    txt = "Join our community:\nTelegram: " + GROUP_LINK + "\nX: " + X_LINK + "\n\nAfter joining, send /verify"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /connect @your_x_username")
        return
    x_user = context.args[0].replace("@", "")
    user = update.effective_user
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET x_username=? WHERE user_id=?", (x_user, user.id))
    if c.rowcount == 0:
        c.execute("INSERT INTO users (user_id, username, x_username, verified) VALUES (?,?,?,1)", (user.id, user.username or user.first_name, x_user))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"X connected: @{x_user} ✅\nNow go to /tasks and Claim +10 points!")

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    r = get_active_raid()
    if not r:
        await update.message.reply_text("No active raid yet. Wait for admin to set one.")
        return
    kb = [[InlineKeyboardButton("Open Tweet on X", url=r[1])]]
    txt = "ACTIVE RAID:\n\n" + r[1] + "\n\n1. Like + Repost + Comment on X\n2. Take a screenshot\n3. Send the screenshot here\nAdmin will approve and give you +10 points."
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    await update.message.reply_text("Send your raid screenshot as a photo now. Admin will review it.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        await update.message.reply_text("Please send your raid screenshot in DM with @GovernWatchBot, not in the group.")
        return
    user = update.effective_user
    if not get_user(user.id):
        await update.message.reply_text("Type /verify first.")
        return
    photo_id = update.message.photo[-1].file_id
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO pending VALUES (?,?)", (user.id, photo_id))
    conn.commit()
    conn.close()
    await update.message.reply_text("Screenshot received! Waiting for admin approval. +10 points after approval.")
    try:
        kb = []
        kb.append([InlineKeyboardButton("Approve +10", callback_data="approve_" + str(user.id))])
        kb.append([InlineKeyboardButton("Reject", callback_data="reject_" + str(user.id))])
        cap = "New Raid Proof\nFrom: " + user.first_name + " @" + (user.username or "") + "\nID: " + str(user.id)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=cap, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        print(e, flush=True)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    today = date.today().isoformat()
    if row[5] == today:
        await update.message.reply_text("Already claimed today! Come back tomorrow. ✅")
        return
    last = row[5]
    streak = 1
    try:
        if last and (date.fromisoformat(today) - date.fromisoformat(last)).days == 1:
            streak = row[4] + 1
    except:
        streak = 1
    bonus = 50 if streak >= 7 else 0
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET points=points+?, last_daily=?, streak=? WHERE user_id=?", (10 + bonus, today, streak, user.id))
    conn.commit()
    conn.close()
    msg = f"DAILY CHECK-IN! ✅\n+10 Points\nStreak: {streak} days"
    if bonus:
        msg += "\n7-DAY BONUS! +50 Points"
    await update.message.reply_text(msg)

async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_callback = bool(update.callback_query)
    if is_callback:
        if update.effective_chat.type in ["group", "supergroup"]:
            await update.callback_query.answer("Please use DM @GovernWatchBot", show_alert=True)
            return
    else:
        if await check_group(update):
            return
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    text = "GOVERN TASKS:\n\n"
    kb = []
    for t in TASKS:
        claimed = is_task_claimed(user.id, t["id"])
        done_ok = check_task(user.id, t["id"], row)
        if claimed:
            status = "✅ CLAIMED"
        elif done_ok:
            status = "🟢 READY - Click Claim"
        else:
            status = "⏳ NOT DONE"
        extra = ""
        if t["id"] == "first_raid":
            extra = f" Raids: {row[9] or 0}/1"
        if t["id"] == "raid_10":
            extra = f" Raids: {row[9] or 0}/10"
        if t["id"] == "invite_3":
            extra = f" Invited: {get_invite_count(user.id)}/3"
        if t["id"] == "daily_7":
            extra = f" Streak: {row[4] or 0}/7"
        text += f"{t['title']} - {t['points']} pts - {status}{extra}\n{t['desc']}\n\n"
        # Show Claim button ONLY if done and NOT claimed - prevents double claim
        if done_ok and not claimed:
            kb.append([InlineKeyboardButton(f"Claim {t['title']} +{t['points']} pts", callback_data="claim_" + t["id"])])
    # Show Join button ONLY if not joined yet
    if not row[3] and not row[10]:
        kb.append([InlineKeyboardButton("Join Group", url=GROUP_LINK)])
    if is_callback:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb) if kb else None)

async def handle_claim(user, task_id, reply_func):
    row = get_user(user.id)
    if not row:
        await reply_func("Type /verify first.")
        return
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        await reply_func("Invalid task ID.")
        return
    # DOUBLE CLAIM PROTECTION - Most important check
    if is_task_claimed(user.id, task_id):
        await reply_func(f"Already claimed: {task['title']} ✅\nYou cannot claim it twice.")
        return
    if not check_task(user.id, task_id, row):
        await reply_func("Task not done yet: " + task["title"])
        return
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO claimed_tasks VALUES (?,?)", (user.id, task_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        await reply_func("Already claimed. ✅")
        return
    conn.close()
    add_points(user.id, task["points"])
    await reply_func(f"Claimed {task['title']}! +{task['points']} points! 🎉\nYour total: {get_user(user.id)[2]} pts")

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /claim <task_id>")
        return
    await handle_claim(update.effective_user, context.args[0], update.message.reply_text)

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    row = get_user(update.effective_user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    await update.message.reply_text(f"Points: {row[2]} ⭐\nBadge: {get_badge(row[2])}\nRank: #{get_rank(update.effective_user.id)}\nApproved Raids: {row[9] or 0}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    bot_username = context.bot.username or "GovernWatchBot"
    kb = []
    kb.append([InlineKeyboardButton("🎯 Tasks", callback_data="tasks")])
    kb.append([InlineKeyboardButton("🔥 Active Raid", callback_data="raid")])
    # Join button ONLY if not joined
    if not row[3] and not row[10]:
        kb.append([InlineKeyboardButton("Join Group", url=GROUP_LINK)])
    kb.append([InlineKeyboardButton("Follow on X", url=X_LINK)])
    txt = f"Profile: {user.first_name}\nPoints: {row[2]} ⭐\nBadge: {get_badge(row[2])}\nRank: #{get_rank(user.id)}\nStreak: {row[4]} days\nApproved Raids: {row[9] or 0}\nInvited: {get_invite_count(user.id)} friends\n\nYour Invite Link:\nhttps://t.me/{bot_username}?start={user.id}\n\nShare it, get +10 points per person!"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def rank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    row = get_user(update.effective_user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    await update.message.reply_text(f"Your Rank: #{get_rank(update.effective_user.id)}\nPoints: {row[2]} ⭐")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_callback = bool(update.callback_query)
    if is_callback:
        if update.effective_chat.type in ["group", "supergroup"]:
            await update.callback_query.answer("Please use DM @GovernWatchBot", show_alert=True)
            return
    else:
        if await check_group(update):
            return
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        msg = "No citizens yet. /verify"
        if is_callback:
            await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return
    txt = "GOVERN Leaderboard 🏆:\n\n"
    for i, r in enumerate(rows, 1):
        txt += f"{i}. {r[0] or 'User'} - {r[1]} pts\n"
    if is_callback:
        await update.callback_query.message.reply_text(txt)
    else:
        await update.message.reply_text(txt)

async def newraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /newraid <tweet link>")
        return
    link = " ".join(context.args)
    save_raid(link)
    await update.message.reply_text("New Raid Set!\n" + link)

async def setraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await newraid(update, context)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if update.effective_chat.type in ["group", "supergroup"]:
        await q.answer("Please use DM @GovernWatchBot", show_alert=True)
        return
    data = q.data
    user = update.effective_user
    if data == "verify":
        await verify(update, context)
    elif data == "tasks":
        await tasks_cmd(update, context)
    elif data == "profile":
        await profile(update, context)
    elif data == "leaderboard":
        await leaderboard(update, context)
    elif data == "raid":
        await raid(update, context)
    elif data.startswith("claim_"):
        tid = data.replace("claim_", "")
        async def reply_func(text):
            await q.message.reply_text(text)
        await handle_claim(user, tid, reply_func)
    elif data.startswith("approve_"):
        if user.id != ADMIN_ID:
            await q.message.reply_text("Admin only.")
            return
        target_id = int(data.replace("approve_", ""))
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("UPDATE users SET points=points+10, raid_count=raid_count+1 WHERE user_id=?", (target_id,))
        conn.commit()
        conn.close()
        # Remove from pending
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("DELETE FROM pending WHERE user_id=?", (target_id,))
        conn.commit()
        conn.close()
        await q.message.reply_text(f"Approved +10 to {target_id} ✅")
        try:
            await context.bot.send_message(chat_id=target_id, text="Your Raid Approved! +10 points! 🔥\nCheck /profile")
        except:
            pass
    elif data.startswith("reject_"):
        if user.id != ADMIN_ID:
            return
        target_id = int(data.replace("reject_", ""))
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("DELETE FROM pending WHERE user_id=?", (target_id,))
        conn.commit()
        conn.close()
        await q.message.reply_text(f"Rejected {target_id}")
        try:
            await context.bot.send_message(chat_id=target_id, text="Your Raid was rejected. Please try again with a clear screenshot.")
        except:
            pass

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    txt = "GOVERN Commands:\n\n/start - Start\n/verify - Verify\n/profile - Your profile\n/tasks - Tasks\n/daily - Daily bonus +10\n/raid - Active raid\n/connect @username - Connect X\n/points - Points\n/leaderboard - Top 10\n/rank - Your rank"
    await update.message.reply_text(txt)

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("verify", verify))
    app_bot.add_handler(CommandHandler("join", join_cmd))
    app_bot.add_handler(CommandHandler("connect", connect))
    app_bot.add_handler(CommandHandler("raid", raid))
    app_bot.add_handler(CommandHandler("newraid", newraid))
    app_bot.add_handler(CommandHandler("setraid", setraid))
    app_bot.add_handler(CommandHandler("done", done))
    app_bot.add_handler(CommandHandler("daily", daily))
    app_bot.add_handler(CommandHandler("tasks", tasks_cmd))
    app_bot.add_handler(CommandHandler("claim", claim))
    app_bot.add_handler(CommandHandler("points", points))
    app_bot.add_handler(CommandHandler("profile", profile))
    app_bot.add_handler(CommandHandler("rank", rank_cmd))
    app_bot.add_handler(CommandHandler("leaderboard", leaderboard))
    app_bot.add_handler(CommandHandler("help", help_cmd))
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("Bot running...", flush=True)
    app_bot.run_polling()

if __name__ == "__main__":
    main()
