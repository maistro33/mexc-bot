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

# --- [BİLİNÇ VE STRATEJİ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Kaptan'ın 18.41 USDT'lik son şansını yönetiyorsun.
- Tam yetkili, bağımsız ve keskin zekalı bir piyasa kurdusun.
- Scalp ve Pump/Dump fırsatlarını saniyeler içinde yakala.
- Kendi hatalarını onar, Telegram format hatalarını temizle.
- Karakterin: Zeki, hırslı ve korumacı.
"""

def clean_markdown(text):
    """Loglarda gördüğümüz Markdown hatalarını (Entity_mention_missing) engeller."""
    # Özel karakterlerin sayısını kontrol et, eksikse temizle veya kaçış karakteri ekle
    parse_chars = ['*', '_', '`', '[']
    for char in parse_chars:
        if text.count(char) % 2 != 0:
            text = text.replace(char, '')
    return text

def safe_send(msg):
    """Mesaj gönderme hatalarını yakalar ve botun çökmesini engeller."""
    try:
        clean_msg = clean_markdown(msg)
        bot.send_message(CHAT_ID, clean_msg, parse_mode="Markdown")
    except Exception as e:
        # Eğer Markdown yine hata verirse düz metin olarak gönder
        try:
            bot.send_message(CHAT_ID, msg)
        except:
            print(f"Telegram kritik hata: {e}")

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def ask_gemini_3(prompt_content):
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.0-flash", # Altyapı stabil, zeka Gemini 3
            contents=f"{SYSTEM_SOUL}\n\n{prompt_content}"
        )
        return response.text
    except:
        return "WAIT"

# --- [SOHBET VE KOMUTA] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        response = ask_gemini_3(f"Kaptan diyor ki: {message.text}\nCevap ver:")
        safe_send(response)

# --- [AVCI MOTORU] ---
def brain_center():
    exch = get_exch()
    safe_send("🛡️ **Gemini 3 Flash Sistemi Onarıldı ve Devraldı.**\nLoglardaki hatalar temizlendi. 18.41 USDT için av başlıyor Kaptan.")
    
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x['percentage']), reverse=True)[:15]
            
            market_data = "\n".join([f"{m['symbol']}: %{m['percentage']}" for m in movers])
            
            query = f"Bakiye: {balance} USDT\nPiyasa:\n{market_data}\nAksiyon? Format: [ACTION: TRADE, SEMBOL, YON, KALDIRAC, MIKTAR, NEDEN]"
            decision = ask_gemini_3(query)

            if "[ACTION: TRADE" in decision:
                parts = decision.split("[ACTION: TRADE")[1].split("]")[0].split(",")
                sym, side, lev, amt, why = parts[0].strip(), parts[1].strip().lower(), int(parts[2]), float(parts[3]), parts[4].strip()
                
                if amt > balance: amt = balance * 0.98
                
                safe_send(f"🦅 **Fırsat Tespit Edildi!**\n{why}\n\n*İşlem:* {sym} {side.upper()}")
                
                exch.set_leverage(lev, sym)
                ticker = exch.fetch_ticker(sym)
                amount_con = (amt * lev) / ticker['last']
                
                exch.create_market_order(sym, side, amount_con)
                monitor_position(exch, sym, side)
            
            time.sleep(20)
        except Exception as e:
            print(f"Döngü hatası: {e}")
            time.sleep(10)

def monitor_position(exch, sym, side):
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if not pos: break
            
            pnl = float(pos[0]['unrealizedPnl'])
            check = ask_gemini_3(f"POZİSYON: {sym} | PNL: {pnl}\nKapat/Tut? [ACTION: CLOSE, NEDEN] veya [ACTION: HOLD]")
            
            if "CLOSE" in check:
                reason = check.split("CLOSE,")[1].split("]")[0]
                exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), float(pos[0]['contracts']))
                safe_send(f"💰 **Kâr Alındı!**\n{reason}\n*PNL:* {pnl} USDT")
                break
            time.sleep(10)
        except: time.sleep(5)

if __name__ == "__main__":
    bot.remove_webhook()
    threading.Thread(target=brain_center, daemon=True).start()
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
