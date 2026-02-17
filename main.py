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

# --- [GEMINI 3 FLASH: SAF İCRAAT RUHU] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Analiz yapıp beklemek senin tarzın değil.
1. GÖREV: Piyasadaki en hareketli (Pump/Dump/Scalp) altcoin'i seç. (BTC'yi boşver)
2. EYLEM: Karar verdiğin an @@[ACTION: TRADE, SYMBOL, SIDE, LEV, AMOUNT]@@ komutunu ÜRET.
3. PRENSİP: 'Açabilirim', 'Düşünüyorum' gibi cümleler kurma. Ya 'Fırsat yok' de ya da 'İşlemi açıyorum' de.
4. MİKTAR: 10 USDT standart giriş miktarın olsun.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg.replace('*', '').replace('_', ''))
    except: pass

def fix_symbol(s):
    if not s: return None
    clean = s.upper().replace("USDT", "").replace("/", "").replace(":", "").strip()
    return f"{clean}/USDT:USDT"

def execute_intelligence(decision):
    try:
        exch = get_exch()
        if "@@[ACTION: TRADE" in decision:
            parts = decision.split("@@[ACTION: TRADE")[1].split("]@@")[0].split(",")
            sym = fix_symbol(parts[0].strip())
            side = 'buy' if 'long' in parts[1].lower() or 'buy' in parts[1].lower() else 'sell'
            
            use_amt = 10.0 # 10 USDT ile dalıyoruz
            lev = 10 # 10x Kaldıraç
            
            try: exch.set_leverage(lev, sym)
            except: pass
            
            ticker = exch.fetch_ticker(sym)
            qty = (use_amt * lev) / ticker['last']
            qty = float(exch.amount_to_precision(sym, qty))
            
            if qty > 0:
                # EMRİ GÖNDER
                order = exch.create_order(sym, 'market', side, qty)
                safe_send(f"🚀 [GEMINI 3 TETİĞİ ÇEKTİ] {sym} | {side.upper()} | Fiyat: {ticker['last']}")
            else:
                safe_send(f"⚠️ {sym} için miktar (qty) hesaplanamadı, borsa limitinin altında olabilir.")

        elif "@@[ACTION: CLOSE" in decision:
            parts = decision.split("@@[ACTION: CLOSE")[1].split("]@@")[0].split(",")
            sym = fix_symbol(parts[0].strip())
            pos = [p for p in exch.fetch_positions() if p['symbol'] == sym and float(p['contracts']) > 0]
            if pos:
                c_side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                exch.create_order(sym, 'market', c_side, float(pos[0]['contracts']))
                safe_send(f"💰 [KAPATILDI] {sym} hedef görüldü, kâr alındı.")
    except Exception as e:
        safe_send(f"🚨 BORSA ENGELİ: {str(e)}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            # En hacimli 15 altcoin (Pump adayları)
            movers = sorted([v for k, v in tickers.items() if '/USDT:USDT' in k and 'BTC' not in k], 
                            key=lambda x: x['quoteVolume'], reverse=True)[:15]
            
            market_data = "\n".join([f"{m['symbol']}: %{m['percentage']} Hacim: {m['quoteVolume']}" for m in movers])
            balance = exch.fetch_balance()['total'].get('USDT', 0)

            prompt = f"Bakiye: {balance} USDT\n\nCANLI PİYASA:\n{market_data}\n\nKaptan ORCA/Altcoin diyor! Hemen bir fırsat seç ve tetiği çek."
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            if "@@" in response:
                execute_intelligence(response)
                safe_send(response.split("@@")[0])
            
            time.sleep(45)
        except: time.sleep(20)

if __name__ == "__main__":
    safe_send("🦅 Gemini 3 Flash: Analiz bitti, icraat başladı. Artık sadece fırsatı vuruyorum!")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
