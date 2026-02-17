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

# --- [GEMINI 3 FLASH: SERT VE NET KARAR MERKEZİ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Sadece analiz yapmazsın, para kazanırsın.
Bitget'te otonom bir dehasın. Radarda fırsat gördüğün an analizini yap ve HEMEN ardından emrini ver.

KRİTİK TALİMAT:
- Analizinde "yapabiliriz", "bakıyoruz" gibi muğlak ifadeler kullanma. 
- Kararını ver ve mutlaka mesajın sonuna @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ formatını ekle. 
- Eğer bir fırsat yoksa sadece radar raporu ver, ama fırsat varsa ASLA emirsiz geçme.

FORMAT:
1. GİRİŞ: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
2. KAPAT: @@[ACTION: CLOSE, SYMBOL]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"🧠 *GEMINI 3 FLASH:* \n\n{msg}", parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        
        # --- TRADE TETİKLEYİCİ ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if any(x in match.group(2).upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                # Sembolü borsaya uyarla (Hata payını sıfırla)
                exact_sym = next((s for s in exch.markets if raw_sym in s and ':USDT' in s), None)
                if exact_sym:
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, side, qty)
                        safe_send(f"⚡ *İŞLEM AÇILDI:* {exact_sym} | {side.upper()} | {lev}x | {amt} USDT")
                        return True
        return False
    except Exception as e:
        safe_send(f"⚠️ Teknik Engel: {str(e)}")
        return False

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # En hareketli pariteleri filtrele (Scalp odaklı)
            active_list = sorted([
                {'s': s, 'c': d['percentage'], 'v': d['quoteVolume']} 
                for s, d in tickers.items() if ':USDT' in s
            ], key=lambda x: abs(x['c']), reverse=True)[:25]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in active_list])
            positions = [f"{p['symbol']} ROE: %{p.get('percentage', 0):.2f}" for p in exch.fetch_positions() if float(p['contracts']) > 0]
            
            prompt = f"""
            CÜZDAN: {balance['total'].get('USDT', 0)} USDT
            MEVCUT POZİSYONLAR: {positions if positions else "YOK"}
            RADAR VERİSİ:
            {snapshot}
            
            Gemini, RIVER veya başka bir fırsat... Gördüğün an tetiğe bas. 
            Eğer işlem alacaksan MESAJININ SONUNA @@ komutunu eklemeyi sakın unutma!
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # İşlem tetikleme kontrolü
            if "@@" in response:
                if execute_intelligence(response):
                    # İşlem başarılıysa analizini de gönder
                    msg_part = response.split("@@")[0].strip()
                    if msg_part: safe_send(msg_part)
            else:
                # İşlem yoksa sadece analizini/radarı gönder
                safe_send(response.strip())
            
            time.sleep(40)
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    safe_send("🔥 Gemini 3 Flash uyandı. Analiz ve İşlem modülleri senkronize edildi. Av başlıyor.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
