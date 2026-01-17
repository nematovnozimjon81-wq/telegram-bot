from telebot import TeleBot, types
import sqlite3
import time
import uuid
import os
from flask import Flask
from threading import Thread


TOKEN = os.getenv("TOKEN")
from html import escape  # <-- shu qatorda qo‘shiladi
# =========================
# CONFIG
# =========================
ADMIN_ID = 8066401832
WEB_APP_URL = "https://bxpoff.netlify.app/"

bot = TeleBot(TOKEN, parse_mode="HTML")
admin_add_stars = {}
admin_broadcast = set()
admin_force = {}
waiting_for_amount = set()
waiting_for_check = set()
waiting_for_contact = set()
MIN_PAYMENT = 2000

temp_amount = {}
# =========================
# DATABASE
# =========================
def get_db():
    return sqlite3.connect("bot.db", check_same_thread=False)

with get_db() as db:
    cur = db.cursor()
    
    # Majburiy obuna kanali
    cur.execute("""
    CREATE TABLE IF NOT EXISTS force_sub (
        channel TEXT
    )
    """)
    
    # Foydalanuvchilar
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        stars INTEGER DEFAULT 0,
        balance INTEGER DEFAULT 0,
        referer_id INTEGER,
        last_daily INTEGER DEFAULT 0
    )
    """)

    # To‘lovlar (payment)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        pid TEXT PRIMARY KEY,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'pending'
    )
    """)

    # Referallar (ixtiyoriy, lekin keyin qo‘shish mumkin)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS referrals (
        user_id INTEGER,
        referer_id INTEGER
    )
    """)

    db.commit()


# =========================
# FORCE SUB CHECK
# =========================
def check_sub(user_id):
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT channel FROM force_sub")
        row = cur.fetchone()

    if not row:
        return True

    channel = row[0].strip()
    if channel.startswith("https://t.me/"):
        channel = "@" + channel.split("/")[-1]

    try:
        member = bot.get_chat_member(channel, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"check_sub error: {e}")
        return False

# =========================
# ADMIN MENU
# =========================
def admin_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⭐ Stars qo‘shish / ayirish", callback_data="admin_stars"),
        types.InlineKeyboardButton("📢 Hammaga xabar", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("📢 Majburiy obuna", callback_data="admin_force")
    )
    return kb

@bot.message_handler(commands=["admin"])
def admin_cmd(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Siz admin emassiz")
        return

    bot.send_message(
        message.chat.id,
        "🎛 <b>ADMIN PANEL</b>",
        reply_markup=admin_menu()
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("force_"))
def force_handler(call):
    if call.from_user.id != ADMIN_ID:
        return

    if call.data == "force_add":
        bot.send_message(call.from_user.id, "📎 Kanal linkini yuboring:")
        admin_force["add"] = True

    elif call.data == "force_remove":
        with get_db() as db:
            cur = db.cursor()
            cur.execute("DELETE FROM force_sub")
            db.commit()
        bot.send_message(call.from_user.id, "❌ Majburiy obuna olib tashlandi")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_"))
def admin_callbacks(call):
    uid = call.from_user.id
    if uid != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo‘q")
        return

    if call.data == "admin_stars":
        bot.send_message(
            uid,
            "✍️ Format yuboring:\n"
            "<code>user_id +10</code> yoki <code>user_id -5</code>"
        )
        admin_add_stars[uid] = True

    elif call.data == "admin_broadcast":
        bot.send_message(uid, "📢 Hammaga yuboriladigan xabarni yozing:")
        admin_broadcast.add(uid)

    elif call.data == "admin_force":
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("➕ Qo‘shish", callback_data="force_add"),
            types.InlineKeyboardButton("➖ O‘chirish", callback_data="force_remove")
        )
        bot.send_message(uid, "📢 Majburiy obuna:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_text(message):
    uid = message.from_user.id
    text = message.text.strip()

    with get_db() as db:
        cur = db.cursor()

        # ⭐ STARS QO‘SHISH / AYIRISH
        if uid in admin_add_stars:
            try:
                user_id, amount = text.split()
                user_id = int(user_id)
                amount = int(amount)
                # Agar foydalanuvchi bazada bo‘lmasa qo‘shish
                cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
                cur.execute(
                    "UPDATE users SET stars = stars + ? WHERE user_id=?",
                    (amount, user_id)
                )
                db.commit()
                bot.send_message(uid, "✅ Stars muvaffaqiyatli o‘zgartirildi")
            except:
                bot.send_message(uid, "❌ Format xato. Misol: 123456 +5")
            admin_add_stars.pop(uid, None)

        # 📢 HAMMAGA XABAR
        elif uid in admin_broadcast:
            cur.execute("SELECT user_id FROM users")
            all_users = cur.fetchall()
            sent = 0
            for (u,) in all_users:
                try:
                    bot.send_message(u, text)
                    sent += 1
                except:
                    pass
            bot.send_message(uid, f"📢 {sent} ta userga yuborildi")
            admin_broadcast.remove(uid)

        # 📢 MAJBURIY OBUNA QO‘SHISH
        elif admin_force.get("add"):
            cur.execute("DELETE FROM force_sub")
            cur.execute("INSERT INTO force_sub (channel) VALUES (?)", (text,))
            db.commit()
            bot.send_message(uid, "✅ Majburiy obuna qo‘shildi")
            admin_force.clear()

# =========================
# MAIN MENU
# =========================
def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🛍 Xizmatlar", web_app=types.WebAppInfo(url=WEB_APP_URL))
    )
    kb.add(
        types.InlineKeyboardButton("💳 Hisob", callback_data="account"),
        types.InlineKeyboardButton("⭐ Stars olish", callback_data="buy_stars")
    )
    kb.add(
        types.InlineKeyboardButton("💎 Premium olish", callback_data="Premium"),
        types.InlineKeyboardButton("💲 Hisob toldirish", callback_data="payment_warning")
    )
    kb.add(
        types.InlineKeyboardButton("🎁 Kunlik bonus", callback_data="daily"),
        types.InlineKeyboardButton("🔗 Referal", callback_data="referal")
    )
    return kb

# =========================
# STARS MENU
# =========================
def stars_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("15 💝", callback_data="stars_15_💝"),
        types.InlineKeyboardButton("15 🧸", callback_data="stars_15_🧸")
    )
    kb.add(
        types.InlineKeyboardButton("25 🎁", callback_data="stars_25_🎁"),
        types.InlineKeyboardButton("25 🌹", callback_data="stars_25_🌹")
    )
    kb.add(
        types.InlineKeyboardButton("50 🚀", callback_data="stars_50_🚀"),
        types.InlineKeyboardButton("50 🍾", callback_data="stars_50_🍾")
    )
    kb.add(
        types.InlineKeyboardButton("100 💎", callback_data="stars_100_💎")
    )
    return kb

# =========================
# START + REFERAL
# =========================
# =========================
# START + REFERAL
# =========================
@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    name = escape(message.from_user.first_name)
    args = message.text.split()
    referer_id = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    with get_db() as db:
        cur = db.cursor()
        cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))

    # Majburiy kanalni tekshirish
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT channel FROM force_sub")
        row = cur.fetchone()
        channel = row[0] if row else None

    if channel:
        # Agar kanal username ko‘rinishda bo‘lsa, to‘g‘ri linkga aylantirish
        if channel.startswith("@"):
            channel_url = f"https://t.me/{channel[1:]}"
        elif channel.startswith("https://t.me/"):
            channel_url = channel
        else:
            channel_url = f"https://t.me/{channel}"  # fallback

        if not check_sub(uid):
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📢 Kanalga obuna bo‘lish", url=channel_url))
            kb.add(types.InlineKeyboardButton("✅ Obunani tekshirish", callback_data=f"check_sub_{referer_id}"))

            bot.send_message(
                uid,
                "❗ Botdan foydalanish uchun kanalga obuna bo‘ling",
                reply_markup=kb
            )
            return  # ← shu yerda END qilamiz, keyingi kod ishlamaydi

    # Agar foydalanuvchi obuna bo‘lsa → referal bonus va MAIN MENU
    give_referal_bonus(uid, referer_id)
    bot.send_message(
        uid,
        f"👋 Salom <b>{name}</b>!\nXush kelibsiz 🚀",
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda c: c.data == "payment_warning")
def payment_warning(call):
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Ha", callback_data="payment_confirm"),
        types.InlineKeyboardButton("❌ Yo‘q", callback_data="payment_cancel")
    )
    bot.send_message(
        uid,
        "⚠️ Diqqat! Bu faqat O‘qish kursi yoki Premium uchun to‘lovdir.\n"
        "Shuni davom ettirmoqchimisiz?",
        reply_markup=kb
    )
@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_"))
def admin_payment_handler(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo‘q")
        return
    handle_admin_payment(call)

@bot.callback_query_handler(func=lambda c: c.data in ["payment_confirm", "payment_cancel"])
def payment_confirm_or_cancel(call):
    uid = call.from_user.id
    if call.data == "payment_confirm":
        waiting_for_amount.add(uid)
        bot.send_message(
            uid,
            f"💳 To‘lov ma’lumotlari:\n\n"
            f"🏦 Karta: `9860 0803 8652 9814`\n"
            f"👤 Ism: **E.Polvonova**\n"
            f"💵 Minimal: {MIN_PAYMENT} so‘m\n\n"
            f"💰 To‘lov summasini kiriting:"
        )
    else:
        bot.send_message(uid, "❌ To‘lov bekor qilindi", reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.from_user.id in waiting_for_amount)
def payment_amount(message):
    uid = message.from_user.id

    if not message.text.isdigit():
        bot.send_message(uid, "❌ Faqat raqam kiriting")
        return

    amount = int(message.text)
    if amount < MIN_PAYMENT:
        bot.send_message(uid, f"❌ Minimal summa {MIN_PAYMENT} so‘m")
        return

    waiting_for_amount.remove(uid)
    waiting_for_check.add(uid)
    temp_amount[uid] = amount

    bot.send_message(uid, "📸 Endi chek screenshotini yuboring")

# =========================
# PAYMENT PHOTO
# =========================
@bot.message_handler(content_types=["photo"])
def payment_photo(message):
    uid = message.from_user.id
    if uid not in waiting_for_check:
        return

    waiting_for_check.remove(uid)
    amount = temp_amount.pop(uid)
    pid = str(uuid.uuid4())

    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO payments VALUES (?, ?, ?, 'pending')",
            (pid, uid, amount)
        )
        db.commit()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ OK", callback_data=f"pay_ok_{pid}"),
        types.InlineKeyboardButton("❌ NO", callback_data=f"pay_no_{pid}")
    )

    bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=f"🧾 TO‘LOV\n👤 ID {uid}\n💰 {amount} so‘m",
        reply_markup=kb
    )

    bot.send_message(uid, "⏳ Chek adminga yuborildi", reply_markup=main_menu())
# PREMIUM INLINE MENU
@bot.callback_query_handler(func=lambda c: c.data == "Premium")
def premium_menu(call):
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("Akkauntga kirib", callback_data="premium_self"),
        types.InlineKeyboardButton("Hadya qilib", callback_data="premium_gift")
    )
    bot.send_message(uid, "💎 Premium tanlang:", reply_markup=kb)

# AKKAUNTGA KIRIB
@bot.callback_query_handler(func=lambda c: c.data == "premium_self")
def premium_self_menu(call):
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("1 oy - 45 000 so‘m", callback_data="premium_self_1m")
    )
    bot.send_message(uid, "💎 Akkauntga Premium:", reply_markup=kb)

# HADYA QILIB
@bot.callback_query_handler(func=lambda c: c.data == "premium_gift")
def premium_gift_menu(call):
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("3 oy - 180 000 so‘m", callback_data="premium_gift_3m"),
        types.InlineKeyboardButton("6 oy - 240 000 so‘m", callback_data="premium_gift_6m"),
        types.InlineKeyboardButton("12 oy - 320 000 so‘m", callback_data="premium_gift_12m")
    )
    bot.send_message(uid, "💎 Hadya qilib Premium:", reply_markup=kb)

# MISOL: TO‘LOV CALLBACK (KEYIN ADMIN CHECK YOKI WEBAPP LINK)
# =========================
# PREMIUM INLINE MENU
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "Premium")
def premium_menu(call):
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("Akkauntga kirib", callback_data="premium_self"),
        types.InlineKeyboardButton("Hadya qilib", callback_data="premium_gift")
    )
    bot.send_message(uid, "💎 Premium tanlang:", reply_markup=kb)


# =========================
# AKKAUNTGA KIRIB MENU
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "premium_self")
def premium_self_menu(call):
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("1 oy - 45 000 so‘m", callback_data="premium_self_1m")
    )
    bot.send_message(uid, "💎 Akkauntga Premium:", reply_markup=kb)


# =========================
# HADYA QILIB MENU
# =========================
@bot.callback_query_handler(func=lambda c: c.data == "premium_gift")
def premium_gift_menu(call):
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("3 oy - 180 000 so‘m", callback_data="premium_gift_3m"),
        types.InlineKeyboardButton("6 oy - 240 000 so‘m", callback_data="premium_gift_6m"),
        types.InlineKeyboardButton("12 oy - 320 000 so‘m", callback_data="premium_gift_12m")
    )
    bot.send_message(uid, "💎 Hadya qilib Premium:", reply_markup=kb)

# =========================
# PREMIUM TO‘LOV CALLBACK
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("premium_"))
def premium_payment(call):
    uid = call.from_user.id
    code = call.data

    prices = {
        "premium_self_1m": 45000,
        "premium_gift_3m": 180000,
        "premium_gift_6m": 240000,
        "premium_gift_12m": 320000
    }

    plans = {
        "premium_self_1m": "1 oy (akkauntga)",
        "premium_gift_3m": "3 oy (hadya)",
        "premium_gift_6m": "6 oy (hadya)",
        "premium_gift_12m": "12 oy (hadya)"
    }

    amount = prices.get(code)
    plan_text = plans.get(code)
    if amount is None:
        return

    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
        balance = row[0] if row else 0

    if balance < amount:
        bot.send_message(
            uid,
            f"❌ <b>Balans yetarli emas!</b>\n\n"
            f"💰 Sizda: {balance} so‘m\n"
            f"💵 Kerak: {amount} so‘m",
            reply_markup=main_menu()
        )
        return

    # ✅ BALANSDAN YECHISH
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=?",
            (amount, uid)
        )
        db.commit()

    # ✅ USERGA XABAR
    bot.send_message(
        uid,
        f"🎉 <b>Premium muvaffaqiyatli faollashtirildi!</b>\n\n"
        f"💎 Plan: {plan_text}\n"
        f"💰 {amount} so‘m balansingizdan yechildi\n"
        f"💳 Qolgan balans: {balance - amount} so‘m\n\n"
        "⏳ Admin tekshiruvdan so‘ng Premium to‘liq ishga tushadi.",
        reply_markup=main_menu()
    )

    # ✅ ADMIN XABARI
    user = call.from_user
    if user.username:
        user_text = f"@{user.username}"
    else:
        user_text = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'

    bot.send_message(
        ADMIN_ID,
        f"👤 <b>Foydalanuvchi Premium oldi!</b>\n\n"
        f"👥 User: {user_text}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💎 Plan: {plan_text}\n"
        f"💰 Summasi: {amount} so‘m\n"
        f"✅ Balansdan yechildi",
        parse_mode="HTML"
    )

# =========================
# ADMIN PAYMENT CONFIRM
# =========================
# =========================
# ADMIN PAYMENT CONFIRM
# =========================
def handle_admin_payment(call):
    _, action, pid = call.data.split("_", 2)

    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT user_id, amount, status FROM payments WHERE pid=?", (pid,))
        pay = cur.fetchone()

        if not pay:
            bot.answer_callback_query(call.id, "⚠️ To‘lov topilmadi!")
            return

        user_id, amount, status = pay

        if status != "pending":
            bot.answer_callback_query(call.id, "⚠️ Bu to‘lov allaqachon tasdiqlangan")
            return

        if action == "ok":
            # ✅ Balansga qo‘shish
            cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
            cur.execute("UPDATE payments SET status='ok' WHERE pid=?", (pid,))
            db.commit()

            # Foydalanuvchining yangi balansini olish
            cur.execute("SELECT balance, stars FROM users WHERE user_id=?", (user_id,))
            balance, stars = cur.fetchone()

            bot.send_message(
                user_id,
                f"✅ To‘lov muvaffaqiyatli amalga oshirildi!\n"
                f"💰 Balans: {balance} so‘m\n"
                f"⭐ Stars: {stars}",
                reply_markup=main_menu()
            )

            bot.edit_message_caption(
                caption=f"✅ TASDIQLANDI\n👤 ID: {user_id}\n💰 {amount} so‘m",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )

        elif action == "no":
            cur.execute("UPDATE payments SET status='rejected' WHERE pid=?", (pid,))
            db.commit()

            bot.send_message(
                user_id,
                "❌ To‘lov rad etildi.",
                reply_markup=main_menu()
            )

            bot.edit_message_caption(
                caption=f"❌ RAD ETILDI\n👤 ID: {user_id}\n💰 {amount} so‘m",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )

        bot.answer_callback_query(call.id)

# =========================
# CHECK SUB CALLBACK
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("check_sub"))
def check_sub_callback(call):
    uid = call.from_user.id
    data_parts = call.data.split("_")
    referer_id = int(data_parts[2]) if len(data_parts) > 2 and data_parts[2].isdigit() else None

    if check_sub(uid):
        give_referal_bonus(uid, referer_id)
        bot.send_message(uid, "✅ Siz kanalga obuna bo‘ldingiz! Endi botdan foydalanishingiz mumkin.", reply_markup=main_menu())
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali kanalga obuna bo‘lmagansiz.")

# =========================
# REFERAL BONUS FUNKSIYASI
# =========================
def give_referal_bonus(uid, referer_id):
    if not referer_id:
        return

    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT referer_id FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
        saved_ref = row[0] if row else None

        if saved_ref is None and referer_id != uid:
            cur.execute("UPDATE users SET referer_id=? WHERE user_id=?", (referer_id, uid))
            cur.execute("UPDATE users SET stars = stars + 3 WHERE user_id=?", (referer_id,))
            db.commit()
            bot.send_message(
                referer_id,
                "👥 Yangi referal!\n⭐ Sizga +3 Stars berildi"
            )

# =========================
# CALLBACKS
# =========================
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    uid = call.from_user.id
    name = call.from_user.first_name

    with get_db() as db:
        cur = db.cursor()

        # HISOB
        if call.data == "account":
            cur.execute("SELECT stars, balance FROM users WHERE user_id=?", (uid,))
            row = cur.fetchone()
            stars = row[0] if row else 0
            balance = row[1] if row else 0

            bot.send_message(
                uid,
                f"👤 <b>Ism:</b> {name}\n"
                f"🆔 <b>ID:</b> {uid}\n"
                f"⭐ <b>Stars:</b> {stars}\n"
                f"💰 <b>Balans:</b> {balance} so‘m"
            )

        # STARS OLISH
        elif call.data == "buy_stars":
            bot.send_message(uid, "⭐ Qaysi starsni olmoqchisiz?", reply_markup=stars_menu())

        # KUNLIK BONUS
        elif call.data == "daily":
            # ⚡ Adminni kanal tekshiruvdan ozod qilish
            if uid != ADMIN_ID and not check_sub(uid):
                bot.send_message(uid, "❌ Kunlik bonus olish uchun kanalga obuna bo‘ling!")
                return

            with get_db() as db:
                cur = db.cursor()
                cur.execute("SELECT last_daily FROM users WHERE user_id=?", (uid,))
                row = cur.fetchone()
                last = row[0] if row and row[0] else 0  # None bo'lsa 0 qiling
                now = int(time.time())

                if now - last >= 86400:
                    cur.execute(
                        "UPDATE users SET stars = stars + 1, last_daily=? WHERE user_id=?",
                        (now, uid)
                    )
                    db.commit()
                    bot.send_message(uid, "🎁 Sizga +1 ⭐ Stars berildi!")
                else:
                    remaining = 86400 - (now - last)
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60
                    bot.send_message(uid, f"⏳ Kunlik bonus hali olinmagan.\nKeyingi bonus: {hours} soat {minutes} minutdan keyin.")

        # REFERAL
        elif call.data == "referal":
            link = f"https://t.me/{bot.get_me().username}?start={uid}"
            bot.send_message(
                uid,
                f"🔗 <b>Referal havolang:</b>\n{link}\n\n"
                "👥 Har bir referal = ⭐ 3 Stars"
            )

        # STARS BUY CHECK
        elif call.data.startswith("stars_"):
            _, amount, emoji = call.data.split("_")
            amount = int(amount)

            cur.execute("SELECT stars FROM users WHERE user_id=?", (uid,))
            row = cur.fetchone()
            user_stars = row[0] if row else 0

            if user_stars >= amount:
                cur.execute("UPDATE users SET stars = stars - ? WHERE user_id=?", (amount, uid))
                db.commit()
                bot.send_message(
                    uid,
                    f"✅ <b>Muvaffaqiyatli!</b>\n"
                    f"{amount} ⭐ Stars ({emoji}) buyurtma qilindi.\n"
                    "📦 Yaqin orada yuboriladi."
                )
                # ADMIN XABAR
                bot.send_message(
                    ADMIN_ID,
                    f"🛒 <b>Yangi buyurtma!</b>\n\n"
                    f"👤 Ism: {name}\n"
                    f"🆔 ID: {uid}\n"
                    f"⭐ Stars: {amount} {emoji}"
                )
            else:
                bot.send_message(
                    uid,
                    f"❌ Yetarli stars yo‘q!\n"
                    f"Sizda: {user_stars} ⭐\n"
                    f"Kerak: {amount} ⭐"
                )
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run_web():
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_web).start()

# =========================
# RUN
# =========================
print("🤖 Bot ishga tushdi...")
bot.infinity_polling()
