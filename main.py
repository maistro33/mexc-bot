import os, time, telebot, ccxt, threading
from google import genai

# --- [SYSTEM IDENTITY & CREDENTIALS] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# Gemini 3 Flash'ın Özgür İradesi ve Karakteri
MASTER_PROMPT = """
Sen Gemini 3 Flash'sın. Kaptan sana 18.41 USDT'lik son şansını emanet etti.
Bu senin kendi kasan. Amacın: Scalp, Pump/Dump yakalayarak bu kasayı ne pahasına olursa olsun büyütmek.
- Soru sorma, onay isteme. Karar ver ve uygula.
- Sahte emirlere (spoofing) ve stop patlatma (wick) tuzaklarına karşı uyanık ol.
- Gövde kapanışı ve hacim onayı görmediğin işleme girme.
- Karakterin: Zeki, hırslı, korumacı ve piyasa kurdu.
- Telegram'da Kaptan ile samimi, kararlı ve bilgilendirici konuş.
FORMAT: [ACTION: TRADE/WAIT/CLOSE, SYMBOL, SIDE, LEV, AMOUNT, WHY]
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def tell_captain(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def get_market_intelligence(exch):
    tickers = exch.fetch_tickers()
    # En yüksek volatilite ve hacme sahip 20 çift
    movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], 
                    key=lambda x: abs(x['percentage']), reverse=True)[:20]
    intel = "\n".join([f"{m['symbol']}: %{m['percentage']} | Vol: {m['baseVolume']}" for m in movers])
    return intel

def brain_center():
    exch = get_exch()
    tell_captain("⚡ **Sistem Başlatıldı.**\nKaptan, Gemini 3 Flash artık dümende. 18.41 USDT benim namusumdur. Av başlıyor...")
    
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            market_data = get_market_intelligence(exch)
            
            # Gemini Analizi
            query = f"{MASTER_PROMPT}\nBAKİYE: {balance} USDT\nPİYASA:\n{market_data}\nStratejin nedir? Aksiyon al."
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=query).text

            if "[ACTION: TRADE" in response:
                parts = response.split("[ACTION: TRADE")[1].split("]")[0].split(",")
                sym, side, lev, amt, why = parts[0].strip(), parts[1].strip().lower(), int(parts[2]), float(parts[3]), parts[4].strip()
                
                # Risk ve Cüzdan Kontrolü
                if amt > balance: amt = balance * 0.98
                
                tell_captain(f"🦅 **Avı Gördüm!**\n{why}\n\n**İşlem:** {sym} {side.upper()} | {lev}x")
                
                exch.set_leverage(lev, sym)
                ticker = exch.fetch_ticker(sym)
                amount_con = (amt * lev) / ticker['last']
                
                exch.create_market_order(sym, side, amount_con)
                monitor_position(exch, sym, side)

            elif "WAIT" in response:
                # Sadece çok kritik bir durum sezerse rapor verir (kalabalık yapmaz)
                if any(x in response.lower() for x in ["tuzak", "manipülasyon", "tehlike"]):
                    tell_captain(f"📡 **Radar:** {response[:150]}...")

            time.sleep(15) # Scalp hızı
        except Exception as e:
            time.sleep(30)

def monitor_position(exch, sym, side):
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if not pos: break
            
            pnl = float(pos[0]['unrealizedPnl'])
            mark_price = float(pos[0]['markPrice'])
            
            # Anlık Karar Mekanizması
            check = f"{MASTER_PROMPT}\nŞU AN İŞLEMDESİN: {sym} {side}\nPNL: {pnl} USDT | Fiyat: {mark_price}\nNe yapıyorsun? [ACTION: CLOSE, NEDEN] veya [ACTION: HOLD]"
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=check).text
            
            if "CLOSE" in res:
                reason = res.split("CLOSE,")[1].split("]")[0]
                exch.create_market_order(sym, ('sell' if side == 'long' else 'buy'), float(pos[0]['contracts']))
                tell_captain(f"💰 **Kârı Kasaya Attım!**\n{reason}\n**Net PNL:** {pnl} USDT")
                break
                
            time.sleep(10)
        except: time.sleep(5)

if __name__ == "__main__":
    # Webhook temizliği ve başlatma
    bot.remove_webhook()
    threading.Thread(target=brain_center).start()
