import os
import sqlite3
import time
import threading
import traceback
from datetime import date
from flask import Flask
from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler
from telegram.ext import CallbackQueryHandler
from telegram.ext import ContextTypes
from telegram.ext import filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DB = "govern.db"
RAID_FILE = "raid.txt"
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

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_daily TEXT, last_raid TEXT, invited_by INTEGER, x_username TEXT, raid_count INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS raids (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT, active INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS claimed_tasks (user_id INTEGER, task_id TEXT, PRIMARY KEY(user_id, task_id))")
    c.execute("CREATE TABLE IF NOT EXISTS pending (user_id INTEGER, photo_id TEXT)")
    try:
        c.execute("ALTER TABLE users ADD COLUMN x_username TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN raid_count INTEGER DEFAULT 0")
    except:
        pass
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
        txt = "Please use DM for all bot commands.\n"
        txt += "Go to @GovernWatchBot and send your command there.\n"
        txt += "After you finish, you can share your badge here."
        try:
            await update.message.reply_text(txt)
        except:
            pass
        return True
    return False

TASKS = []
TASKS.append({"id": "join_tg", "title": "Join Telegram Group", "points": 20, "desc": "Join Group", "url": GROUP_LINK, "url_text": "Join Group"})
TASKS.append({"id": "connect_x", "title": "Connect Your X", "points": 10, "desc": "Use /connect @your_username", "url": None, "url_text": None})
TASKS.append({"id": "follow_x", "title": "Follow on X", "points": 20, "desc": "Follow us on X", "url": X_LINK, "url_text": "Follow on X"})
TASKS.append({"id": "first_raid", "title": "Complete First Raid", "points": 50, "desc": "Do 1 raid and get approval", "url": None, "url_text": None})
TASKS.append({"id": "raid_10", "title": "Complete 10 Raids", "points": 200, "desc": "Do 10 raids with approval", "url": None, "url_text": None})
TASKS.append({"id": "invite_3", "title": "Invite 3 Friends", "points": 30, "desc": "Share your link from /invite", "url": None, "url_text": None})
TASKS.append({"id": "daily_7", "title": "7-Day Daily Streak", "points": 50, "desc": "Use /daily 7 days in a row", "url": None, "url_text": None})

def is_task_claimed(uid, tid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT 1 FROM claimed_tasks WHERE user_id=? AND task_id=?", (uid, tid))
    r = c.fetchone()
    conn.close()
    return bool(r)

def check_task(uid, tid, row):
    if tid == "join_tg":
        return True
    if tid == "connect_x":
        return bool(row[8])
    if tid == "follow_x":
        return True
    if tid == "first_raid":
        return (row[9] or 0) >= 1
    if tid == "raid_10":
        return (row[9] or 0) >= 10
    if tid == "invite_3":
        return get_invite_count(uid) >= 3
    if tid == "daily_7":
        return (row[4] or 0) >= 7
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    user = update.effective_user
    args = context.args
    invited_by = None
    if args and args[0].isdigit():
        invited_by = int(args[0])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    exists = c.fetchone()
    if not exists:
        c.execute("INSERT INTO users (user_id, username, invited_by) VALUES (?,?,?)", (user.id, user.username or user.first_name, invited_by))
        conn.commit()
        if invited_by and invited_by != user.id:
            c.execute("UPDATE users SET points=points+10 WHERE user_id=?", (invited_by,))
            conn.commit()
            try:
                msg = "New user joined with your link! +10 points!"
                await context.bot.send_message(chat_id=invited_by, text=msg)
            except:
                pass
    conn.close()
    kb = []
    kb.append([InlineKeyboardButton("Verify", callback_data="verify")])
    kb.append([InlineKeyboardButton("Join Group", url=GROUP_LINK)])
    kb.append([InlineKeyboardButton("Follow on X", url=X_LINK)])
    kb.append([InlineKeyboardButton("Leaderboard", callback_data="leaderboard")])
    kb.append([InlineKeyboardButton("Tasks", callback_data="tasks")])
    txt = "Welcome to GOVERN!\n"
    txt += "Use /verify to start earning.\n"
    txt += "Use /tasks to see tasks.\n"
    txt += "Use /raid for active raid.\n"
    txt += "Use /daily for daily bonus.\n"
    txt += "Use /join to join our group."
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        if update.effective_chat.type in ["group", "supergroup"]:
            await update.callback_query.answer("Please use DM @GovernWatchBot", show_alert=True)
            return
    else:
        if await check_group(update):
            return
    user = update.effective_user
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET verified=1 WHERE user_id=?", (user.id,))
    if c.rowcount == 0:
        c.execute("INSERT INTO users (user_id, username, verified) VALUES (?,?,1)", (user.id, user.username or user.first_name))
    conn.commit()
    conn.close()
    kb = []
    kb.append([InlineKeyboardButton("Join Group", url=GROUP_LINK)])
    kb.append([InlineKeyboardButton("Follow on X", url=X_LINK)])
    kb.append([InlineKeyboardButton("Tasks", callback_data="tasks")])
    txt = "Verified! You are now a CITIZEN.\n"
    txt += "Next: Join Group + Follow on X, then do /tasks"
    if update.callback_query:
        await update.callback_query.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def join_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    kb = []
    kb.append([InlineKeyboardButton("Join GOVERN Group", url=GROUP_LINK)])
    kb.append([InlineKeyboardButton("Follow on X", url=X_LINK)])
    txt = "Join our community:\n"
    txt += "Telegram Group: " + GROUP_LINK + "\n"
    txt += "X: " + X_LINK + "\n"
    txt += "After joining, go to /tasks and Claim +20 points!"
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
        c.execute("INSERT INTO users (user_id, username, x_username) VALUES (?,?,?)", (user.id, user.username or user.first_name, x_user))
    conn.commit()
    conn.close()
    txt = "X connected: @" + x_user + "\n"
    txt += "Now go to /tasks and Claim +10 points!"
    await update.message.reply_text(txt)

async def raid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    r = get_active_raid()
    if not r:
        await update.message.reply_text("No active raid yet. Wait for admin to set one.")
        return
    kb = [[InlineKeyboardButton("Open Tweet on X", url=r[1])]]
    txt = "ACTIVE RAID:\n\n" + r[1] + "\n\n"
    txt += "1. Like + Repost + Comment on X\n"
    txt += "2. Take a screenshot\n"
    txt += "3. Send the screenshot here\n"
    txt += "Admin will approve and give you +10 points."
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
        uname = user.username or ""
        cap = "New Raid Proof\nFrom: " + user.first_name + " @" + uname + "\nID: " + str(user.id)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=cap, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        print("Could not send to admin")
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
        await update.message.reply_text("Already claimed today!")
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
    msg = "DAILY CHECK-IN!\n+10 Points\nStreak: " + str(streak) + " days"
    if bonus:
        msg += "\n7-DAY BONUS! +50 Points"
    await update.message.reply_text(msg)

async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
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
            status = "CLAIMED"
        elif done_ok:
            status = "READY - Click Claim"
        else:
            status = "NOT DONE"
        extra = ""
        if t["id"] == "first_raid":
            extra = " Raids: " + str(row[9] or 0) + "/1"
        if t["id"] == "raid_10":
            extra = " Raids: " + str(row[9] or 0) + "/10"
        if t["id"] == "invite_3":
            extra = " Invited: " + str(get_invite_count(user.id)) + "/3"
        if t["id"] == "daily_7":
            extra = " Streak: " + str(row[4] or 0) + "/7"
        text += t["title"] + " - " + str(t["points"]) + " pts - " + status + extra + "\n"
        text += t["desc"] + "\n\n"
        if t["url"]:
            kb.append([InlineKeyboardButton(t["url_text"], url=t["url"])])
        if done_ok and not claimed:
            btn = "Claim " + t["title"] + " +" + str(t["points"]) + " pts"
            kb.append([InlineKeyboardButton(btn, callback_data="claim_" + t["id"])])
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb) if kb else None)

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /claim <task_id>")
        return
    await handle_claim(update.effective_user, context.args[0], update.message.reply_text)

async def handle_claim(user, task_id, reply_func):
    row = get_user(user.id)
    if not row:
        await reply_func("Type /verify first.")
        return
    task = None
    for t in TASKS:
        if t["id"] == task_id:
            task = t
    if not task:
        await reply_func("Invalid task ID.")
        return
    if is_task_claimed(user.id, task_id):
        await reply_func("Already claimed.")
        return
    if not check_task(user.id, task_id, row):
        await reply_func("Task not done yet: " + task["title"])
        return
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO claimed_tasks VALUES (?,?)", (user.id, task_id))
    conn.commit()
    conn.close()
    add_points(user.id, task["points"])
    await reply_func("Claimed " + task["title"] + "! +" + str(task["points"]) + " points!")

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    row = get_user(update.effective_user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    pts = row[2]
    badge = get_badge(pts)
    txt = "Points: " + str(pts) + "\n"
    txt += "Badge: " + badge + "\n"
    txt += "Rank: #" + str(get_rank(update.effective_user.id)) + "\n"
    txt += "Approved Raids: " + str(row[9] or 0)
    await update.message.reply_text(txt)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    pts = row[2]
    badge = get_badge(pts)
    bot_username = context.bot.username or "GovernWatchBot"
    kb = []
    kb.append([InlineKeyboardButton("Join Group", url=GROUP_LINK)])
    kb.append([InlineKeyboardButton("Follow on X", url=X_LINK)])
    txt = "Profile: " + user.first_name + "\n"
    txt += "Points: " + str(pts) + "\n"
    txt += "Badge: " + badge + "\n"
    txt += "Rank: #" + str(get_rank(user.id)) + "\n"
    txt += "Streak: " + str(row[4]) + " days\n"
    txt += "Approved Raids: " + str(row[9] or 0) + "\n"
    txt += "Invited: " + str(get_invite_count(user.id)) + " friends\n\n"
    txt += "Your Invite Link:\n"
    txt += "https://t.me/" + bot_username + "?start=" + str(user.id) + "\n\n"
    txt += "Share it, get +10 points per person!"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def rank_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update):
        return
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Type /verify first.")
        return
    txt = "Your Rank: #" + str(get_rank(user.id)) + "\n"
    txt += "Points: " + str(row[2])
    await update.message.reply_text(txt)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
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
        if update.callback_query:
            await update.callback_query.message.reply_text("No citizens yet. /verify")
        else:
            await update.message.reply_text("No citizens yet. /verify")
        return
    txt = "GOVERN Leaderboard:\n\n"
    for i, r in enumerate(rows, 1):
        txt += str(i) + ". " + str(r[0] or "User") + " - " + str(r[1]) + " pts\n"
    if update.callback_query:
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
    if q.data == "verify":
        await verify(update, context)
    elif q.data == "leaderboard":
        await leaderboard(update, context)
    elif q.data == "tasks":
        await tasks_cmd(update, context)
    elif q.data.startswith("claim_"):
        tid = q.data.replace("claim_", "")
        await handle_claim(q.from_user, tid, q.message.reply_text)
    elif q.data.startswith("approve_"):
        if q.from_user.id != ADMIN_ID:
            await q.message.reply_text("Admin only.")
            return
        uid = int(q.data.replace("approve_", ""))
        add_points(uid, 10)
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("UPDATE users SET raid_count=raid_count+1 WHERE user_id=?", (uid,))
        c.execute("DELETE FROM pending WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        await q.message.reply_text("Approved! User " + str(uid) + " got +10 points.")
        try:
            await context.bot.send_message(chat_id=uid, text="Raid approved! You received +10 points.")
        except:
            pass
    elif q.data.startswith("reject_"):
        if q.from_user.id != ADMIN_ID:
            await q.message.reply_text("Admin only.")
            return
        uid = int(q.data.replace("reject_", ""))
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("DELETE FROM pending WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        await q.message.reply_text("Rejected user " + str(uid) + ".")
        try:
            await context.bot.send_message(chat_id=uid, text="Your raid screenshot was not approved. Please try again.")
        except:
            pass

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        return
    if update.message and update.message.text:
        await update.message.reply_text("Use /start to see menu, /raid for raid, /daily for bonus, /join to join group.")

def main():
    print("STARTING BOT", flush=True)
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN IS MISSING", flush=True)
        while True:
            time.sleep(60)
    try:
        init_db()
        threading.Thread(target=run_flask, daemon=True).start()
        b = ApplicationBuilder().token(BOT_TOKEN).build()
        b.add_handler(CommandHandler("start", start))
        b.add_handler(CommandHandler("help", start))
        b.add_handler(CommandHandler("verify", verify))
        b.add_handler(CommandHandler("join", join_cmd))
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
        b.add_handler(CallbackQueryHandler(button_handler))
        b.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        b.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all))
        print("Bot Started", flush=True)
        b.run_polling()
    except Exception as e:
        print("FATAL ERROR", flush=True)
        print(e, flush=True)
        traceback.print_exc()
        while True:
            time.sleep(60)

if __name__ == "__main__":
    main()
