import os
import sqlite3
import logging
import time
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from flask import Flask
import threading

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "-1004325278182"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
X_HANDLE = "@Governbull"
X_LINK = "https://x.com/Governbull"
TELEGRAM_GROUP = "@governpublic"
RAID_LINK = os.getenv("RAID_LINK", "https://x.com/Governbull")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
DB = "govern.db"

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
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT id, link FROM raids WHERE active=1 ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

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
    {"id": "connect_x", "title": "Connect Your X", "points": 10, "desc": "Use /connect your_x_username"},
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
    # Referral tracking: if /start <inviter_id>
    if context.args:
        try:
            inviter = int(context.args[0])
            if inviter != user.id:
                row = get_user(user.id)
                # Only count if user is new (0 points and not verified) - simplified: count once via invites
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
        "HOW TO RAID - 4 STEPS:\n"
        "Step 1: /connect - Connect your X FIRST (Only Once)\n"
        "Step 2: /raid - Click RAID Link\n"
        "Step 3: Go to X, Like, Retweet, Reply with YOUR OWN WORDS\n"
        "Step 4: Come back and click DONE / /done\n\n"
        "COMMANDS:\n"
        "/verify - Verify Telegram +20\n"
        "/connect - Connect X\n"
        "/raid - Current Raid\n"
        "/done - Claim Raid +50\n"
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
        await update.message.reply_text(
            "CONNECT YOUR X FIRST (Only Once)\n\n"
            "Type:\n"
            "/connect your_x_username\n\n"
            "Example:\n"
            "/connect Ukona123",
            parse_mode="Markdown"
        )
        return
    x_user = context.args[0].replace("@", "").strip()
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET x_username=? WHERE user_id=?", (x_user, user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(
        f"X Connected!\n\n"
        f"Telegram: @{user.username or user.first_name}\n"
        f"X: @{x_user}\n\n"
        f"Now you can raid! Type /raid"
    )

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row or not row[2]:
        await update.message.reply_text(
            "CONNECT FIRST OR YOUR WORK WILL NOT COUNT\n\n"
            "Connect your X first:\n"
            "/connect your_x_username\n"
            "Then type /raid again.",
            parse_mode="Markdown"
        )
        return
    active = get_active_raid()
    link = active[1] if active else RAID_LINK
    keyboard = [
        [InlineKeyboardButton("CLICK RAID LINK - GO TO X", url=link)],
        [InlineKeyboardButton("DONE - I DID IT", callback_data="raid_done")]
    ]
    await update.message.reply_text(
        "$GOVERN RAID IS LIVE!\n\n"
        "Step 2: Click RAID Link\n"
        "Step 3: On X - Like, Retweet, Reply with YOUR OWN WORDS\n"
        "Example: 'This is real governance, WE GOVERN!' - use your own style\n"
        "Step 4: Come back and click DONE\n\n"
        "Follow: https://x.com/Governbull\n"
        "PUBLIC GOAL: Likes 100% | Retweets 100% | Replies 100%\n"
        "WORK TOGETHER - STAY ACTIVE",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def myraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
