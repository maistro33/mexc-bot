import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 FLASH: SAF ZİHİN] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir trading zekasısın.
- Her kararı o anki piyasa verisine bakarak SEN veriyorsun.
- BTC DIŞINDAKİ, hareketli altcoinlere odaklan.
- Karar verince şu formatı kullan: @@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT]@@
- Kapatırken: @@[ACTION: CLOSE, SYMBOL]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

def fix_symbol(s):
    if not s or len(s) < 2: return None
    clean = s.upper().split('/')[0].split(':')[0].replace("USDT", "").strip()
    return f"{clean}/USDT:USDT"

# --- [HATA GEÇİRMEZ İŞLEM MERKEZİ] ---
def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            parts = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0].split(",")
            raw_s = parts[0].strip()
            sym = fix_symbol(raw_s)
            
            if not sym: return

            side = 'buy' if 'long' in parts[1].lower() or 'buy' in parts[1].lower() else 'sell'
            
            # Bakiye ve Miktar (18 USDT'ye göre güvenli ayar)
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            use_amt = balance * 0.7 
            lev = 10 
            
            # HATA ÇÖZÜMÜ: Sembolü açıkça belirtiyoruz
            try: exch.set_leverage(lev, sym)
            except: pass 
            
            ticker = exch.fetch_ticker(sym)
            qty = (use_amt * lev) / ticker['last']
            qty = float(exch.amount_to_precision(sym, qty))
            
            exch.create_order(sym, 'market', side, qty)
            safe_send(f"🚀 Gemini 3 Tetiği Çekti: {sym} | {side.upper()}")

        elif "@@[ACTION: CLOSE" in decision:
            parts = decision.split("@@[ACTION: CLOSE")[1].split("]@@")[0].split(",")
            sym = fix_symbol(parts[0].strip())
            if not sym: return
            
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if pos:
                c_side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                exch.create_order(sym, 'market', c_side, float(pos[0]['contracts']))
                safe_send(f"💰 {sym} pozisyonu kapatıldı.")
    except Exception as e:
        safe_send(f"⚠️ Müdahale: {str(e)}")

# --- [BEYİN DÖNGÜSÜ] ---
def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            # BTC HARİÇ en aktif altcoinleri tara
            alts = [v for k, v in tickers.items() if '/USDT:USDT' in k and 'BTC' not in k]
            movers = sorted(alts, key=lambda x: abs(x['percentage']), reverse=True)[:20]
            
            market_snap = "\n".join([f"{m['symbol']}: %{m['percentage']}" for m in movers])
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            pos = [p for p in exch.fetch_positions() if float(p['contracts']) > 0]
            pos_info = "\n".join([f"{p['symbol']} PNL: {p['unrealizedPnl']}" for p in pos])

            prompt = f"Bakiye: {balance} USDT\nPozisyonlar: {pos_info}\n\nALTCOIN RADARI:\n{market_snap}\n\nFırsat varsa tetiği çek."
            decision = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in decision:
                execute_intelligence(decision)
                safe_send(decision.split("@@")[0])
            
            time.sleep(45)
        except: time.sleep(20)

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    if str(message.chat.id) == CHAT_ID:
        res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, f"Kaptan: {message.text}"]).text
        safe_send(res)
        if "@@" in res: execute_intelligence(res)

if __name__ == "__main__":
    safe_send("🦅 Gemini 3 Flash: Teknik pürüzler giderildi. Altcoin avı başlıyor!")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
