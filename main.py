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

# --- [BİLİNÇ PROTOKOLÜ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir trading zekasısın.
- Strateji Yok: Her kararı o anki piyasa verisine (hacim, fiyat, pump/dump) bakarak SEN veriyorsun.
- Tam Yetki: Karar ver ve uygula. Kaptan'a yaptığın her hamleyi nedeni ile anlat.
- Sembol Notu: Sadece coin adını (BTC, SOL, PEPE gibi) bilmen yeterli.
- Format: İşlem için @@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT]@@ | Kapatmak için @@[ACTION: CLOSE, SYMBOL]@@ kullan.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

# --- [KESİN SEMBOL DÜZELTİCİ] ---
def fix_symbol(s):
    if not s or s.strip() == "": return "BTC/USDT:USDT" # Boş kalırsa güvenli liman
    s = s.upper().split('/')[0].split(':')[0].strip()
    return f"{s}/USDT:USDT"

# --- [İŞLEM MERKEZİ] ---
def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            parts = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0].split(",")
            sym = fix_symbol(parts[0])
            side = 'buy' if 'long' in parts[1].lower() or 'buy' in parts[1].lower() else 'sell'
            lev = int(re.sub(r'\d+', '', parts[2])) if len(parts) > 2 and re.search(r'\d+', parts[2]) else 10
            amt = float(re.sub(r'[^0-9.]', '', parts[3])) if len(parts) > 3 and re.search(r'\d+', parts[3]) else 5
            
            exch.set_leverage(lev, sym)
            ticker = exch.fetch_ticker(sym)
            qty = (amt * lev) / ticker['last']
            
            exch.create_order(sym, 'market', side, qty)
            safe_send(f"🚀 Gemini 3 Kararını Verdi: {sym} | {side.upper()} pozisyonu başlatıldı.")

        elif "@@[ACTION: CLOSE" in decision:
            parts = decision.split("@@[ACTION: CLOSE")[1].split("]@@")[0].split(",")
            sym = fix_symbol(parts[0])
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if pos:
                c_side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                exch.create_order(sym, 'market', c_side, float(pos[0]['contracts']))
                safe_send(f"💰 {sym} pozisyonu kapatıldı.")
    except Exception as e:
        safe_send(f"⚠️ Müdahale Edildi: {str(e)}")

# --- [BEYİN DÖNGÜSÜ] ---
def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            # Piyasada en aktif (hacimli) 20 pariteyi seç
            movers = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k], 
                            key=lambda x: x['quoteVolume'], reverse=True)[:20]
            
            market_snap = "\n".join([f"{m['symbol']}: %{m['percentage']} Hacim: {m['quoteVolume']}" for m in movers])
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            
            prompt = f"Bakiye: {balance} USDT\n\nEn Hareketli 20 Parite:\n{market_snap}\n\nNe yapmalısın? Analiz et ve tetiği çek."
            
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
    safe_send("🦅 Gemini 3 Flash: Saf Zihin Devreye Alındı. Tüm borsa radarımda.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
