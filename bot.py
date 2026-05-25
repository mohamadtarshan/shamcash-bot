import telebot
import sqlite3
import os

# ------------------ الإعدادات ------------------
TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
DEPOSIT_FEE = 0.5
WITHDRAW_FEE = 0.5
USDT_RATE = 14000

bot = telebot.TeleBot(TOKEN)

# ------------------ قاعدة البيانات ------------------
def init_db():
    conn = sqlite3.connect('wallet.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  shamcash_balance REAL DEFAULT 0,
                  usdt_balance REAL DEFAULT 0,
                  shamcash_wallet TEXT,
                  usdt_wallet TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  type TEXT,
                  amount REAL,
                  fee REAL,
                  currency TEXT,
                  status TEXT,
                  date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect('wallet.db')
    c = conn.cursor()
    c.execute(query, params)
    result = c.fetchone() if fetch else None
    conn.commit()
    conn.close()
    return result

init_db()

# ------------------ أوامر البوت الأساسية ------------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "بدون يوزر"
    user = db_execute("SELECT user_id FROM users WHERE user_id=?", (user_id,), fetch=True)
    if user is None:
        db_execute("INSERT INTO users (user_id, username) VALUES (?,?)", (user_id, username))
        welcome_text = "👋 أهلاً بك في بوت محفظة USDT ↔ شام كاش!\n\n"
        welcome_text += "🎉 تم إنشاء حسابك.\n\n"
        welcome_text += "📋 الأوامر المتاحة:\n"
        welcome_text += "/balance - عرض رصيدك\n"
        welcome_text += "/deposit - إيداع أموال\n"
        welcome_text += "/withdraw - سحب أموال\n"
        welcome_text += "/convert - تحويل عملات\n"
        welcome_text += "/help - مساعدة"
        bot.reply_to(message, welcome_text)
    else:
        bot.reply_to(message, "👋 أهلاً مجدداً!\nاكتب /balance لعرض رصيدك.")

@bot.message_handler(commands=['balance'])
def balance(message):
    user_id = message.from_user.id
    result = db_execute("SELECT shamcash_balance, usdt_balance FROM users WHERE user_id=?", (user_id,), fetch=True)
    if result:
        sham, usdt = result
        balance_text = "💰 *رصيدك الحالي:*\n\n"
        balance_text += f"💵 USDT: `{usdt:.2f}`\n"
        balance_text += f"📱 شام كاش: `{sham:.2f}` ل.س\n\n"
        balance_text += f"📊 سعر الصرف: 1 USDT = {USDT_RATE} ل.س"
        bot.send_message(message.chat.id, balance_text, parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ ليس لديك حساب. اكتب /start")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    help_text = "ℹ️ *المساعدة*\n\n"
    help_text += "🏦 *بوت محفظة USDT ↔ شام كاش*\n\n"
    help_text += f"📌 *العمولات:*\n• إيداع: {DEPOSIT_FEE}$\n• سحب: {WITHDRAW_FEE}$\n\n"
    help_text += "📋 *الأوامر:*\n/balance - الرصيد\n/deposit - إيداع\n/withdraw - سحب\n/convert - تحويل\n/help - مساعدة"
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['deposit'])
def deposit_menu(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    btn_usdt = telebot.types.InlineKeyboardButton("💵 USDT", callback_data="dep_usdt")
    btn_sham = telebot.types.InlineKeyboardButton("📱 شام كاش", callback_data="dep_sham")
    markup.add(btn_usdt, btn_sham)
    bot.send_message(message.chat.id, "📥 اختر عملة الإيداع:\n\n⚠️ عمولة الإيداع: 0.5$", reply_markup=markup)

@bot.message_handler(commands=['withdraw'])
def withdraw_menu(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    btn_usdt = telebot.types.InlineKeyboardButton("💵 USDT", callback_data="wit_usdt")
    btn_sham = telebot.types.InlineKeyboardButton("📱 شام كاش", callback_data="wit_sham")
    markup.add(btn_usdt, btn_sham)
    bot.send_message(message.chat.id, "📤 اختر عملة السحب:\n\n⚠️ عمولة السحب: 0.5$", reply_markup=markup)

@bot.message_handler(commands=['convert'])
def convert_menu(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("💵 USDT → 📱 شام كاش", callback_data="conv_u2s"),
        telebot.types.InlineKeyboardButton("📱 شام كاش → 💵 USDT", callback_data="conv_s2u")
    )
    bot.send_message(message.chat.id, "🔄 اختر اتجاه التحويل:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    bot.answer_callback_query(call.id, "الميزة غير مفعلة بعد ⚠️")

# ------------------ تشغيل البوت ------------------
print("✅ البوت يعمل الآن على السيرفر...")
bot.polling(non_stop=True)
