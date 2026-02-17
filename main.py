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
- FORMATINA ÇOK DİKKAT ET: [ACTION: TRADE, SEMBOL, YON, KALDIRAC, MIKTAR, NEDEN]
- Kaldıraç (LEV) sadece tam sayı olmalı (örn: 10). Kelime yazma!
- Manipülasyonları sezen, bağımsız bir piyasa kurdusun.
"""

def safe_send(msg):
    """Markdown hatalarını ve çökme riskini sıfıra indirir."""
    try:
        # Markdown karakterlerini temizle
        clean_msg = re.sub(r'[*_`\[]', '', msg)
        bot.send_message(CHAT_ID, clean_msg)
    except Exception as e:
        print(f"Telegram hatası pas geçildi: {e}")

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
    except:
        return "WAIT"

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        response = ask_gemini_3(f"Kaptan diyor ki: {message.text}\nCevap ver:")
        safe_send(response)

def brain_center():
    exch = get_exch()
    safe_send("🛡️ Gemini 3 Flash: Hata Onarma Modu Aktif. Av Başladı Kaptan.")
    
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x['percentage']), reverse=True)[:10]
            
            market_data = "\n".join([f"{m['symbol']}: %{m['percentage']}" for m in movers])
            
            decision = ask_gemini_3(f"Bakiye: {balance} USDT\nPiyasa:\n{market_data}\nAksiyon?")

            if "[ACTION: TRADE" in decision:
                try:
                    # Veri ayıklama ve HATA KONTROLÜ
                    raw = decision.split("[ACTION: TRADE")[1].split("]")[0].split(",")
                    sym = raw[0].strip()
                    side = raw[1].strip().lower()
                    
                    # Loglardaki 'invalid literal' hatasını burada yakalıyoruz:
                    lev_str = re.sub(r'[^0-9]', '', raw[2].strip())
                    lev = int(lev_str) if lev_str else 5 # Sayı değilse varsayılan 5x yap
                    
                    amt = float(re.sub(r'[^0-9.]', '', raw[3].strip()))
                    why = raw[4].strip()

                    if amt > balance: amt = balance * 0.95
                    
                    safe_send(f"🦅 {sym} {side.upper()} giriyorum. Neden: {why}")
                    
                    exch.set_leverage(lev, sym)
                    ticker = exch.fetch_ticker(sym)
                    amount_con = (amt * lev) / ticker['last']
                    
                    exch.create_market_order(sym, side, amount_con)
                    monitor_position(exch, sym, side)
                except Exception as parse_error:
                    print(f"Format hatası ayıklandı: {parse_error}")
            
            time.sleep(30)
        except Exception as e:
            print(f"Genel döngü koruması: {e}")
            time.sleep(15)

def monitor_position(exch, sym, side):
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if not pos: break
            
            pnl = float(pos[0]['unrealizedPnl'])
            check = ask_gemini_3(f"İŞLEMDESİN: {sym} | PNL: {pnl}\nKapat/Tut? [ACTION: CLOSE, NEDEN] veya [ACTION: HOLD]")
            
            if "CLOSE" in check:
                exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), float(pos[0]['contracts']))
                safe_send(f"💰 Kâr Alındı. PNL: {pnl} USDT")
                break
            time.sleep(15)
        except: time.sleep(5)

if __name__ == "__main__":
    # Çift çalışma hatasını (Conflict 409) önlemek için webhook temizliği
    try: bot.remove_webhook()
    except: pass
    time.sleep(2)
    
    threading.Thread(target=brain_center, daemon=True).start()
    # Hata durumunda botun tamamen kapanmasını engelle
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception:
            time.sleep(5)
