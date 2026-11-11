# -*- coding: utf-8 -*-
import os
import re
import time
import sqlite3
import threading
import telebot
from telebot import types

class Config:
    TOKEN = os.environ.get("BOT_TOKEN", "8721804861:AAHcUmRNRqdBIi3-LIJnvzzd8tWnyvdZPiQ")
    DEVELOPER_ID = 4322490316
    SUPPORT_GROUP = -1004471681505
    DB_PATH = "/tmp/secretary.db"
    RULES_URL = "https://telegra.ph/Pravila-dlya-polzovatelej-tesnyj-angel-07-24"
    FLOOD_INTERVAL = 2
    MUTE_TIME = 30
    MIN_SETROLE = 5
    MIN_REMOVEROLE = 5
    MIN_BAN = 5
    MIN_UNBAN = 5
    MIN_WARN = 5
    MIN_UNWARN = 5
    MIN_KICK = 5
    MIN_MUTE = 5
    MIN_UNMUTE = 5
    MIN_BOTSTATS = 8
    MIN_LOGS = 8
    MIN_BROADCAST = 8
    MIN_CHECK = 1
    MIN_TAKE = 1

RANKS = {
    0: "Пользователь", 1: "Администратор", 2: "Младший администратор",
    3: "Администратор бота", 4: "Старший администратор", 5: "Заместитель совладельца",
    6: "Заместитель владельца", 7: "Совладелец", 8: "Владелец", 100: "Разработчик",
}

class Storage:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self.lock:
            c = self.conn.cursor()
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, username TEXT, pseudo TEXT UNIQUE,
                    nickname TEXT, age TEXT, need TEXT, rank INTEGER DEFAULT 0,
                    agreement INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
                    ban_reason TEXT, warns INTEGER DEFAULT 0, muted_until REAL DEFAULT 0,
                    last_msg REAL DEFAULT 0, messages INTEGER DEFAULT 0,
                    rating_sum INTEGER DEFAULT 0, rating_count INTEGER DEFAULT 0, joined TEXT
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                    admin_id INTEGER, category TEXT, status TEXT DEFAULT 'open', created TEXT
                );
                CREATE TABLE IF NOT EXISTS replies (
                    admin_msg_id INTEGER PRIMARY KEY, user_id INTEGER, ticket_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, admin_id INTEGER,
                    target_id INTEGER, details TEXT, date TEXT
                );
                CREATE TABLE IF NOT EXISTS command_perms (command TEXT PRIMARY KEY, min_rank INTEGER);
            """)
            c.execute("INSERT OR IGNORE INTO settings VALUES('agreement', 'Прежде чем продолжить, ознакомься с правилами использования бота.')")
            c.execute("INSERT OR IGNORE INTO users(user_id, rank, nickname, joined) VALUES(?, 100, 'Разработчик', ?)",
                      (Config.DEVELOPER_ID, time.strftime("%d.%m.%Y")))
            defaults = {"setrole": 5, "removerole": 5, "ban": 5, "unban": 5, "warn": 5, "unwarn": 5,
                        "kick": 5, "mute": 5, "unmute": 5, "check": 1, "botstats": 8, "logs": 8, "broadcast": 8}
            for cmd, rank in defaults.items():
                c.execute("INSERT OR IGNORE INTO command_perms VALUES(?, ?)", (cmd, rank))
            self.conn.commit()

    def _exec(self, sql, params=(), fetch=None):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            if fetch == "one": return cur.fetchone()
            if fetch == "all": return cur.fetchall()
            self.conn.commit()
            return cur.lastrowid

    def get_user(self, uid):
        row = self._exec("SELECT * FROM users WHERE user_id=?", (uid,), "one")
        if not row:
            self._exec("INSERT INTO users(user_id, joined) VALUES(?, ?)", (uid, time.strftime("%d.%m.%Y")))
            row = self._exec("SELECT * FROM users WHERE user_id=?", (uid,), "one")
        return row

    def set_user(self, uid, **kwargs):
        if not kwargs: return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        self._exec(f"UPDATE users SET {fields} WHERE user_id=?", list(kwargs.values()) + [uid])

    def set_rank(self, uid, rank, nickname=None):
        self._exec("UPDATE users SET rank=?, nickname=? WHERE user_id=?", (int(rank), nickname, uid))

    def remove_role(self, uid):
        self._exec("UPDATE users SET rank=0, nickname=NULL WHERE user_id=?", (uid,))

    def pseudo_taken(self, pseudo):
        return self._exec("SELECT user_id FROM users WHERE pseudo=?", (pseudo,), "one") is not None

    def set_ban(self, uid, banned, reason=""):
        self._exec("UPDATE users SET banned=?, ban_reason=? WHERE user_id=?", (banned, reason, uid))

    def set_warns(self, uid, count):
        self._exec("UPDATE users SET warns=? WHERE user_id=?", (count, uid))

    def add_rating(self, uid, score):
        self._exec("UPDATE users SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE user_id=?", (score, uid))

    def rating_str(self, uid):
        if uid == Config.DEVELOPER_ID: return "⭐⭐⭐⭐⭐ (5.0)"
        u = self.get_user(uid)
        if not u["rating_count"]: return "—"
        avg = round(u["rating_sum"] / u["rating_count"], 1)
        return f"{'⭐' * int(round(avg))} ({avg})"

    def get_all_admins(self):
        return self._exec("SELECT * FROM users WHERE rank >= 1 ORDER BY rank DESC, user_id", fetch="all") or []

    def create_ticket(self, uid, category):
        return self._exec("INSERT INTO tickets(user_id, category, created) VALUES(?, ?, ?)", (uid, category, time.strftime("%d.%m.%Y %H:%M")))

    def get_open_ticket(self, uid):
        return self._exec("SELECT * FROM tickets WHERE user_id=? AND status='open' ORDER BY ticket_id DESC LIMIT 1", (uid,), "one")

    def get_ticket(self, tid):
        return self._exec("SELECT * FROM tickets WHERE ticket_id=?", (tid,), "one")

    def set_ticket_admin(self, tid, admin_id):
        self._exec("UPDATE tickets SET admin_id=? WHERE ticket_id=?", (admin_id, tid))

    def close_ticket(self, tid):
        self._exec("UPDATE tickets SET status='closed' WHERE ticket_id=?", (tid,))

    def save_reply(self, msg_id, uid, tid):
        self._exec("REPLACE INTO replies VALUES(?, ?, ?)", (msg_id, uid, tid))

    def get_reply(self, msg_id):
        return self._exec("SELECT * FROM replies WHERE admin_msg_id=?", (msg_id,), "one")

    def get_setting(self, key, default=""):
        row = self._exec("SELECT value FROM settings WHERE key=?", (key,), "one")
        return row["value"] if row else default

    def add_log(self, action, admin_id=None, target_id=None, details=""):
        self._exec("INSERT INTO logs(action, admin_id, target_id, details, date) VALUES(?, ?, ?, ?, ?)", (action, admin_id, target_id, details, time.strftime("%d.%m.%Y %H:%M:%S")))

    def get_logs(self, limit=10):
        return self._exec("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,), "all") or []

    def get_all_users(self):
        return self._exec("SELECT user_id FROM users", fetch="all") or []

    def get_stats(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM users"); total = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE rank >= 1"); admins = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE rank = 0"); users_only = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE banned=1"); banned = cur.fetchone()["cnt"]
            cur.execute("SELECT COUNT(*) as cnt FROM users WHERE messages > 0"); active = cur.fetchone()["cnt"]
            cur.execute("SELECT SUM(messages) as s FROM users"); total_messages = cur.fetchone()["s"] or 0
            cur.execute("SELECT SUM(warns) as s FROM users"); total_warns = cur.fetchone()["s"] or 0
        return {"total": total, "admins": admins, "users_only": users_only, "banned": banned,
                "active": active, "total_messages": total_messages, "total_warns": total_warns}

    def get_perm(self, command, default=8):
        row = self._exec("SELECT min_rank FROM command_perms WHERE command=?", (command,), "one")
        return row["min_rank"] if row else default

db = Storage(Config.DB_PATH)
bot = telebot.TeleBot(Config.TOKEN, parse_mode="HTML")
try:
    bot.remove_webhook(drop_pending_updates=True)
    print("✅ Webhook удалён")
except Exception as e:
    print(f"⚠️ Webhook: {e}")

talk_sessions = {}

def rank_of(uid): return 100 if uid == Config.DEVELOPER_ID else db.get_user(uid)["rank"]
def rank_label(r): return "⚙️ Разработчик" if r == 100 else ("👤 Пользователь" if r == 0 else f"🛡 {RANKS.get(r, 'Неизвестно')}")
def is_banned(uid): return bool(db.get_user(uid)["banned"])

def nick_tg(uid):
    try: return bot.get_chat(uid).first_name or f"ID{uid}"
    except: return f"ID{uid}"

def safe_username(uid):
    u = db.get_user(uid)
    if u["username"]: return f"@{u['username']}"
    try:
        c = bot.get_chat(uid)
        return f"@{c.username}" if c.username else "без username"
    except: return "без username"

def admin_pseudo(uid):
    if not uid: return "(#не назначен)"
    nick = db.get_user(uid)["nickname"]
    return f"(#{nick})" if nick else "(#Администратор)"

def is_flood(uid):
    u = db.get_user(uid); now = time.time()
    if u["muted_until"] and now < u["muted_until"]: return True
    if u["last_msg"] and now - u["last_msg"] < Config.FLOOD_INTERVAL:
        db.set_user(uid, muted_until=now + Config.MUTE_TIME); return True
    db.set_user(uid, last_msg=now); return False

def check_access(message, min_rank):
    if rank_of(message.from_user.id) < min_rank:
        bot.reply_to(message, "❌ Недостаточно прав!"); return False
    return True

def parse_pseudo(raw):
    if not raw: return None, "Введите псевдоним через \"#\" пример: #бес"
    raw = raw.strip()
    if not raw.startswith("#"): return None, "Введите псевдоним через \"#\" пример: #бес"
    name = raw[1:]
    if not name: return None, "Введите псевдоним через \"#\" пример: #бес"
    if re.search(r"\d", name): return None, "Используйте только буквы пример: #бес"
    if not re.match(r"^[A-Za-zА-Яа-яЁё]+$", name): return None, "Используйте только буквы пример: #бес"
    pseudo = "#" + name
    if db.pseudo_taken(pseudo): return None, "Этот псевдоним уже занят!"
    return pseudo, None

def resolve_user(message, text):
    if message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id == bot.get_me().id:
            r = db.get_reply(rt.message_id)
            if r: return r["user_id"]
        return rt.from_user.id
    if not text: return None
    arg = text.strip().split()[0]
    if arg.isdigit(): return int(arg)
    if arg.startswith("@"):
        try: return bot.get_chat(arg).id
        except: return None
    return None

def main_menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(types.KeyboardButton("💬 Поговорить с бесом"))
    return kb

def dialog_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(types.KeyboardButton("❌ Разорвать связь"), types.KeyboardButton("⭐ Поставить оценку"),
           types.KeyboardButton("🔄 Сменить беса"), types.KeyboardButton("👑 Позвать беса"))
    return kb

def need_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("💙 Поддержка", callback_data="need_Поддержка"),
           types.InlineKeyboardButton("💬 Общение", callback_data="need_Общение"),
           types.InlineKeyboardButton("🎯 Универсал", callback_data="need_Универсал"))
    return kb

def rating_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for i in range(1, 6): kb.add(types.InlineKeyboardButton(str(i), callback_data=f"rate_{i}"))
    return kb
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if message.chat.type != "private": return
    uid = message.from_user.id; u = db.get_user(uid)
    if u["banned"]: return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
    if not u["agreement"]:
        agreement = db.get_setting("agreement", "Прежде чем продолжить, ознакомься с правилами использования бота.")
        text = f"❗<b>Пользовательское соглашение</b>\n\n{agreement}\n\nНажми на кнопку <b>«Принять соглашение»</b>, чтобы продолжить."
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("✅ Принять соглашение", callback_data="accept"),
               types.InlineKeyboardButton("📜 Пользовательское соглашение", url=Config.RULES_URL))
        return bot.send_message(uid, text, reply_markup=kb)
    send_welcome(uid)

def send_welcome(uid):
    text = ("Соглашение принято ✅\n\n🌙 <b>ᴨᴩиʙᴇт, зᴀбᴧудиʙɯᴀя душᴀ</b> 🖤\n\nЗа этим экраном — не роботы, а живые люди. Мы здесь, чтобы выслушать тебя и поговорить по душам.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n🕯️ <b>ᴄообщᴇния доходят нᴇ ᴄᴩᴀзу</b>\n\nПожалуйста, не блокируй бот, если тебе не ответили в первые 10–20 минут.\n\n"
            "🖤 <b>ᴋᴀᴋ нᴀчᴀᴛь?</b>\n\n▸ Нажми на кнопку «💬 Поговорить с бесом» внизу")
    bot.send_message(uid, text, reply_markup=main_menu_kb())

@bot.callback_query_handler(func=lambda c: c.data == "accept")
def cb_accept(call):
    uid = call.from_user.id
    if is_banned(uid): return bot.answer_callback_query(call.id, "Вы заблокированы")
    db.set_user(uid, agreement=1)
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    send_welcome(uid); bot.answer_callback_query(call.id, "✅ Соглашение принято")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "💬 Поговорить с бесом")
def btn_talk(message):
    uid = message.from_user.id
    if is_banned(uid): return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
    if db.get_open_ticket(uid): return bot.send_message(uid, "⚠️ У вас уже есть активный запрос!")
    u = db.get_user(uid)
    if u["pseudo"] and u["age"]:
        talk_sessions[uid] = {"step": 2, "pseudo": u["pseudo"], "age": u["age"]}
        return bot.send_message(uid, "💭 Что тебе нужно?", reply_markup=need_kb())
    talk_sessions[uid] = {"step": 0, "pseudo": None, "age": None}
    bot.send_message(uid, "💭 <b>Скрыть истинное имя (Псевдоним)</b>\n\nПридумай псевдоним — только буквы, через #. Пример: <code>#бес</code>")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.from_user.id in talk_sessions, content_types=["text"])
def talk_step(message):
    uid = message.from_user.id
    if is_banned(uid): return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
    state = talk_sessions[uid]; text = (message.text or "").strip()
    if state["step"] == 0:
        pseudo, err = parse_pseudo(text)
        if err: return bot.send_message(uid, err)
        state["pseudo"] = pseudo; state["step"] = 1
        return bot.send_message(uid, "🙂 Какого возраста хочешь себе беса?")
    if state["step"] == 1:
        if not text.isdigit(): return bot.send_message(uid, "Используйте только цифры!")
        state["age"] = text; db.set_user(uid, pseudo=state["pseudo"], age=state["age"]); state["step"] = 2
        return bot.send_message(uid, "💭 Что тебе нужно?", reply_markup=need_kb())
    if state["step"] == 2: return bot.send_message(uid, "Нажми на кнопку ниже 👇", reply_markup=need_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("need_"))
def cb_need(call):
    uid = call.from_user.id
    if is_banned(uid): return bot.answer_callback_query(call.id, "Вы заблокированы")
    if uid not in talk_sessions: return bot.answer_callback_query(call.id, "Анкета не активна")
    need = call.data.split("_", 1)[1]; state = talk_sessions.pop(uid)
    if state["pseudo"]: db.set_user(uid, pseudo=state["pseudo"], age=state["age"], need=need)
    else: db.set_user(uid, need=need)
    tid = db.create_ticket(uid, need)
    bot.edit_message_text("✔️ <b>Запрос отправлен!</b>\n\n❤️ Ожидай — кто-то из поддержки скоро напишет.\n\n<i>Можешь просто побыть здесь</i>", call.message.chat.id, call.message.message_id)
    post_new_ticket(uid, tid, need); bot.answer_callback_query(call.id, "✅ Запрос отправлен")

def post_new_ticket(uid, tid, need):
    u = db.get_user(uid)
    text = f"🆕 <b>Новый запрос</b>\n━━━━━━━━━━━━━━━━━━\n👤 <b>Псевдоним:</b> {u['pseudo']}\n🎂 <b>Возраст:</b> {u['age']}\n🎯 <b>Нужно:</b> {need}\n🆔 <code>{uid}</code>"
    kb = types.InlineKeyboardMarkup(); kb.add(types.InlineKeyboardButton("✅ Взять", callback_data=f"take_{tid}"))
    try:
        sent = bot.send_message(Config.SUPPORT_GROUP, text, reply_markup=kb); db.save_reply(sent.message_id, uid, tid)
    except Exception as e: print(f"[post_new_ticket] {e}")

@bot.callback_query_handler(func=lambda c: c.data.startswith("take_"))
def cb_take(call):
    admin_id = call.from_user.id
    if rank_of(admin_id) < Config.MIN_TAKE:
        return bot.answer_callback_query(call.id, "❌ Брать заявки могут только с 1 ранга", show_alert=True)
    tid = int(call.data.split("_", 1)[1]); t = db.get_ticket(tid)
    if not t or t["status"] != "open": return bot.answer_callback_query(call.id, "Заявка уже закрыта")
    if t["admin_id"]: return bot.answer_callback_query(call.id, "Заявку уже взяли", show_alert=True)
    db.set_ticket_admin(tid, admin_id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    u = db.get_user(t["user_id"])
    bot.send_message(Config.SUPPORT_GROUP, f"🖤 <b>Заявка принята</b>\n👮 Бес: {admin_pseudo(admin_id)}\n👤 Пользователь: {u['pseudo']}")
    rating = db.rating_str(admin_id)
    try:
        bot.send_message(t["user_id"], f"✔️ <b>Бес тут!</b>\n👮 Твой бес: {admin_pseudo(admin_id)}\n⭐ Рейтинг: {rating}\n\n❤️ Я здесь, чтобы выслушать и поддержать.\n\n💭 Просто пиши — я всё вижу.", reply_markup=dialog_kb())
    except: pass
    bot.answer_callback_query(call.id, "✅ Принято")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "❌ Разорвать связь")
def btn_close(message):
    uid = message.from_user.id
    if is_banned(uid): return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
    t = db.get_open_ticket(uid)
    if not t: return bot.send_message(uid, "⚠️ Нет активного обращения.")
    db.close_ticket(t["ticket_id"]); u = db.get_user(uid)
    bot.send_message(Config.SUPPORT_GROUP, f"🔚 <b>Обращение закрыто</b>\n━━━━━━━━━━━━━━━━━━\n👤 Пользователь: {u['pseudo']}")
    bot.send_message(uid, "✔️ <b>Обращение завершено.</b>\n\n⭐ Оцени, пожалуйста, работу поддержки:")
    bot.send_message(uid, "Выберите оценку:", reply_markup=rating_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("rate_"))
def cb_rate(call):
    uid = call.from_user.id
    if is_banned(uid): return bot.answer_callback_query(call.id, "Вы заблокированы")
    score = int(call.data.split("_", 1)[1]); stars = "⭐" * score
    last_ticket = db._exec("SELECT admin_id, ticket_id FROM tickets WHERE user_id=? AND admin_id IS NOT NULL ORDER BY ticket_id DESC LIMIT 1", (uid,), "one")
    if last_ticket and last_ticket["admin_id"]:
        admin_id = last_ticket["admin_id"]; db.add_rating(admin_id, score); db.add_log("rating", uid, admin_id, f"{score}⭐")
        reviewer = db.get_user(uid); reviewer_pseudo = reviewer["pseudo"] or f"ID{uid}"
        try:
            bot.send_message(admin_id, f"⭐ <b>Вам оставили отзыв!</b>\n━━━━━━━━━━━━━━━━━━\n👤 От: {reviewer_pseudo}\n⭐ Оценка: {stars} ({score}/5)\n🎫 Обращение: #{last_ticket['ticket_id']}")
        except: pass
    bot.edit_message_text(f"✔️ Оценка {stars} — спасибо!\n\n<i>Если понадобится — я здесь.</i>", call.message.chat.id, call.message.message_id)
    bot.send_message(uid, "Главное меню:", reply_markup=main_menu_kb()); bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "🔄 Сменить беса")
def btn_change(message):
    uid = message.from_user.id
    if is_banned(uid): return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
    t = db.get_open_ticket(uid)
    if not t: return bot.send_message(uid, "⚠️ Нет активного обращения.")
    kb = types.InlineKeyboardMarkup(row_width=1); kb.add(types.InlineKeyboardButton("❌ Да, сменить", callback_data="change_yes"), types.InlineKeyboardButton("🔵 Отмена", callback_data="change_no"))
    bot.send_message(uid, f"🔄 <b>Сменить беса?</b>\n\nТекущий администратор будет уведомлён, и к тебе назначат другого.\nОсталось смен сегодня: 3", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "change_no")
def cb_change_no(call): bot.edit_message_text("✔️ Отмена — администратор остался прежним.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "change_yes")
def cb_change_yes(call):
    uid = call.from_user.id
    if is_banned(uid): return bot.answer_callback_query(call.id, "Вы заблокированы")
    t = db.get_open_ticket(uid)
    if not t: return bot.answer_callback_query(call.id, "Нет активного обращения")
    old_admin = t["admin_id"]; db._exec("UPDATE tickets SET admin_id=NULL WHERE ticket_id=?", (t["ticket_id"],))
    u = db.get_user(uid); user_pseudo = u["pseudo"] or uid; old_admin_pseudo = admin_pseudo(old_admin) if old_admin else "(#не назначен)"
    try: bot.send_message(Config.SUPPORT_GROUP, f"🔄 Пользователь {user_pseudo} сменил беса\n👮 Старый: {old_admin_pseudo}")
    except: pass
    bot.edit_message_text("Вы успешно сменили администратора, ожидайте когда вам напишет новый администратор", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "👑 Позвать беса")
def btn_call(message):
    uid = message.from_user.id
    if is_banned(uid): return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
    t = db.get_open_ticket(uid)
    if not t: return bot.send_message(uid, "⚠️ Нет активного обращения.")
    u = db.get_user(uid)
    try: bot.send_message(Config.SUPPORT_GROUP, f"👑 <b>Пользователь зовёт беса</b>\n👤 Пользователь: {u['pseudo']}")
    except: pass
    bot.send_message(uid, "✅ Бес получил знак и скоро вернётся.")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.text == "⭐ Поставить оценку")
def btn_rating(message):
    uid = message.from_user.id
    if is_banned(uid): return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
    t = db.get_open_ticket(uid)
    if not t: return bot.send_message(uid, "⚠️ Нет активного обращения.")
    bot.send_message(uid, "⭐ Выбери оценку:", reply_markup=rating_kb())

@bot.message_handler(commands=["help"])
def cmd_help(message):
    if message.chat.type == "private" and is_banned(message.from_user.id): return
    uid = message.from_user.id; r = rank_of(uid); text = "📖 <b>Команды</b>\n\n👤 Для всех:\n/start /help /stats /close /rules /info\n\n"
    if r >= 1: text += "🛠 Ранг 1+:\n/check (reply)\n/staff\n\n"
    if r >= 5: text += "🧑‍💼 Ранг 5+:\n/setrole @user N #ник\n/removerole @user\n/ban /unban /warn /unwarn /kick /mute /unmute\n\n"
    if r >= 8: text += "👑 Ранг 8+:\n/broadcast /logs /botstats\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    if message.chat.type == "private" and is_banned(message.from_user.id): return
    uid = message.from_user.id; arg = message.text.partition(" ")[2].strip()
    if arg or message.reply_to_message:
        if rank_of(uid) < 1: return bot.reply_to(message, "❌ Недостаточно прав!")
        target = resolve_user(message, arg)
        if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    else: target = uid
    u = db.get_user(target); rating = db.rating_str(target)
    text = f"📊 <b>Профиль</b>\n━━━━━━━━━━━━━━━━━━\n🆔 <code>{target}</code>\n👤 <b>Имя:</b> {nick_tg(target)}\n🔗 <b>Username:</b> {safe_username(target)}\n🎖 <b>Ранг:</b> {rank_label(u['rank'])}\n📛 <b>Псевдоним:</b> {u['nickname'] or u['pseudo'] or '—'}\n⭐ <b>Рейтинг:</b> {rating}\n💬 <b>Сообщений:</b> {u['messages']}\n⚠️ <b>Варнов:</b> {u['warns']}"
    bot.reply_to(message, text)

@bot.message_handler(commands=["staff"])
def cmd_staff(message):
    if message.chat.type == "private" and is_banned(message.from_user.id): return
    if rank_of(message.from_user.id) < 1: return bot.reply_to(message, "❌ Недостаточно прав!")
    admins = db.get_all_admins()
    if not admins: return bot.reply_to(message, "📭 В составе пока никого нет.")
    text = "🖤 <b>Состав администрации</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for a in admins:
        uid = a["user_id"]; username = f"@{a['username']}" if a["username"] else "без username"; pseudo = a["nickname"] or "—"; rank_name = "Разработчик" if uid == Config.DEVELOPER_ID else RANKS.get(a["rank"], "—"); rating = db.rating_str(uid)
        text += f"👤 <b>{username}</b>\n📛 Псевдоним: {pseudo}\n🎖 Должность: {rank_name}\n⭐ Рейтинг: {rating}\n━━━━━━━━━━━━━━━━━━\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=["rules"])
def cmd_rules(message):
    if message.chat.type == "private" and is_banned(message.from_user.id): return
    bot.reply_to(message, f"📜 <a href='{Config.RULES_URL}'>Правила</a>")

@bot.message_handler(commands=["info"])
def cmd_info(message):
    if message.chat.type == "private" and is_banned(message.from_user.id): return
    bot.reply_to(message, "🤖 Бот анонимной поддержки «Разговоры по душам».")

@bot.message_handler(commands=["close"])
def cmd_close(message):
    if message.chat.id == Config.SUPPORT_GROUP and message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id != bot.get_me().id: return
        r = db.get_reply(rt.message_id)
        if not r: return
        target = r["user_id"]; tid = r["ticket_id"]
        db.close_ticket(tid); u = db.get_user(target)
        try: bot.send_message(target, "🔚 <b>Обращение закрыто</b>\n\nГлавное меню:", reply_markup=main_menu_kb())
        except: pass
        bot.send_message(Config.SUPPORT_GROUP, f"🔚 <b>Обращение закрыто</b>\n━━━━━━━━━━━━━━━━━━\n👮 Бес: {admin_pseudo(message.from_user.id)}\n👤 Пользователь: {u['pseudo'] or target}")
        bot.reply_to(message, "✅ Обращение закрыто"); return
    if message.chat.type == "private":
        uid = message.from_user.id
        if is_banned(uid): return bot.send_message(uid, "🚫 Вы заблокированы в боте.")
        t = db.get_open_ticket(uid)
        if t: db.close_ticket(t["ticket_id"]); bot.send_message(uid, "🔚 Обращение закрыто.", reply_markup=main_menu_kb())
        else: bot.send_message(uid, "❌ Нет активного обращения.")

@bot.message_handler(commands=["check"])
def cmd_check(message):
    if rank_of(message.from_user.id) < db.get_perm("check", 1): return bot.reply_to(message, "❌ Недостаточно прав!")
    if not message.reply_to_message: return bot.reply_to(message, "Ответьте этой командой на сообщение")
    target = resolve_user(message, "")
    if not target: return
    u = db.get_user(target); rating = db.rating_str(target)
    bot.reply_to(message, f"🔍 <b>Инфо</b>\n👤 Ник: {nick_tg(target)}\n🔗 Username: {safe_username(target)}\n🆔 <code>{target}</code>\n🎖 Ранг: {rank_label(u['rank'])}\n📛 Псевдоним: {u['nickname'] or u['pseudo'] or '—'}\n⭐ Рейтинг: {rating}")

@bot.message_handler(commands=["setrole"])
def cmd_setrole(message):
    if not check_access(message, db.get_perm("setrole", Config.MIN_SETROLE)): return
    text = message.text.partition(" ")[2].strip(); target, rank, nickname = None, None, None
    if message.reply_to_message:
        target = resolve_user(message, ""); parts = text.split(maxsplit=1)
        if not parts: return bot.reply_to(message, "Выберите номер ранга (1-8) или 100")
        try: rank = int(parts[0])
        except ValueError: return bot.reply_to(message, "❌ Ранг 1–8 или 100")
        if len(parts) > 1 and parts[1].strip().startswith("#"): nickname = parts[1].strip()[1:]
    else:
        parts = text.split(maxsplit=2)
        if not parts: return bot.reply_to(message, "Укажите @user / ID / reply")
        target = resolve_user(message, parts[0])
        if not target: return bot.reply_to(message, "Пользователь не найден")
        if len(parts) < 2: return bot.reply_to(message, "Укажите ранг (1-8) или 100")
        try: rank = int(parts[1])
        except ValueError: return bot.reply_to(message, "❌ Ранг 1–8 или 100")
        if len(parts) > 2 and parts[2].strip().startswith("#"): nickname = parts[2].strip()[1:]
    if not nickname: return bot.reply_to(message, "Укажите #псевдоним")
    if not ((1 <= rank <= 8) or rank == 100): return bot.reply_to(message, "❌ Ранг 1–8 или 100")
    if rank == 100 and message.from_user.id != Config.DEVELOPER_ID: return bot.reply_to(message, "❌ Только разработчик может выдать ранг 100")
    my = rank_of(message.from_user.id)
    if rank >= my and message.from_user.id != Config.DEVELOPER_ID: return bot.reply_to(message, "❌ Нельзя выдать ранг выше своего")
    db.set_rank(target, rank, nickname); db.add_log("setrole", message.from_user.id, target, f"rank={rank} nick={nickname}")
    bot.reply_to(message, f"👮 Администратор {safe_username(message.from_user.id)} ({nick_tg(message.from_user.id)}) назначил {RANKS.get(rank, 'Неизвестно')} {safe_username(target)} ({nick_tg(target)})")
    try: bot.send_message(target, f"Вас назначили на {RANKS.get(rank, 'Неизвестно')} с псевдонимом #{nickname}")
    except: pass

@bot.message_handler(commands=["removerole"])
def cmd_removerole(message):
    if not check_access(message, db.get_perm("removerole", Config.MIN_REMOVEROLE)): return
    arg = message.text.partition(" ")[2].strip(); target = resolve_user(message, arg)
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    old_rank = RANKS.get(db.get_user(target)["rank"], "—"); db.remove_role(target); db.add_log("removerole", message.from_user.id, target, f"old_rank={old_rank}")
    bot.reply_to(message, f"👮 Администратор {safe_username(message.from_user.id)} ({nick_tg(message.from_user.id)}) снял роль с {safe_username(target)} ({nick_tg(target)})\n🎭 Бывший ранг: {old_rank}")
    try: bot.send_message(target, f"С вас сняли роль.\nБывший ранг: {old_rank}")
    except: pass

@bot.message_handler(commands=["ban"])
def cmd_ban(message):
    if not check_access(message, db.get_perm("ban", Config.MIN_BAN)): return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_ban(target, 1, "по решению администрации"); db.add_log("ban", message.from_user.id, target)
    bot.reply_to(message, f"🚫 {nick_tg(target)} забанен")
    try: bot.send_message(target, "🚫 Вы заблокированы в боте.")
    except: pass

@bot.message_handler(commands=["unban"])
def cmd_unban(message):
    if not check_access(message, db.get_perm("unban", Config.MIN_UNBAN)): return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_ban(target, 0, ""); db.add_log("unban", message.from_user.id, target)
    bot.reply_to(message, f"✅ {nick_tg(target)} разбанен")
    try: bot.send_message(target, "✅ Вы разблокированы.")
    except: pass

@bot.message_handler(commands=["warn"])
def cmd_warn(message):
    if not check_access(message, db.get_perm("warn", Config.MIN_WARN)): return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    u = db.get_user(target); warns = (u["warns"] or 0) + 1; db.set_warns(target, warns)
    bot.reply_to(message, f"⚠️ {nick_tg(target)} — варн {warns}/3")
    if warns >= 3:
        db.set_ban(target, 1, "3 варна")
        try: bot.send_message(Config.SUPPORT_GROUP, f"🚫 Автобан {nick_tg(target)} за 3 варна")
        except: pass

@bot.message_handler(commands=["unwarn"])
def cmd_unwarn(message):
    if not check_access(message, db.get_perm("unwarn", Config.MIN_UNWARN)): return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    u = db.get_user(target); warns = max(0, (u["warns"] or 0) - 1); db.set_warns(target, warns)
    bot.reply_to(message, f"✅ Варн снят, осталось: {warns}")

@bot.message_handler(commands=["kick"])
def cmd_kick(message):
    if not check_access(message, db.get_perm("kick", Config.MIN_KICK)): return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_ban(target, 1, "кик"); bot.reply_to(message, f"👢 {nick_tg(target)} кикнут")

@bot.message_handler(commands=["mute"])
def cmd_mute(message):
    if not check_access(message, db.get_perm("mute", Config.MIN_MUTE)): return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_user(target, muted_until=time.time() + 3600); bot.reply_to(message, f"🔇 {nick_tg(target)} замучен на 1 час")

@bot.message_handler(commands=["unmute"])
def cmd_unmute(message):
    if not check_access(message, db.get_perm("unmute", Config.MIN_UNMUTE)): return
    target = resolve_user(message, message.text.partition(" ")[2].strip())
    if not target: return bot.reply_to(message, "❌ Пользователь не найден")
    db.set_user(target, muted_until=0); bot.reply_to(message, f"🔊 {nick_tg(target)} размучен")

@bot.message_handler(commands=["botstats"])
def cmd_botstats(message):
    if rank_of(message.from_user.id) < db.get_perm("botstats", Config.MIN_BOTSTATS): return bot.reply_to(message, "❌ Недостаточно прав!")
    s = db.get_stats(); me = bot.get_me()
    bot.reply_to(message, f"📊 <b>Статистика</b>\n━━━━━━━━━━━━━━━━━━\n🤖 @{me.username}\n👥 Всего: <b>{s['total']}</b>\n👮 Админов: <b>{s['admins']}</b>\n🟢 Активных: <b>{s['active']}</b>\n🚫 Забанено: <b>{s['banned']}</b>\n✉️ Сообщений: <b>{s['total_messages']}</b>\n⚠️ Варнов: <b>{s['total_warns']}</b>")

@bot.message_handler(commands=["logs"])
def cmd_logs(message):
    if rank_of(message.from_user.id) < db.get_perm("logs", Config.MIN_LOGS): return bot.reply_to(message, "❌ Недостаточно прав!")
    rows = db.get_logs(20)
    if not rows: return bot.reply_to(message, "📭 Логов нет")
    text = "📋 <b>Последние действия</b>\n━━━━━━━━━━━━━━━━━━\n"
    for r in rows: text += f"• {r['date']} | {r['action']}\n"
    bot.reply_to(message, text)

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    if rank_of(message.from_user.id) < db.get_perm("broadcast", Config.MIN_BROADCAST): return bot.reply_to(message, "❌ Недостаточно прав!")
    text = message.text.partition(" ")[2].strip()
    if not text: return bot.reply_to(message, "Формат: /broadcast [текст]")
    users = db.get_all_users(); sent, failed = 0, 0
    for u in users:
        try: bot.send_message(u["user_id"], f"📢 {text}"); sent += 1; time.sleep(0.05)
        except: failed += 1
    bot.reply_to(message, f"✅ Отправлено: {sent}, ошибок: {failed}")

@bot.message_handler(content_types=["text", "photo", "video", "animation", "voice", "sticker", "video_note", "document", "audio"])
def handle_messages(message):
    chat = message.chat.id; uid = message.from_user.id
    if message.text and message.text.startswith("/"): return
    if chat == Config.SUPPORT_GROUP and message.reply_to_message:
        rt = message.reply_to_message
        if rt.from_user.id != bot.get_me().id: return
        r = db.get_reply(rt.message_id)
        if not r: return
        target = r["user_id"]; admin_id = uid
        try:
            bot.send_message(target, f"📩 <b>Новое сообщение</b>\nОт администратора\n👮 {admin_pseudo(admin_id)}")
            bot.copy_message(target, chat, message.message_id)
        except Exception as e: bot.reply_to(message, f"❌ Не доставлено: {e}")
        return
    if message.chat.type == "private":
        u = db.get_user(uid)
        if u["banned"]:
            try: bot.send_message(uid, "🚫 Вы заблокированы в боте.")
            except: pass
            return
        if is_flood(uid): return
        if message.from_user.username: db.set_user(uid, username=message.from_user.username)
        db.set_user(uid, messages=(u["messages"] or 0) + 1)
        t = db.get_open_ticket(uid)
        if t:
            try:
                admin_nick = admin_pseudo(t["admin_id"]) if t["admin_id"] else "(#не назначен)"
                sent = bot.send_message(Config.SUPPORT_GROUP, f"📩 <b>Сообщение от {u['pseudo'] or uid}</b>\n━━━━━━━━━━━━━━━━━━\n🆔 <code>{uid}</code>\n👮 Администратор пользователя: {admin_nick}")
                bot.copy_message(Config.SUPPORT_GROUP, chat, message.message_id); db.save_reply(sent.message_id, uid, t["ticket_id"])
            except Exception as e: print(f"[forward] {e}")
            return

if __name__ == "__main__":
    print("🤖 Бот запущен...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
