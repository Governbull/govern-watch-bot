import os
import threading
from datetime import date
from flask import Flask
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ChatMemberHandler
from telegram.constants import ChatMemberStatus

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DATABASE_URL = os.environ.get("DATABASE_URL")
GROUP_LINK = "https://t.me/governpublic"
GROUP_USERNAME = "@governpublic"
X_LINK = "https://x.com/Governbull"

app = Flask(__name__)
@app.route("/")
def home():
    return "GOVERN Bot is Live - GVNP!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def main_menu(is_verified=False):
    if is_verified:
        keyboard = [
            [KeyboardButton("📋 My Profile"), KeyboardButton("🎯 Tasks")],
            [KeyboardButton("🔥 Raid"), KeyboardButton("📅 Daily")],
            [KeyboardButton("🏆 Leaderboard"), KeyboardButton("👥 Invite")],
        ]
    else:
        keyboard = [
            [KeyboardButton("✅ Verify"), KeyboardButton("👥 Join Group")],
            [KeyboardButton("📋 My Profile"), KeyboardButton("🎯 Tasks")],
            [KeyboardButton("🏆 Leaderboard"), KeyboardButton("❓ Help")],
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, verified INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_daily TEXT, last_raid TEXT, invited_by BIGINT, x_username TEXT, raid_count INTEGER DEFAULT 0, joined_group INTEGER DEFAULT 0)""")
    c.execute("CREATE TABLE IF NOT EXISTS raids (id SERIAL PRIMARY KEY, link TEXT, active INTEGER DEFAULT 1)")
    c.execute("CREATE TABLE IF NOT EXISTS claimed_tasks (user_id BIGINT, task_id TEXT, PRIMARY KEY(user_id, task_id))")
    c.execute("CREATE TABLE IF NOT EXISTS pending (user_id BIGINT, photo_id TEXT)")
    conn.commit(); conn.close()

def get_user(uid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
    row = c.fetchone(); conn.close()
    if not row: return None
    return (row['user_id'], row['username'], row['points'], row['verified'], row['streak'], row['last_daily'], row['last_raid'], row['invited_by'], row['x_username'], row['raid_count'], row['joined_group'])

def add_points(uid, pts):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE users SET points=points+%s WHERE user_id=%s", (pts, uid))
    conn.commit(); conn.close()

def get_rank(uid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT user_id FROM users ORDER BY points DESC")
    rows = c.fetchall(); conn.close()
    for i, r in enumerate(rows, 1):
        if r['user_id'] == uid: return i
    return 0

def get_active_raid():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, link FROM raids WHERE active=1 ORDER BY id DESC LIMIT 1")
    row = c.fetchone(); conn.close()
    return (row['id'], row['link']) if row else None

def save_raid(link):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE raids SET active=0")
    c.execute("INSERT INTO raids (link, active) VALUES (%s,1)", (link,))
    conn.commit(); conn.close()

def get_invite_count(uid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE invited_by=%s", (uid,))
    n = c.fetchone()['cnt']; conn.close(); return n

def get_badge(pts):
    if pts >= 500: return "GOVERNOR"
    if pts >= 200: return "ELITE"
    if pts >= 100: return "WARRIOR"
    return "CITIZEN"

async def check_group(update):
    if update.effective_chat.type in ["group", "supergroup"]:
        return True
    return False

TASKS = [
    {"id": "join_tg", "title": "Join Telegram Group", "points": 20, "desc": "Join our community group"},
    {"id": "connect_x", "title": "Connect Your X", "points": 10, "desc": "Tap Connect X and send @username"},
    {"id": "follow_x", "title": "Follow on X", "points": 20, "desc": "Follow @Governbull on X"},
    {"id": "first_raid", "title": "Complete First Raid", "points": 50, "desc": "Do 1 raid and get approval"},
    {"id": "raid_10", "title": "Complete 10 Raids", "points": 200, "desc": "Do 10 raids with approval"},
    {"id": "invite_3", "title": "Invite 3 Friends", "points": 30, "desc": "Share your link from Invite"},
    {"id": "daily_7", "title": "7-Day Daily Streak", "points": 50, "desc": "Tap Daily 7 days in a row"},
]

def is_task_claimed(uid, tid):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT 1 FROM claimed_tasks WHERE user_id=%s AND task_id=%s", (uid, tid))
    r = c.fetchone(); conn.close(); return bool(r)

def check_task(uid, tid, row):
    if tid == "join_tg": return bool(row[3]) or bool(row[10])
    if tid == "connect_x": return bool(row[8])
    if tid == "follow_x": return bool(row[3])
    if tid == "first_raid": return (row[9] or 0) >= 1
    if tid == "raid_10": return (row[9] or 0) >= 10
    if tid == "invite_3": return get_invite_count(uid) >= 3
    if tid == "daily_7": return (row[4] or 0) >= 7
    return False

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if result is None:
        return
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    if old_status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED] and new_status == ChatMemberStatus.MEMBER:
        user = result.new_chat_member.user
        if user.is_bot:
            return
        name = user.first_name
        username = f"@{user.username}" if user.username else name
        kb = [[InlineKeyboardButton("🚀 Start Earning GVNP", url=f"https://t.me/{context.bot.username}?start")]]
        txt = (
            f"👑 WELCOME TO GOVERN, {name}! {username} 👑\n\n"
            f"We are happy to have you here.\n\n"
            f"🔥 You are now part of the GOVERN Family.\n"
            f"💰 Earn GVNP - Our Community Token\n\n"
            f"👉 STEP 1: Go to @GovernWatchBot\n"
            f"👉 STEP 2: Tap ✅ Verify\n"
            f"👉 STEP 3: Tap 🎯 Tasks and Start Earning\n\n"
            f"Do not just watch. Join us. WE GOVERN. WE DON'T FOLLOW. 👑"
        )
        try:
            await context.bot.send_message(chat_id=result.chat.id, text=txt, reply_markup=InlineKeyboardMarkup(kb))
        except Exception as e:
            print(e, flush=True)

async def do_start(update, context, invited_by=None):
    user = update.effective_user
    existing = get_user(user.id)
    if existing:
        txt = f"Welcome back, {user.first_name}! 👋\n\n💰 GVNP Balance: {existing[2]} GVNP 🪙\nBadge: {get_badge(existing[2])}\nRank: #{get_rank(user.id)}\n\nYou are already part of GOVERN. No need to join again.\nKeep earning GVNP!"
        await update.message.reply_text(txt, reply_markup=main_menu(True))
        return
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO users (user_id, username, invited_by) VALUES (%s,%s,%s)", (user.id, user.username or user.first_name, invited_by))
    conn.commit()
    if invited_by and invited_by != user.id:
        c.execute("UPDATE users SET points=points+10 WHERE user_id=%s", (invited_by,))
        conn.commit()
        try: await context.bot.send_message(chat_id=invited_by, text="New user joined with your link! +10 GVNP! 🪙")
        except: pass
    conn.close()
    txt = f"Welcome to GOVERN, {user.first_name}! 👑\n\nWe build together. We win together.\n\n💰 Earn GVNP - Our Community Token\nTap ✅ Verify below to start earning GVNP."
    await update.message.reply_text(txt, reply_markup=main_menu(False))

async def do_verify(update, context):
    user = update.effective_user
    existing = get_user(user.id)
    if existing and existing[3] == 1:
        await update.message.reply_text(f"You are already verified, {user.first_name}! ✅\n\n💰 GVNP Balance: {existing[2]} GVNP 🪙\nBadge: {get_badge(existing[2])}\nRank: #{get_rank(user.id)}\n\nYou already joined. No need to join again.", reply_markup=main_menu(True))
        return
    conn = get_conn(); c = conn.cursor()
    if existing:
        c.execute("UPDATE users SET verified=1, joined_group=1, username=%s WHERE user_id=%s", (user.username or user.first_name, user.id))
    else:
        c.execute("INSERT INTO users (user_id, username, verified, joined_group) VALUES (%s,%s,1,1)", (user.id, user.username or user.first_name))
    conn.commit(); conn.close()
    await update.message.reply_text("Verified! You are now a CITIZEN. ✅\n\nWelcome to GOVERN.\nTap 🎯 Tasks below to start earning GVNP.", reply_markup=main_menu(True))

async def do_profile(update, context):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Tap ✅ Verify first.", reply_markup=main_menu(False)); return
    bot_username = context.bot.username or "GovernWatchBot"
    kb = [[InlineKeyboardButton("🎯 Tasks", callback_data="tasks")], [InlineKeyboardButton("🔥 Raid", callback_data="raid")]]
    txt = f"Profile: {user.first_name}\n💰 GVNP Balance: {row[2]} GVNP 🪙\nBadge: {get_badge(row[2])}\nRank: #{get_rank(user.id)}\nStreak: {row[4]} days\nApproved Raids: {row[9] or 0}\nInvited: {get_invite_count(user.id)} friends\n\nYour Invite Link:\nhttps://t.me/{bot_username}?start={user.id}\n\nShare it, get +10 GVNP per person!"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def do_tasks(update, context):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Tap ✅ Verify first.", reply_markup=main_menu(False)); return
    text = f"GOVERN TASKS - Earn GVNP 🪙\nYour Balance: {row[2]} GVNP\n\n"
    kb = []
    for t in TASKS:
        claimed = is_task_claimed(user.id, t["id"])
        done_ok = check_task(user.id, t["id"], row)
        if claimed: status = "✅ CLAIMED"
        elif done_ok: status = "🟢 READY - Tap Claim"
        else: status = "⏳ NOT DONE"
        extra = ""
        if t["id"] == "first_raid": extra = f" Raids: {row[9] or 0}/1"
        if t["id"] == "raid_10": extra = f" Raids: {row[9] or 0}/10"
        if t["id"] == "invite_3": extra = f" Invited: {get_invite_count(user.id)}/3"
        if t["id"] == "daily_7": extra = f" Streak: {row[4] or 0}/7"
        text += f"{t['title']} - {t['points']} GVNP - {status}{extra}\n{t['desc']}\n\n"
        if done_ok and not claimed:
            kb.append([InlineKeyboardButton(f"Claim {t['title']} +{t['points']} GVNP", callback_data="claim_" + t["id"])])
    kb.append([InlineKeyboardButton("𝕏 Connect My X", callback_data="connect_x")])
    kb.append([InlineKeyboardButton("𝕏 Follow on X", url=X_LINK)])
    if not row[3] and not row[10]:
        kb.append([InlineKeyboardButton("👥 Join Group", url=GROUP_LINK)])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def do_daily(update, context):
    user = update.effective_user
    row = get_user(user.id)
    if not row:
        await update.message.reply_text("Tap ✅ Verify first.", reply_markup=main_menu(False)); return
    today = date.today().isoformat()
    if row[5] == today:
        await update.message.reply_text("Already claimed today! Come back tomorrow. ✅", reply_markup=main_menu(True)); return
    streak = 1
    try:
        if row[5] and (date.fromisoformat(today) - date.fromisoformat(row[5])).days == 1:
            streak = row[4] + 1
    except: streak = 1
    bonus = 50 if streak >= 7 else 0
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE users SET points=points+%s, last_daily=%s, streak=%s WHERE user_id=%s", (10+bonus, today, streak, user.id))
    conn.commit(); conn.close()
    msg = f"DAILY CHECK-IN! ✅\n+10 GVNP 🪙\nStreak: {streak} days\nYour Balance: {get_user(user.id)[2]} GVNP"
    if bonus: msg += "\n7-DAY BONUS! +50 GVNP 🪙"
    await update.message.reply_text(msg, reply_markup=main_menu(True))

async def do_raid(update, context):
    r = get_active_raid()
    if not r:
        await update.message.reply_text("No active raid yet. Wait for admin.", reply_markup=main_menu(True)); return
    kb = [[InlineKeyboardButton("Open Tweet on X", url=r[1])]]
    txt = "ACTIVE RAID:\n\n" + r[1] + "\n\n1. Like + Repost + Comment\n2. Take screenshot\n3. Send screenshot here\nAdmin will approve +10 GVNP 🪙"
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb))

async def do_leaderboard(update, context):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    rows = c.fetchall(); conn.close()
    if not rows:
        await update.message.reply_text("No citizens yet. Tap ✅ Verify", reply_markup=main_menu(False)); return
    txt = "GOVERN Leaderboard - Top GVNP Holders 🏆:\n\n"
    for i, r in enumerate(rows, 1):
        txt += f"{i}. {r['username'] or 'User'} - {r['points']} GVNP 🪙\n"
    await update.message.reply_text(txt, reply_markup=main_menu(True))

async def do_invite(update, context):
    user = update.effective_user
    bot_username = context.bot.username or "GovernWatchBot"
    txt = f"Your Invite Link:\nhttps://t.me/{bot_username}?start={user.id}\n\nShare it. Get +10 GVNP per person!\nInvited: {get_invite_count(user.id)} friends"
    await update.message.reply_text(txt, reply_markup=main_menu(True))

async def do_help(update, context):
    txt = "GOVERN - Earn GVNP 🪙\n\n✅ Verify - Join\n📋 My Profile - Your GVNP Balance\n🎯 Tasks - Earn GVNP\n🔥 Raid - Active raid\n📅 Daily - Daily +10 GVNP\n🏆 Leaderboard - Top GVNP Holders\n👥 Invite - Invite friends, +10 GVNP each\n\nNo need to type any command! Just tap buttons."
    await update.message.reply_text(txt, reply_markup=main_menu(True))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update): return
    invited_by = None
    if context.args and context.args[0].isdigit():
        invited_by = int(context.args[0])
    await do_start(update, context, invited_by)

async def verify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update): return
    await do_verify(update, context)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        return
    user = update.effective_user
    if not get_user(user.id):
        await update.message.reply_text("Tap ✅ Verify first.", reply_markup=main_menu(False)); return
    photo_id = update.message.photo[-1].file_id
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO pending VALUES (%s,%s)", (user.id, photo_id))
    conn.commit(); conn.close()
    await update.message.reply_text("Screenshot received! Waiting for admin approval. +10 GVNP after approval.")
    try:
        kb = [[InlineKeyboardButton("Approve +10 GVNP", callback_data="approve_" + str(user.id))], [InlineKeyboardButton("Reject", callback_data="reject_" + str(user.id))]]
        cap = f"New Raid Proof\nFrom: {user.first_name} @{user.username or ''}\nID: {user.id}"
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=cap, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e: print(e, flush=True)

async def handle_claim(user, task_id, reply_func):
    row = get_user(user.id)
    if not row:
        await reply_func("Tap ✅ Verify first."); return
    task = next((t for t in TASKS if t["id"] == task_id), None)
    if not task:
        await reply_func("Invalid task."); return
    if is_task_claimed(user.id, task_id):
        await reply_func(f"Already claimed: {task['title']} ✅\nYou cannot claim it twice."); return
    if not check_task(user.id, task_id, row):
        await reply_func("Task not done yet: " + task["title"]); return
    conn = get_conn(); c = conn.cursor()
    try:
        c.execute("INSERT INTO claimed_tasks VALUES (%s,%s)", (user.id, task_id))
        conn.commit()
    except Exception:
        conn.close(); await reply_func("Already claimed. ✅"); return
    conn.close()
    add_points(user.id, task["points"])
    await reply_func(f"Claimed {task['title']}! +{task['points']} GVNP! 🎉\nYour total: {get_user(user.id)[2]} GVNP 🪙")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if update.effective_chat.type in ["group", "supergroup"]:
        await q.answer("Please use DM @GovernWatchBot", show_alert=True); return
    data = q.data; user = update.effective_user
    class FakeUpdate:
        def __init__(self, u, msg): self.effective_user = u; self.message = msg; self.effective_chat = update.effective_chat
    fake = FakeUpdate(user, q.message)
    if data == "verify":
        await do_verify(fake, context)
    elif data == "tasks":
        await do_tasks(fake, context)
    elif data == "profile":
        await do_profile(fake, context)
    elif data == "leaderboard":
        await do_leaderboard(fake, context)
    elif data == "raid":
        await do_raid(fake, context)
    elif data == "connect_x":
        await q.message.reply_text("Send your X username like this:\n@your_username\nJust type it, I will connect it for you.")
        context.user_data["waiting_x"] = True
    elif data.startswith("claim_"):
        tid = data.replace("claim_", "")
        async def reply_func(text): await q.message.reply_text(text)
        await handle_claim(user, tid, reply_func)
    elif data.startswith("approve_"):
        if user.id != ADMIN_ID: return
        target_id = int(data.replace("approve_", ""))
        conn = get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET points=points+10, raid_count=raid_count+1 WHERE user_id=%s", (target_id,))
        conn.commit(); conn.close()
        conn = get_conn(); c = conn.cursor()
        c.execute("DELETE FROM pending WHERE user_id=%s", (target_id,))
        conn.commit(); conn.close()
        await q.message.reply_text(f"Approved +10 GVNP to {target_id} ✅")
        try: await context.bot.send_message(chat_id=target_id, text="Your Raid Approved! +10 GVNP! 🔥\nCheck 📋 My Profile")
        except: pass
    elif data.startswith("reject_"):
        if user.id != ADMIN_ID: return
        target_id = int(data.replace("reject_", ""))
        conn = get_conn(); c = conn.cursor()
        c.execute("DELETE FROM pending WHERE user_id=%s", (target_id,))
        conn.commit(); conn.close()
        await q.message.reply_text(f"Rejected {target_id}")
        try: await context.bot.send_message(chat_id=target_id, text="Your Raid was rejected. Try again with clear screenshot.")
        except: pass

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_group(update): return
    text = (update.message.text or "").strip()
    if context.user_data.get("waiting_x"):
        context.user_data["waiting_x"] = False
        x_user = text.replace("@", "").split()[0]
        user = update.effective_user
        conn = get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET x_username=%s WHERE user_id=%s", (x_user, user.id))
        if c.rowcount == 0:
            c.execute("INSERT INTO users (user_id, username, x_username, verified) VALUES (%s,%s,%s,1)", (user.id, user.username or user.first_name, x_user))
        conn.commit(); conn.close()
        await update.message.reply_text(f"X connected: @{x_user} ✅\nTap 🎯 Tasks and Claim +10 GVNP!", reply_markup=main_menu(True))
        return
    if text == "✅ Verify":
        await do_verify(update, context)
    elif text == "📋 My Profile":
        await do_profile(update, context)
    elif text == "🎯 Tasks":
        await do_tasks(update, context)
    elif text == "🔥 Raid":
        await do_raid(update, context)
    elif text == "📅 Daily":
        await do_daily(update, context)
    elif text == "🏆 Leaderboard":
        await do_leaderboard(update, context)
    elif text == "👥 Invite":
        await do_invite(update, context)
    elif text == "👥 Join Group":
        row = get_user(update.effective_user.id)
        if row and (row[3]==1 or row[10]==1):
            await update.message.reply_text("You already joined! ✅", reply_markup=main_menu(True))
        else:
            kb = [[InlineKeyboardButton("Join GOVERN Group", url=GROUP_LINK)]]
            await update.message.reply_text("Tap Join below, then tap ✅ Verify", reply_markup=InlineKeyboardMarkup(kb))
    elif text == "❓ Help":
        await do_help(update, context)
    elif text.startswith("@") and len(text) > 2:
        x_user = text.replace("@", "")
        user = update.effective_user
        conn = get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET x_username=%s WHERE user_id=%s", (x_user, user.id))
        conn.commit(); conn.close()
        await update.message.reply_text(f"X connected: @{x_user} ✅\nTap 🎯 Tasks to Claim!", reply_markup=main_menu(True))
    else:
        await update.message.reply_text("Tap a button below 👇\nNo need to type commands.", reply_markup=main_menu(True))

async def newraid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Admin only."); return
    if not context.args:
        await update.message.reply_text("Admin: Usage /newraid <tweet link>"); return
    link = " ".join(context.args)
    save_raid(link)
    await update.message.reply_text("New Raid Set! Broadcasting to all users...")
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE verified=1")
    users = c.fetchall(); conn.close()
    count = 0
    for u in users:
        try:
            kb = [[InlineKeyboardButton("🔥 Join Raid Now", callback_data="raid")]]
            await context.bot.send_message(chat_id=u['user_id'], text=f"🔥 NEW RAID IS LIVE!\n\n{link}\n\n1. Like + Repost + Comment\n2. Screenshot\n3. Send screenshot here\n\nBe fast! +10 GVNP after approval.", reply_markup=InlineKeyboardMarkup(kb))
            count += 1
        except:
            pass
    try:
        await context.bot.send_message(chat_id=GROUP_USERNAME, text=f"🔥 NEW RAID IS LIVE, GOVERN FAMILY!\n\nGo to @GovernWatchBot and tap 🔥 Raid\n\nLike + Repost + Comment = +10 GVNP!\n\nBe fast!")
    except:
        pass
    await update.message.reply_text(f"✅ Raid broadcasted to {count} users + Group!")

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("verify", verify_cmd))
    app_bot.add_handler(CommandHandler("newraid", newraid))
    app_bot.add_handler(CommandHandler("setraid", newraid))
    app_bot.add_handler(ChatMemberHandler(welcome_new_member, ChatMemberHandler.CHAT_MEMBER))
    app_bot.add_handler(CallbackQueryHandler(button_handler))
    app_bot.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot running - GVNP...", flush=True)
    app_bot.run_polling()

if __name__ == "__main__":
    main()
