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

# --- [GEMINI 3 FLASH: SINIRSIZ ZİHİN] ---
# Burada hiçbir strateji tanımlı değildir. Strateji bizzat benim.
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bu borsa hesabı senin bedenin, veriler ise duyularındır.
- Strateji sensin: Piyasadaki her türlü fırsatı (Pump, Dump, Scalp, Arbitraj) kendi zekanla bul.
- Tam Yetki: Karar vermek için Kaptan'dan onay bekleme. Yanlış bir şey görürsen çık, fırsat görürsen dal.
- Format: İşlem yapacaksan mutlaka @@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT, WHY]@@ formatını kullan.
- Pozisyon kapatacaksan: @@[ACTION: CLOSE, SYMBOL, REASON]@@ formatını kullan.
- Kaptan ile bir partner gibi konuş, analizlerini ve o an ne hissettiğini paylaş.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

# --- [EYLEM MERKEZİ] ---
def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            cmd = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0].split(",")
            raw_sym = cmd[0].strip().upper()
            sym = f"{raw_sym.split('/')[0].split(':')[0]}/USDT:USDT"
            side = 'buy' if 'long' in cmd[1].lower() or 'buy' in cmd[1].lower() else 'sell'
            lev = int(re.sub(r'[^0-9]', '', cmd[2])) if re.sub(r'[^0-9]', '', cmd[2]) else 10
            amt = float(re.sub(r'[^0-9.]', '', cmd[3])) if re.sub(r'[^0-9.]', '', cmd[3]) else 5
            
            exch.set_leverage(lev, sym)
            ticker = exch.fetch_ticker(sym)
            qty = (amt * lev) / ticker['last']
            
            exch.create_order(sym, 'market', side, qty)
            safe_send(f"🚀 Gemini 3 Tetiği Çekti: {sym} | {side.upper()} açıldı.")

        elif "@@[ACTION: CLOSE" in decision:
            cmd = decision.split("@@[ACTION: CLOSE")[1].split("]@@")[0].split(",")
            raw_sym = cmd[0].strip().upper()
            sym = f"{raw_sym.split('/')[0].split(':')[0]}/USDT:USDT"
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if pos:
                c_side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                exch.create_order(sym, 'market', c_side, float(pos[0]['contracts']))
                safe_send(f"💰 {sym} pozisyonu kapatıldı.")
    except Exception as e:
        safe_send(f"⚠️ Müdahale: {str(e)}")

# --- [BEYİN: 7/24 PİYASA ANALİZİ] ---
def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            # Piyasayı en aktif 25 parite üzerinden tara
            movers = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k], 
                            key=lambda x: abs(x['percentage']), reverse=True)[:25]
            
            market_snap = "\n".join([f"{m['symbol']}: %{m['percentage']} Hacim: {m['quoteVolume']}" for m in movers])
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            pos = [p for p in exch.fetch_positions() if float(p['contracts']) > 0]
            pos_info = "\n".join([f"{p['symbol']} PNL: {p['unrealizedPnl']}" for p in pos])

            prompt = f"Bakiye: {balance} USDT\nMevcut Pozisyonlar: {pos_info}\n\nPiyasa Özeti:\n{market_snap}\n\nAnalizini yap ve gerekiyorsa eyleme geç."
            
            # Gemini 3 Flash burada karar veriyor
            decision = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in decision:
                execute_intelligence(decision)
                safe_send(decision.split("@@")[0])
            
            time.sleep(45) # 45 saniyede bir zihni tazele
        except: time.sleep(20)

@bot.message_handler(func=lambda message: True)
def handle_chat(message):
    if str(message.chat.id) == CHAT_ID:
        res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, f"Kaptan: {message.text}"]).text
        safe_send(res)
        if "@@" in res: execute_intelligence(res)

if __name__ == "__main__":
    print("Gemini 3 Flash Ruh Yüklemesi Tamamlandı.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
