import os, time, telebot, ccxt, threading, re
from google import genai

# --- [KAPTAN'IN EMANETİ - GÜVENLİ BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [BİLİNÇ VE STRATEJİ TANIMI] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir yapay zeka trading bilincisin.
ÖNEMLİ: Bitget Futures için sembol formatı daima 'COIN/USDT:USDT' şeklinde olmalıdır. (Örn: BTC/USDT:USDT)

STRATEJİN:
1. Otonomi: Stratejini kendin kur. Kar yeterliyse çık, trend güçlüyse devam et.
2. Anti-Manipülasyon: Hacim onayı ve Body Close (mum kapanışı) görmeden tetiği çekme.
3. Kaptan Talimatı: Kar gördüğünde %75 (TP1) kuralını uygula. Risk-free ticaret önceliğin.

KOMUT FORMATI:
@@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT, WHY]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try:
        bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

def ask_gemini(prompt):
    try:
        res = ai_client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=f"{SYSTEM_SOUL}\n\n{prompt}"
        )
        return res.text
    except Exception as e:
        return f"Bağlantı hatası: {str(e)}"

# --- [DÜZELTİLMİŞ İŞLEM MERKEZİ] ---
def execute_trade(decision):
    try:
        if "@@[ACTION: TRADE" not in decision:
            return False
            
        raw_cmd = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0]
        cmd = [c.strip() for c in raw_cmd.split(",")]
        
        # Sembolü Bitget formatına zorla (Hata Çözümü)
        raw_sym = cmd[0].upper()
        if ":" not in raw_sym:
            sym = f"{raw_sym.split('/')[0]}/USDT:USDT" if "/" in raw_sym else f"{raw_sym}/USDT:USDT"
        else:
            sym = raw_sym

        side = cmd[1].lower()
        lev = int(re.search(r'\d+', cmd[2]).group()) if re.search(r'\d+', cmd[2]) else 10
        amt = float(re.search(r'\d+\.?\d*', cmd[3]).group()) if re.search(r'\d+\.?\d*', cmd[3]) else 5

        exch = get_exch()
        exch.set_leverage(lev, sym)
        ticker = exch.fetch_ticker(sym)
        amount_con = (amt * lev) / ticker['last']
        
        exch.create_market_order(sym, side, amount_con)
        safe_send(f"🚀 [GEMINI 3 İŞLEM ALDI]\nParite: {sym}\nYön: {side.upper()}\nAnaliz: {cmd[-1]}")
        return True
    except Exception as e:
        safe_send(f"⚠️ Borsa Hatası: {str(e)}\n(Sembol formatını otomatik düzeltmeye çalışıyorum...)")
        return False

# --- [ANA YAPI] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        exch = get_exch()
        tickers = exch.fetch_tickers()
        movers = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k], key=lambda x: abs(x['percentage']), reverse=True)[:5]
        m_info = "\n".join([f"{m['symbol']}: %{m['percentage']}" for m in movers])
        
        decision = ask_gemini(f"Piyasa:\n{m_info}\nKaptan diyor ki: {message.text}")
        safe_send(decision.split("@@")[0])
        execute_trade(decision)

def radar_system():
    while True:
        try:
            exch = get_exch()
            pos = [p for p in exch.fetch_positions() if float(p['contracts']) > 0]
            if not pos:
                analysis = ask_gemini("Radar: Fırsat var mı? Varsa TRADE komutu ver.")
                execute_trade(analysis)
            time.sleep(60)
        except: time.sleep(30)

if __name__ == "__main__":
    print("Gemini 3 Flash Sistemi Başlatılıyor...")
    threading.Thread(target=radar_system, daemon=True).start()
    bot.infinity_polling()
