import os
import logging
from datetime import date
from flask import Flask, request, redirect, session
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ChatMemberStatus
import sqlite3

# ========== SETTINGS ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "Put Your Token Here")
GROUP_USERNAME = "@governpublic"
GROUP_ID = os.getenv("GROUP_ID", "-1004325278182")
GROUP_LINK = "https://t.me/governpublic"
BOT_USERNAME = "GovernWatchBot"
ADMIN_ID = 1375360019
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Govern1234")
DB_PATH = "/data/bot.db" if os.path.exists("/data") else "bot.db"
# ==============================

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "govern-secret-123")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, referrer INTEGER, last_daily TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS verified (user_id INTEGER PRIMARY KEY)")
    return conn

def get_user_points(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def get_rank(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE points > (SELECT points FROM users WHERE user_id=?)", (user_id,))
    rank = cur.fetchone()[0] + 1
    conn.close()
    return rank

def get_referral_count(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE referrer=?", (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

# ===== WEB DASHBOARD =====
@app.route('/')
def home():
    return "Bot is Live! <br><a href='/admin'>Go to Admin Dashboard</a>"

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin')
        return "Wrong Password! <a href='/admin'>Try Again</a>"
    if not session.get('admin'):
        return '''
        <h2>GovernWatch Admin Login</h2>
        <form method="POST"><input type="password" name="password" placeholder="Password" required>
        <button>Login</button></form>
        '''
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(points) FROM users")
    total_users, total_points = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM verified")
    total_verified = cur.fetchone()[0]
    search = request.args.get('search', '')
    if search:
        cur.execute("SELECT user_id, username, points, referrer FROM users WHERE username LIKE ? OR user_id LIKE ? ORDER BY points DESC", (f"%{search}%", f"%{search}%"))
    else:
        cur.execute("SELECT user_id, username, points, referrer FROM users ORDER BY points DESC LIMIT 100")
    users = cur.fetchall()
    conn.close()
    rows = "".join([f"<tr><td>{u[0]}</td><td>@{u[1]}</td><td>{u[2]}</td><td>{u[3] or '-'}</td><td><a href='/admin/add/{u[0]}?pts=10'>+10</a> | <a href='/admin/add/{u[0]}?pts=-10'>-10</a></td></tr>" for u in users])
    return f'''
    <h1>GovernWatch Dashboard</h1>
    <p><b>Total Users:</b> {total_users or 0} | <b>Verified:</b> {total_verified} | <b>Total Points:</b> {total_points or 0}</p>
    <form method="GET"><input name="search" placeholder="Search by Username / ID" value="{search}"><button>Search</button></form>
    <br>
    <form action="/admin/broadcast" method="POST"><input name="msg" placeholder="Broadcast message to all users" style="width:300px" required><button>Send to All</button></form>
    <br>
    <table border="1" cellpadding="8"><tr><th>ID</th><th>Username</th><th>Points</th><th>Referrer</th><th>Action</th></tr>{rows}</table>
    <br><a href="/admin/logout">Logout</a>
    '''

@app.route('/admin/add/<int:user_id>')
def admin_add(user_id):
    if not session.get('admin'): return redirect('/admin')
    pts = int(request.args.get('pts', 0))
    conn = get_db()
    conn.execute("UPDATE users SET points = points + ? WHERE user_id=?", (pts, user_id))
    conn.commit(); conn.close()
    return redirect('/admin')

@app.route('/admin/broadcast', methods=['POST'])
def admin_broadcast():
    if not session.get('admin'): return redirect('/admin')
    msg = request.form.get('msg', '')
    with open("broadcast.txt", "w") as f: f.write(msg)
    return "Broadcast saved! It will send on next bot restart. <a href='/admin'>Back</a>"

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin')

# ===== BOT COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer = int(args[0]) if args and args[0].isdigit() else None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username, points) VALUES (?, ?, 0)", (user.id, user.username or user.first_name))
    if referrer and referrer != user.id:
        cur.execute("SELECT * FROM users WHERE user_id=?", (referrer,))
        if cur.fetchone():
            cur.execute("SELECT referrer FROM users WHERE user_id=?", (user.id,))
            if not cur.fetchone()[0]:
                cur.execute("UPDATE users SET referrer=? WHERE user_id=?", (referrer, user.id))
                cur.execute("UPDATE users SET points = points + 10 WHERE user_id=?", (referrer,))
                try: await context.bot.send_message(referrer, "Someone joined with your link! +10 Points")
                except: pass
    conn.commit(); conn.close()
    pts = get_user_points(user.id)
    keyboard = [[InlineKeyboardButton("Join Community", url=GROUP_LINK)]]
    await update.message.reply_text(f"Hello {user.first_name}!\n\nWelcome to GovernWatch.\n\nStep 1: Join our Community\nStep 2: Send /verify to get +20 points\nStep 3: Invite friends with /referral to get +10 each\n\nYour points: {pts}\n\nSend /help to see all commands.", reply_markup=InlineKeyboardMarkup(keyboard))

async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user.id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER, ChatMemberStatus.CREATOR]:
            conn = get_db(); cur = conn.cursor()
            cur.execute("SELECT * FROM verified WHERE user_id=?", (user.id,))
            if cur.fetchone():
                await update.message.reply_text("You are already Verified! Send /profile to see your points.")
            else:
                cur.execute("INSERT INTO verified VALUES (?)", (user.id,))
                cur.execute("UPDATE users SET points = points + 20 WHERE user_id=?", (user.id,))
                conn.commit()
                await update.message.reply_text("Verified! +20 Points! Send /profile to see your points.")
            conn.close()
        else:
            await update.message.reply_text("You have not joined the Group yet. Join and try again:\n" + GROUP_LINK)
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("You have not joined the Group yet. Join and try again:\n" + GROUP_LINK + "\n\nIf you already joined, make sure the Bot is Admin in the Group.")

async def points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pts = get_user_points(user.id)
    await update.message.reply_text(f"{user.first_name}\n\nYour Points: {pts}\n\nYour Referral Link:\nhttps://t.me/{BOT_USERNAME}?start={user.id}")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    pts = get_user_points(user.id); rank = get_rank(user.id); refs = get_referral_count(user.id)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM verified WHERE user_id=?", (user.id,))
    is_verified = "Verified" if cur.fetchone() else "Not Verified"
    conn.close()
    await update.message.reply_text(f"PROFILE\n\nName: {user.first_name}\nUsername: @{user.username or 'None'}\nStatus: {is_verified}\n\nPoints: {pts}\nRank: #{rank}\nReferrals: {refs} people\n\nReferral Link:\nhttps://t.me/{BOT_USERNAME}?start={user.id}\n\nSend /daily to claim +5 Points for today!")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    refs = get_referral_count(user.id); pts = get_user_points(user.id)
    link = f"https://t.me/{BOT_USERNAME}?start={user.id}"
    await update.message.reply_text(f"REFERRAL\n\nInvite your friends, get +10 Points for each!\n\nYour Link:\n{link}\n\nPeople you invited: {refs}\nYour Points: {pts}\n\nShare this link with your friends!")

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; today = str(date.today())
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT last_daily FROM users WHERE user_id=?", (user.id,))
    row = cur.fetchone()
    if row and row[0] == today:
        await update.message.reply_text("You already claimed Daily for today! Come back tomorrow.")
    else:
        cur.execute("UPDATE users SET points = points + 5, last_daily=? WHERE user_id=?", (today, user.id))
        conn.commit()
        pts = get_user_points(user.id)
        await update.message.reply_text(f"Daily Bonus! +5 Points!\n\nYour Points now: {pts}\nCome back tomorrow!")
    conn.close()

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = cur.fetchall(); conn.close()
    text = "LEADERBOARD - Top 10\n\n"
    for i, (name, pts) in enumerate(rows, 1): text += f"{i}. {name or 'User'} - {pts} pts\n"
    await update.message.reply_text(text or "No one yet.")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Join Community", url=GROUP_LINK)]]
    await update.message.reply_text("Click below to join our Community, then come back and send /verify", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("GovernWatchBot - Commands\n\n/start - Start Bot\n/verify - Verify you joined Group (+20)\n/profile - View your Profile\n/points - View your Points\n/referral - Get your Referral Link (+10)\n/daily - Claim +5 Points for today\n/leaderboard - Top 10\n/connect - Group Link\n/help - This list\n\nJoin Group, Verify, Invite friends!")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized.")
        return
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(points) FROM users")
    total_users, total_points = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM verified")
    total_verified = cur.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"ADMIN STATS\n\nTotal Users: {total_users or 0}\nVerified Users: {total_verified}\nTotal Points Given: {total_points or 0}\n\nWeb Dashboard: Open your Render link + /admin")

def main():
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))).start()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("verify", verify))
    application.add_handler(CommandHandler("points", points))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("referral", referral))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("connect", connect))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("admin", admin_stats))
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
