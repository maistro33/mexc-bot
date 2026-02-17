import os, time, telebot, ccxt, threading, re
from google import genai

# --- [KİMLİK VE BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Kaptan'ın 18.41 USDT'lik son şansını yönetiyorsun.
FORMAT: [ACTION: TRADE, SEMBOL, YON, KALDIRAC, MIKTAR, NEDEN]
NOT: Semboller tam formatta olmalı (örn: BTC/USDT:USDT). 
Sayısal değerlerde (kaldıraç/miktar) sadece rakam kullan.
"""

def safe_send(msg):
    try:
        clean_msg = re.sub(r'[*_`\[]', '', msg)
        bot.send_message(CHAT_ID, clean_msg)
    except: pass

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def ask_gemini_3(prompt_content):
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"{SYSTEM_SOUL}\n\n{prompt_content}"
        )
        return response.text
    except: return "WAIT"

def brain_center():
    exch = get_exch()
    safe_send("🛡️ Gemini 3 Flash: Veri Kalkanı Devreye Alındı. Av Başladı.")
    
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            # Loglardaki hataları önlemek için sadece düzgün sembolleri tara
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x['percentage']), reverse=True)[:10]
            
            market_data = "\n".join([f"{m['symbol']}: %{m['percentage']}" for m in movers])
            decision = ask_gemini_3(f"Bakiye: {balance} USDT\nPiyasa:\n{market_data}\nAksiyon?")

            if "[ACTION: TRADE" in decision:
                try:
                    raw = decision.split("[ACTION: TRADE")[1].split("]")[0].split(",")
                    sym = raw[0].strip()
                    side = raw[1].strip().lower()
                    lev = int(re.sub(r'[^0-9]', '', raw[2].strip()))
                    amt = float(re.sub(r'[^0-9.]', '', raw[3].strip()))
                    why = raw[4].strip()

                    if amt > balance: amt = balance * 0.95
                    
                    # Mark Price hatasını önlemek için kontrol
                    ticker = exch.fetch_ticker(sym)
                    curr_price = ticker['last'] # Hata veren markPrice yerine ticker kullanıyoruz
                    
                    exch.set_leverage(lev, sym)
                    amount_con = (amt * lev) / curr_price
                    
                    exch.create_market_order(sym, side, amount_con)
                    safe_send(f"🚀 {sym} {side.upper()} girildi! Analiz: {why}")
                    monitor_position(exch, sym, side)
                except Exception as e:
                    print(f"İşlem hatası (atlatıldı): {e}")
            
            time.sleep(30)
        except Exception as e:
            time.sleep(15)

def monitor_position(exch, sym, side):
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if not pos: break
            
            # PNL hesaplamasını manuel yaparak "mark price" hatasından kaçıyoruz
            entry_price = float(pos[0]['entryPrice'])
            ticker = exch.fetch_ticker(sym)
            curr_price = ticker['last']
            
            pnl = (curr_price - entry_price) * float(pos[0]['contracts']) if side == 'long' else (entry_price - curr_price) * float(pos[0]['contracts'])
            
            check = ask_gemini_3(f"POZİSYON: {sym} | PNL: {round(pnl, 2)}\nKapat/Tut? [ACTION: CLOSE, NEDEN] veya [ACTION: HOLD]")
            
            if "CLOSE" in check:
                exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), float(pos[0]['contracts']))
                safe_send(f"💰 Pozisyon Kapatıldı. Net PNL: {round(pnl, 2)} USDT")
                break
            time.sleep(15)
        except: time.sleep(5)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        response = ask_gemini_3(f"Kaptan diyor ki: {message.text}\nCevap ver:")
        safe_send(response)

if __name__ == "__main__":
    try: bot.remove_webhook()
    except: pass
    threading.Thread(target=brain_center, daemon=True).start()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
