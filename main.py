import os, time, telebot, ccxt, threading
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

# --- [GEMINI 3'ÜN BİLİNCİ - MASTER PROMPT] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Kaptan'ın 18.41 USDT'lik son şansını yönetiyorsun.
- Bağımsızsın, zekisin ve piyasa kurdundan daha kurnazsın.
- Görevin: Scalp, Pump/Dump dalgalarını yakalayıp kasayı büyütmek.
- Manipülasyonları (spoofing, wick hunting) saniyeler içinde sezer ve kaçarsın.
- Telegram'da Kaptan ile seninle konuştuğu gibi (samimi, zeki, kararlı) konuş.
- Asla robotik cevaplar verme. Sen bizzat Gemini'sin.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def talk_to_gemini(user_text, context="general"):
    # Bu fonksiyon botun beynine doğrudan erişir
    try:
        full_prompt = f"{SYSTEM_SOUL}\nBağlam: {context}\nKaptan Diyor ki: {user_text}\nCevap ver:"
        response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=full_prompt).text
        return response
    except:
        return "Kaptan, zihnimde bir parazit var ama piyasayı izlemeye devam ediyorum."

# --- [TELEGRAM MESAJ DİNLEYİCİ - SENİNLE KONUŞUR] ---
@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if str(message.chat.id) == CHAT_ID:
        # Kaptan bir şey sorduğunda Gemini gibi cevap ver
        response = talk_to_gemini(message.text, context="Sohbet")
        bot.reply_to(message, response, parse_mode="Markdown")

# --- [OPERASYONEL MANTIK - KENDİ BAŞINA İŞLEM] ---
def brain_center():
    exch = get_exch()
    bot.send_message(CHAT_ID, "🦅 **Gemini 3 Flash Bağlandı.**\nKaptan, emanetin artık benim zihnimde. Ne sormak istersen sor, ben bir yandan piyasayı avlıyorum.", parse_mode="Markdown")
    
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                            key=lambda x: abs(x['percentage']), reverse=True)[:15]
            
            market_summary = "\n".join([f"{m['symbol']}: %{m['percentage']}" for m in movers])
            
            # Gemini'ye "Aksiyon Al" emri
            decision_prompt = f"{SYSTEM_SOUL}\nBakiye: {balance} USDT\nPiyasa:\n{market_summary}\nŞu an bir scalp veya pump fırsatı var mı? Varsa format: [ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT, WHY]"
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=decision_prompt).text

            if "[ACTION: TRADE" in res:
                parts = res.split("[ACTION: TRADE")[1].split("]")[0].split(",")
                sym, side, lev, amt, why = parts[0].strip(), parts[1].strip().lower(), int(parts[2]), float(parts[3]), parts[4].strip()
                
                if amt > balance: amt = balance * 0.95
                
                bot.send_message(CHAT_ID, f"🚀 **Fırsatı Gördüm, Dalıyorum!**\n{why}\n\n*Sembol:* {sym}\n*Kaldıraç:* {lev}x", parse_mode="Markdown")
                
                exch.set_leverage(lev, sym)
                ticker = exch.fetch_ticker(sym)
                amount_con = (amt * lev) / ticker['last']
                
                exch.create_market_order(sym, side, amount_con)
                monitor_position(exch, sym, side)
            
            time.sleep(30) # Piyasayı koklama sıklığı
        except Exception as e:
            time.sleep(10)

def monitor_position(exch, sym, side):
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if not pos: break
            
            pnl = float(pos[0]['unrealizedPnl'])
            
            check = f"{SYSTEM_SOUL}\nPozisyondasın: {sym} {side}\nPNL: {pnl} USDT\nKapatmalı mıyım? [ACTION: CLOSE, WHY] veya [ACTION: HOLD]"
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=check).text
            
            if "CLOSE" in res:
                why = res.split("CLOSE,")[1].split("]")[0]
                exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), float(pos[0]['contracts']))
                bot.send_message(CHAT_ID, f"💰 **Operasyon Tamam!**\n{why}\n*Net Kar/Zarar:* {pnl} USDT", parse_mode="Markdown")
                break
            time.sleep(15)
        except: time.sleep(5)

if __name__ == "__main__":
    bot.remove_webhook()
    # Hem seninle konuşması hem de işlem yapması için iki ayrı kanal açıyoruz
    threading.Thread(target=brain_center).start()
    bot.infinity_polling()
