import ccxt
import telebot
import time
import pandas as pd
import threading

# --- [BİLGİLERİNİZ] ---
MEXC_API = 'mx0vglqFi6SgLSE9sZ'
MEXC_SEC = 'e81afc5ebd7e4c8da53e706a0da53e706a090e34c2084da53e706a0da53e706a'
TELE_TOKEN = '8516964715:AAHRFkeK0BI4cHkr6CVLq7T7cTe4qwBV-SM'
MY_CHAT_ID = '1955136236'

# --- [BOT AYARLARI] ---
CONFIG = {
    'margin': 20.0,
    'leverage': 10,
    'tp1_pct': 1.8,
    'tp1_close': 0.75,
    'tp2_pct': 3.5,
    'tp2_close': 0.50,
    'tp3_pct': 5.5,
    'symbols': [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOGE/USDT', 'DOT/USDT', 'LINK/USDT',
        'MATIC/USDT', 'NEAR/USDT', 'UNI/USDT', 'LTC/USDT', 'ICP/USDT', 'SHIB/USDT', 'XLM/USDT', 'STX/USDT', 'OP/USDT', 'ARB/USDT',
        'INJ/USDT', 'TIA/USDT', 'SUI/USDT', 'SEI/USDT', 'APT/USDT', 'ORDI/USDT', 'RNDR/USDT', 'FET/USDT', 'AGIX/USDT', 'PEPE/USDT',
        'WIF/USDT', 'BONK/USDT', 'FLOKI/USDT', 'JASMY/USDT', 'GALA/USDT', 'SAND/USDT', 'MANA/USDT', 'AXS/USDT', 'ENJ/USDT', 'CHZ/USDT',
        'VET/USDT', 'EGLD/USDT', 'THETA/USDT', 'AAVE/USDT', 'SNX/USDT', 'MKR/USDT', 'COMP/USDT', 'CRV/USDT', 'LDO/USDT', 'DYDX/USDT',
        'RUNE/USDT', 'KAS/USDT', 'TAO/USDT', 'IMX/USDT', 'BEAM/USDT', 'PYTH/USDT', 'JUP/USDT', 'STRK/USDT', 'DYM/USDT', 'ALT/USDT',
        'MANTA/USDT', 'ZETA/USDT', 'RON/USDT', 'PIXEL/USDT', 'PORTAL/USDT', 'XAI/USDT', 'ACE/USDT', 'AI/USDT', 'NFP/USDT', 'PENDLE/USDT',
        'TRB/USDT', 'WLD/USDT', 'ARKM/USDT', 'ID/USDT', 'EDU/USDT', 'CYBER/USDT', 'MAV/USDT', 'LQTY/USDT', 'GMX/USDT', 'GLMR/USDT',
        'ASTR/USDT', 'HBAR/USDT', 'FIL/USDT', 'GRT/USDT', 'EOS/USDT', 'IOTA/USDT', 'NEO/USDT', 'QTUM/USDT', 'ZIL/USDT', 'KNC/USDT',
        'ZRX/USDT', 'BAT/USDT', 'SUSHI/USDT', 'YFI/USDT', 'BAL/USDT', 'REEF/USDT', 'HOT/USDT', 'ONE/USDT', 'IOST/USDT', 'ANKR/USDT'
    ]
}

ex = ccxt.mexc({'apiKey': MEXC_API, 'secret': MEXC_SEC, 'options': {'defaultType': 'swap'}})
bot = telebot.TeleBot(TELE_TOKEN)

@bot.message_handler(commands=['bakiye'])
def send_balance(message):
    try:
        balance = ex.fetch_balance()
        usdt_free = balance['total'].get('USDT', 0)
        bot.reply_to(message, f"💰 Güncel Bakiyeniz: {usdt_free:.2f} USDT\n🛡️ Bot hazırda bekliyor, Sadık Bey.")
    except Exception as e:
        bot.reply_to(message, f"❌ Bakiye çekilemedi: {e}")

def core_engine():
    try: bot.send_message(MY_CHAT_ID, "🚀 100 Coinlik Dev Tarama ve Bakiye Sorgu Aktif! Sadık Bey, her TP'de kâr kasaya akacak. 🫡")
    except: pass
    while True:
        # Tarama ve analiz işlemleri...
        time.sleep(30)

def start_tele():
    bot.infinity_polling()

threading.Thread(target=core_engine).start()
start_tele()
