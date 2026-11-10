import os
import sqlite3
import logging
import time
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from flask import Flask
import threading

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "-1004325278182"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "1375360019"))
X_LINK = "https://x.com/Governbull"
RAID_LINK = os.getenv("RAID_LINK", "https://x.com/Governbull")
RAID_FILE = "current_raid.txt"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
DB = "govern.db"

# Anti-cheat storage
raid_start_time = {}
pending_raid_proof = {}

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, x_username TEXT DEFAULT '', raids INTEGER DEFAULT 0, invites INTEGER DEFAULT 0, last_daily TEXT DEFAULT '', daily_streak INTEGER DEFAULT 0, last_raid_time INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS raids
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS claimed_tasks
                 (user_id INTEGER, task_id TEXT, PRIMARY KEY (user_id, task_id))''')
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT points, verified, x_username, raids, invites, last_daily, daily_streak, last_raid_time FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    conn.close()
    return row

def add_user(uid, uname):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, points, verified) VALUES (?,?,0,0)", (uid, uname))
    conn.commit()
    conn.close()

def add_points(uid, amount):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (amount, uid))
    conn.commit()
    conn.close()

def is_task_claimed(uid, task_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM claimed_tasks WHERE user_id=? AND task_id=?", (uid, task_id))
    row = c.fetchone()
    conn.close()
    return row is not None

def claim_task_db(uid, task_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO claimed_tasks (user_id, task_id) VALUES (?,?)", (uid, task_id))
    conn.commit()
    conn.close()

def set_verified(uid, uname):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)", (uid, uname))
    c.execute("SELECT points, verified FROM users WHERE user_id=?", (uid,))
    pts, ver = c.fetchone()
    if ver == 1:
        conn.close()
        return False, pts
    new = pts + 20
    c.execute("UPDATE users SET points=?, verified=1, username=? WHERE user_id=?", (new, uname, uid))
    conn.commit()
    conn.close()
    return True, new

def get_active_raid():
    # 1. Try file first - survives restart
    try:
        with open(RAID_FILE, "r") as f:
            link = f.read().strip()
            if link:
                return (0, link)
    except:
        pass
    # 2. Try DB
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, link FROM raids WHERE active=1 ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def save_raid_link(link):
    with open(RAID_FILE, "w") as f:
        f.write(link)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE raids SET active=0")
    c.execute("INSERT INTO raids (link, active) VALUES (?,1)", (link,))
    conn.commit()
    conn.close()

def get_rank(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users ORDER BY points DESC")
    rows = c.fetchall()
    conn.close()
    for i, (u,) in enumerate(rows, 1):
        if u == uid:
            return i
    return 0

TASKS = [
    {"id": "join_tg", "title": "Join Telegram Group", "points": 20, "desc": "Join @governpublic and /verify"},
    {"id": "connect_x", "title": "Connect Your X", "points": 10, "desc": "Use /connect"},
    {"id": "follow_x", "title": "Follow @Governbull on X", "points": 20, "desc": "Follow https://x.com/Governbull then claim"},
    {"id": "first_raid", "title": "Complete First Raid", "points": 50, "desc": "Do /raid then DONE"},
    {"id": "raid_5", "title": "Complete 5 Raids", "points": 100, "desc": "Do 5 raids total"},
    {"id": "raid_10", "title": "Complete 10 Raids", "points": 200, "desc": "Do 10 raids total"},
    {"id": "invite_3", "title": "Invite 3 Friends", "points": 30, "desc": "Share your invite link, 3 friends must /verify"},
    {"id": "daily_7", "title": "7-Day Daily Streak", "points": 50, "desc": "Use /daily 7 days in a row"},
]

def check_task_condition(uid, task_id, row):
    if row is None:
        return False
    pts, ver, x, raids, invites, last_daily, streak, last_raid = row
    if task_id == "join_tg":
        return ver == 1
    if task_id == "connect_x":
        return bool(x)
    if task_id == "follow_x":
        return bool(x)
    if task_id == "first_raid":
        return raids >= 1
    if task_id == "raid_5":
        return raids >= 5
    if task_id == "raid_10":
        return raids >= 10
    if task_id == "invite_3":
        return invites >= 3
    if task_id == "daily_7":
        return streak >= 7
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username or user.first_name)
    if context.args:
        try:
            inviter = int(context.args[0])
            if inviter != user.id:
                conn = sqlite3.connect(DB)
                c = conn.cursor()
                c.execute("UPDATE users SET invites = invites + 1 WHERE user_id=?", (inviter,))
                conn.commit()
                conn.close()
        except:
            pass
    await update.message.reply_text(
        "Welcome to $GOVERN Watch Bot!\n\n"
        "CONNECT FIRST OR YOUR WORK WILL NOT COUNT\n\n"
        "HOW TO RAID:\n"
        "Step 1: /connect - Connect your X FIRST (Only Once)\n"
        "Step 2: /raid - Click RAID Link\n"
        "Step 3: Go to X, Like, Retweet, Reply with YOUR OWN WORDS\n"
        "Step 4: Wait 2 Minutes, Click DONE, Send Screenshot\n"
        "Step 5: Wait for Admin Approval - +50 Points\n\n"
        "COMMANDS:\n"
        "/verify - Verify Telegram +20\n"
        "/connect - Connect X\n"
        "/raid - Current Raid\n"
        "/done - Claim Raid (Old Method)\n"
        "/daily - Daily Check-in +10\n"
        "/tasks - All Tasks\n"
        "/claim <task_id> - Claim Task Reward\n"
        "/invite - Your Invite Link\n"
        "/profile - Your Profile\n"
        "/points - Your Points\n"
        "/rank - Your Rank\n"
        "/leaderboard - Top Citizens\n"
        "/myraid - Your Raid Stats\n\n"
        "Follow us: https://x.com/Governbull\n"
        "Group: @governpublic"
    )

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    uname = user.username or user.first_name or "Citizen"
    add_user(user.id, uname)
    if chat.id == GROUP_ID:
        ok, pts = set_verified(user.id, uname)
        if not ok:
            await update.message.reply_text(f"Already Verified! You have {pts} Points.")
        else:
            await update.message.reply_text(f"Verified! +20 Points\nWelcome Citizen @{uname}!\nTotal: {pts} Points")
        return
    try:
        m = await context.bot.get_chat_member(GROUP_ID, user.id)
        if m.status in ['member', 'administrator', 'creator']:
            ok, pts = set_verified(user.id, uname)
            if ok:
                await update.message.reply_text(f"Verified! +20 Points\nTotal: {pts}")
            else:
                await update.message.reply_text(f"Already Verified! {pts} Points")
        else:
            await update.message.reply_text("Join @governpublic first, then /verify")
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Please type /verify INSIDE @governpublic group")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username or user.first_name)
    if not context.args:
        await update.message.reply_text("CONNECT YOUR X FIRST (Only Once)\n\nType:\n/connect your_x_username")
        return
    x_user = context.args[0].replace("@", "").strip()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET x_username=? WHERE user_id=?", (x_user, user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"X Connected!\n\nTelegram: @{user.username or user.first_name}\nX: @{x_user}\n\nNow you can raid! Type /raid")

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row or not row[2]:
        await update.message.reply_text("CONNECT FIRST OR YOUR WORK WILL NOT COUNT\n\nConnect your X first:\n/connect your_x_username\nThen type /raid again.")
        return
    # Start 2-minute timer
    raid_start_time[user.id] = time.time()
    active = get_active_raid()
    link = active[1] if active else RAID_LINK
    keyboard = [
        [InlineKeyboardButton("CLICK RAID LINK - GO TO X", url=link)],
        [InlineKeyboardButton("DONE - I DID IT", callback_data="raid_done")]
    ]
    await update.message.reply_text(
        "$GOVERN RAID IS LIVE!\n\n"
        "Step 1: Click RAID Link\n"
        "Step 2: On X - Like, Retweet, Reply with YOUR OWN WORDS\n"
        "Step 3: WAIT 2 MINUTES - Do not click DONE early\n"
        "Step 4: Click DONE, then send your Screenshot\n"
        "Step 5: Wait for Admin Approval - +50 Points\n\n"
        "Follow: https://x.com/Governbull\n"
        "PUBLIC GOAL: Likes 100% | Retweets 100% | Replies 100%\n"
        "WORK TOGETHER - STAY ACTIVE",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def myraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    pts, ver, x, raids, invites, last_daily, streak, last_raid = row
    await update.message.reply_text(f"YOUR RAID STATS\n\nX: @{x or 'Not Connected'}\nRaids Completed: {raids}\nPoints: {pts}\nRank: #{get_rank(user.id)}")

async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Old direct claim - now redirects to new secure flow
    await update.message.reply_text("Please use /raid and click DONE button, then send Screenshot for approval.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "raid_done":
        user_id = q.from_user.id
        row = get_user(user_id)
        if not row or not row[2]:
            await q.message.reply_text("Connect X first! Type /connect your_x_username")
            return
        # Check 2-minute rule
        start = raid_start_time.get(user_id, 0)
        passed = time.time() - start
        if passed < 120:
            left = int(120 - passed)
            await q.answer(f"Please wait! {left} seconds left. Go and do the raid properly!", show_alert=True)
            return
        # Check 1-hour cooldown
        pts, ver, x, raids, invites, last_daily, streak, last_raid = row
        now = int(time.time())
        if now - last_raid < 3600 and last_raid != 0:
            mins = (3600 - (now - last_raid)) // 60
            await q.message.reply_text(f"Wait {mins} minutes before next Raid claim.\nAnti-spam cooldown: 1 Raid per hour.")
            return
        pending_raid_proof[user_id] = True
        await q.message.reply_text(
            "2 Minutes Completed!\n\n"
            "Now send a SCREENSHOT of your Like + Repost + Reply on X.\n"
            "Without Screenshot, you will NOT get Points."
        )
    elif q.data.startswith("claim_"):
        task_id = q.data.replace("claim_", "")
        await handle_claim(q.from_user, task_id, q.edit_message_text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in pending_raid_proof:
        return
    # Forward screenshot to Admin
    try:
        await context.bot.forward_message(chat_id=ADMIN_ID, from_chat_id=update.effective_chat.id, message_id=update.message.message_id)
        row = get_user(user_id)
        x_name = row[2] if row else "Unknown"
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"NEW RAID PROOF\nUser: @{update.effective_user.username or update.effective_user.first_name}\nID: {user_id}\nX: @{x_name}\n\nTo Approve: /approve {user_id}\nTo Reject: /reject {user_id}"
        )
        await update.message.reply_text("Screenshot sent to Admin. Wait for approval. You will get +50 Points if approved.")
        del pending_raid_proof[user_id]
    except Exception as e:
        logger.error(e)
        await update.message.reply_text("Error sending screenshot. Try again.")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve USER_ID")
        return
    try:
        target_id = int(context.args[0])
    except:
        return
    row = get_user(target_id)
    if not row:
        return
    pts, ver, x, raids, invites, last_daily, streak, last_raid = row
    now = int(time.time())
    new_pts = pts + 50
    new_raids = raids + 1
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET points=?, raids=?, last_raid_time=? WHERE user_id=?", (new_pts, new_raids, now, target_id))
    conn.commit()
    conn.close()
    try:
        await context.bot.send_message(chat_id=target_id, text=f"RAID APPROVED!\n\nX: @{x}\n+50 Points for Raid!\nTotal Raids: {new_raids}\nTotal Points: {new_pts}\n\nWE GOVERN!")
    except:
        pass
    await update.message.reply_text(f"Approved! User {target_id} got +50 Points. Total Raids: {new_raids}")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /reject USER_ID")
        return
    try:
        target_id = int(context.args[0])
    except:
        return
    try:
        await context.bot.send_message(chat_id=target_id, text="RAID REJECTED.\nYour Screenshot was not valid. Please do the raid properly - Like, Repost, Reply with your own words - and try again.")
    except:
        pass
    await update.message.reply_text(f"Rejected user {target_id}.")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user.id, user.username or user.first_name)
    row = get_user(user.id)
    pts, ver, x, raids, invites, last_daily, streak, last_raid = row
    today = date.today().isoformat()
    if last_daily == today:
        await update.message.reply_text(f"Already claimed today! Streak: {streak} days.\nCome back tomorrow.")
        return
    try:
        last_d = date.fromisoformat(last_daily) if last_daily else None
        if last_d and (date.today() - last_d).days == 1:
            new_streak = streak + 1
        else:
            new_streak = 1
    except:
        new_streak = 1
    bonus = 50 if new_streak == 7 else 0
    reward = 10 + bonus
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ?, last_daily=?, daily_streak=? WHERE user_id=?", (reward, today, new_streak, user.id))
    conn.commit()
    conn.close()
    msg = f"DAILY CHECK-IN!\n\n+10 Points\nStreak: {new_streak} days\nTotal: {pts + reward} Points"
    if bonus:
        msg += "\n\n7-DAY BONUS! +50 Extra Points!"
    await update.message.reply_text(msg)

async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    keyboard = []
    text = "$GOVERN TASKS\n\n"
    for t in TASKS:
        claimed = is_task_claimed(user.id, t["id"])
        done = check_task_condition(user.id, t["id"], row)
        if claimed:
            status = "CLAIMED"
        elif done:
            status = "READY - Click Claim"
            keyboard.append([InlineKeyboardButton(f"Claim {t['title']} +{t['points']}", callback_data=f"claim_{t['id']}")])
        else:
            status = "NOT DONE"
        text += f"{t['title']} - +{t['points']} - {status}\n{t['desc']}\nID: {t['id']}\n\n"
    text += "To claim via command: /claim <task_id>\nExample: /claim follow_x"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)

async def claim_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: /claim <task_id>\nSee /tasks for IDs")
        return
    await handle_claim(user, context.args[0], update.message.reply_text)

async def handle_claim(user, task_id, reply_func):
    row = get_user(user.id)
    if not row:
        await reply_func("Type /verify first.")
        return
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        await reply_func("Invalid task ID. See /tasks")
        return
    if is_task_claimed(user.id, task_id):
        await reply_func("Already claimed this task.")
        return
    if not check_task_condition(user.id, task_id, row):
        await reply_func(f"Task not completed yet.\n{task['title']}: {task['desc']}")
        return
    claim_task_db(user.id, task_id)
    add_points(user.id, task["points"])
    new_row = get_user(user.id)
    await reply_func(f"TASK COMPLETED!\n\n{task['title']}\n+{task['points']} Points\nTotal: {new_row[0]} Points")

async def invite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    bot_username = context.bot.username
    link = f"https://t.me/{bot_username}?start={user.id}"
    await update.message.reply_text(f"YOUR INVITE LINK:\n\n{link}\n\nShare it. When 3 friends join and /verify, you complete the Invite Task (+30).\nYour Invites: {row[4]}")

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_user(update.effective_user.id)
    if not row:
        await update.message.reply_text("0 Points. /verify first.")
        return
    await update.message.reply_text(f"Points: {row[0]}\nX: @{row[2] or 'Not connected'}\nRaids: {row[3]}\nInvites: {row[4]}\nStreak: {row[6]} days")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("/verify first.")
        return
    pts, ver, x, raids, invites, last_daily, streak, last_raid = row
    rank = get_rank(user.id)
    status = "Verified" if ver == 1 else "Not Verified"
    badge = "GOVERNOR" if pts >= 500 else "ELITE" if pts >= 200 else "CHAMPION" if pts >= 100 else "CITIZEN" if pts >= 20 else "NEWCOMER"
    await update.message.r

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT username, points, raids FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("No citizens yet. /verify")
        return
    txt = "$GOVERN Leaderboard\n\n"
    for i, (u, p, r) in enumerate(rows, 1):
        txt += f"{i}. @{u} - {p} pts | {r} raids\n"
    await update.message.reply_text(txt)

async def newraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setraid <x_link>\nExample: /setraid https://x.com/Governbull/status/123456")
        return
    link = context.args[0].strip()
    save_raid_link(link)
    await update.message.reply_text(f"New Raid Set!\n{link}\n\nEveryone who sends /raid will now see this post.")

async def setraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await newraid(update, context)

app = Flask(__name__)

@app.route('/')
def home():
    return "GOVERN Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def main():
    print("=== STARTING BOT ===", flush=True)
    print(f"BOT_TOKEN exists? {bool(BOT_TOKEN)} - Length: {len(BOT_TOKEN)}", flush=True)
    print(f"GROUP_ID: {GROUP_ID}", flush=True)
    print(f"ADMIN_ID: {ADMIN_ID}", flush=True)
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN IS MISSING!", flush=True)
        while True:
            time.sleep(60)
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
        b.add_handler(CommandHandler("done", done_cmd))
        b.add_handler(CommandHandler("myraid", myraid))
        b.add_handler(CommandHandler("daily", daily))
        b.add_handler(CommandHandler("tasks", tasks_cmd))
        b.add_handler(CommandHandler("claim", claim_cmd))
        b.add_handler(CommandHandler("invite", invite_cmd))
        b.add_handler(CommandHandler("points", points))
        b.add_handler(CommandHandler("profile", profile))
        b.add_handler(CommandHandler("myprofile", profile))
        b.add_handler(CommandHandler("rank", rank_cmd))
        b.add_handler(CommandHandler("leaderboard", leaderboard))
        b.add_handler(CommandHandler("newraid", newraid))
        b.add_handler(CommandHandler("setraid", setraid))
        b.add_handler(CommandHandler("approve", approve))
        b.add_handler(CommandHandler("reject", reject))
        b.add_handler(CallbackQueryHandler(button_handler))
        b.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        print("Bot Started...", flush=True)
        b.run_polling()
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        while True:
            time.sleep(60)

if __name__ == "__main__":
    main()
