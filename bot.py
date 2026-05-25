import telebot
import sqlite3
import os
from telebot import types

# --- إعدادات USDT (Tron) ---
from tronpy import Tron
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider

# --- إعدادات الشام كاش ---
from shamcash import ShamCashAPISync

# ==================== الإعدادات ====================
TOKEN = os.environ.get('TELEGRAM_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))

# USDT
TRON_PRIVATE_KEY = os.environ.get('TRON_PRIVATE_KEY')
TRON_WALLET_ADDRESS = os.environ.get('TRON_WALLET_ADDRESS')
USDT_CONTRACT = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'

# شام كاش
SHAMCASH_API_TOKEN = os.environ.get('SHAMCASH_API_TOKEN')
SHAMCASH_ACCOUNT_ID = os.environ.get('SHAMCASH_ACCOUNT_ID')

# رسوم و تسعير
DEPOSIT_FEE = 0.5
WITHDRAW_FEE = 0.5
USDT_RATE = 14000

# ==================== قاعدة البيانات ====================
def init_db():
    conn = sqlite3.connect('wallet.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    shamcash_balance REAL DEFAULT 0,
                    usdt_balance REAL DEFAULT 0,
                    shamcash_wallet TEXT,
                    usdt_wallet TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

# ==================== دوال التحويل ====================
def send_usdt(to_address, amount):
    """إرسال USDT عبر شبكة Tron"""
    client = Tron(provider=HTTPProvider())
    priv_key = PrivateKey(bytes.fromhex(TRON_PRIVATE_KEY))
    contract = client.get_contract(USDT_CONTRACT)
    txn = (
        contract.functions.transfer(to_address, int(amount * 1_000_000))
        .with_owner(TRON_WALLET_ADDRESS)
        .fee_limit(1_000_000_000)
        .build()
        .sign(priv_key)
    )
    result = txn.broadcast()
    if result.get('result'):
        return result['txid']
    else:
        raise Exception(result.get('message', 'فشل إرسال USDT'))

def send_shamcash(phone_number, amount):
    """إرسال شام كاش إلى رقم هاتف"""
    with ShamCashAPISync(api_token=SHAMCASH_API_TOKEN) as client:
        # نرسل إلى رقم الهاتف مباشرة
        transaction = client.send_to_phone(
            account_id=SHAMCASH_ACCOUNT_ID,
            phone=phone_number,
            amount=amount
        )
        return transaction.id

# ==================== البوت ====================
bot = telebot.TeleBot(TOKEN)
init_db()

# ... (جميع أوامر /start, /balance, /help ... الخ كما هي)

# ==================== نظام الإيداع ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('dep_'))
def process_deposit(call):
    user_id = call.from_user.id
    currency = 'USDT' if 'usdt' in call.data else 'شام كاش'

    if currency == 'USDT':
        # إيداع USDT
        bot.edit_message_text(
            f"📥 لإيداع {currency}، أرسل المبلغ إلى عنوان المحفظة التالي:\n\n"
            f"`{TRON_WALLET_ADDRESS}`\n\n"
            f"⚠️ العمولة: {DEPOSIT_FEE}$\n\n"
            f"بعد إرسال المبلغ، أرسل لنا صورة الإيصال أو رابط العملية (txid).",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown'
        )
    else:
        # إيداع شام كاش
        bot.edit_message_text(
            f"📥 لإيداع {currency}، أرسل المبلغ إلى حساب الشام كاش التالي:\n\n"
            f"رقم الحساب: `{SHAMCASH_ACCOUNT_ID}`\n\n"
            f"⚠️ العمولة: {DEPOSIT_FEE}$\n\n"
            f"بعد إرسال المبلغ، أرسل لنا صورة الإيصال.",
            call.message.chat.id, call.message.message_id,
            parse_mode='Markdown'
        )

# ... (معالجة الردود على الإيصالات في الـ handler القادم)

# ==================== نظام السحب ====================
# (يستخدم حالات البوت لتخزين البيانات المؤقتة)
withdraw_data = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith('wit_'))
def request_withdraw_details(call):
    user_id = call.from_user.id
    currency = 'USDT' if 'usdt' in call.data else 'شام كاش'

    withdraw_data[user_id] = {'currency': currency}
    msg = bot.edit_message_text(
        f"📤 سحب {currency}\n\n"
        f"أدخل المبلغ الذي ترغب في سحبه (بالدولار):",
        call.message.chat.id, call.message.message_id
    )
    bot.register_next_step_handler(msg, process_withdraw_amount)

def process_withdraw_amount(message):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
    except ValueError:
        bot.reply_to(message, "❌ الرجاء إدخال رقم صحيح.")
        return

    data = withdraw_data.get(user_id, {})
    currency = data.get('currency')

    # تحقق من الرصيد
    user = db_execute("SELECT usdt_balance, shamcash_balance FROM users WHERE user_id=?", (user_id,), fetch=True)
    if not user:
        bot.reply_to(message, "❌ ليس لديك حساب. اكتب /start")
        return

    usdt_bal, sham_bal = user

    if currency == 'USDT' and usdt_bal >= amount:
        # طلب عنوان USDT
        msg = bot.reply_to(message, "📝 أدخل عنوان محفظة USDT (TRC-20) الذي ترغب في استلام المبلغ عليه:")
        bot.register_next_step_handler(msg, process_withdraw_address, amount, currency)
    elif currency == 'شام كاش' and sham_bal >= amount:
        # طلب رقم هاتف شام كاش
        msg = bot.reply_to(message, "📝 أدخل رقم هاتف شام كاش الذي ترغب في استلام المبلغ عليه:")
        bot.register_next_step_handler(msg, process_withdraw_address, amount, currency)
    else:
        bot.reply_to(message, f"❌ رصيدك غير كافٍ. رصيد {currency}: {usdt_bal if currency == 'USDT' else sham_bal}")

def process_withdraw_address(message, amount, currency):
    user_id = message.from_user.id
    address = message.text.strip()

    # تنفيذ التحويل
    try:
        if currency == 'USDT':
            txid = send_usdt(address, amount - WITHDRAW_FEE)
            # خصم من الرصيد
            db_execute("UPDATE users SET usdt_balance = usdt_balance - ? WHERE user_id=?", (amount, user_id))
            bot.reply_to(message, f"✅ تم سحب {amount - WITHDRAW_FEE} USDT بنجاح.\nرقم العملية: `{txid}`")
        else:
            txid = send_shamcash(address, amount - WITHDRAW_FEE)
            db_execute("UPDATE users SET shamcash_balance = shamcash_balance - ? WHERE user_id=?", (amount, user_id))
            bot.reply_to(message, f"✅ تم سحب {amount - WITHDRAW_FEE} شام كاش بنجاح.\nرقم العملية: `{txid}`")
    except Exception as e:
        bot.reply_to(message, f"❌ فشل السحب: {str(e)}")

# ... (باقي الأوامر ونظام التحويل)

print("✅ البوت يعمل الآن على السيرفر...")
bot.polling(non_stop=True)
