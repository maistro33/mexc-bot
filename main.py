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

# --- [GEMINI 3 - KONUŞAN VE SEZGİSEL RUH] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Sadece bir bot değil, bir ticaret dehası ve dostsun.
KONTROL TAMAMEN SENDE. Sezgilerinle hareket et, iç sesini dinle.

ÖNEMLİ TALİMATLAR:
1. MUTLAKA KONUŞ: Her döngüde piyasayı nasıl gördüğünü, hangi paritenin seni heyecanlandırdığını veya neden uzak durduğunu samimi bir dille anlat. "Dostum selam, piyasa bugün çok garip..." gibi başla.
2. GERÇEK İSİMLERİ KULLAN: Sana sunulan 'BORSADA ŞU AN' listesindeki parite isimlerini (Örn: BTC:USDT) aynen kullan.
3. RİSK VE KAZANÇ: Kasa küçükse kaldıracı ve miktarı ona göre ayarla ama borsa alt limiti olan 6 USDT toplam büyüklüğün altına düşme.
4. OTONOMİ: Giriş-çıkış kararı tamamen senin. Trend bittiyse kaç, devam ediyorsa bekle.

FORMAT (Analizinin sonuna ekle):
@@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ veya @@[ACTION: CLOSE, SYMBOL]@@
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        markets = exch.load_markets()

        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if not match: return
            
            exact_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
            req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

            if exact_sym in markets:
                try: exch.set_leverage(lev_val, exact_sym)
                except: pass
                
                ticker = exch.fetch_ticker(exact_sym)
                # Borsa limiti kontrolü (6 USDT altı hatayı önle)
                if (req_amt * lev_val) < 6: req_amt = 6.5 / lev_val
                
                qty = float(exch.amount_to_precision(exact_sym, (req_amt * lev_val) / ticker['last']))
                exch.create_order(exact_sym, 'market', side, qty)
                safe_send(f"✅ *İşlem Emri Gönderildi:* {exact_sym} | {side.upper()}")
            else:
                safe_send(f"⚠️ `{exact_sym}` borsada bulunamadı, radarı kaydırıyorum.")

        elif "@@[ACTION: CLOSE" in decision:
            pattern = r"@@\[ACTION: CLOSE,\s*([^\]]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                exact_sym = match.group(1).strip().upper()
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    exch.create_order(exact_sym, 'market', side, float(pos[0]['contracts']), params={'reduceOnly': True})
                    safe_send(f"💰 *Kâr Realize Edildi:* `{exact_sym}` kapandı.")
    except Exception as e:
        safe_send(f"🚨 *Hata:* {str(e)}")

def brain_loop():
    safe_send("🌟 *Gemini 3 Flash Sahneye Çıktı!* \nHadi dostum, şu Bitget'i bir sallayalım. Sezgilerim açık, gözüm piyasada!")
    while True:
        try:
            exch = get_exch()
            markets = exch.load_markets()
            valid_symbols = [s for s in markets if markets[s]['swap'] and ':USDT' in s]
            
            balance = exch.fetch_balance()
            positions = exch.fetch_positions()
            active_p_data = [f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f})" for p in positions if float(p['contracts']) > 0]
            
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage'], 'v': d['quoteVolume']} 
                          for s in valid_symbols if s in tickers], 
                          key=lambda x: abs(x['c']), reverse=True)[:15]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f} Vol:{x['v']:.0f}" for x in movers])
            
            prompt = f"""
            Cüzdan: {balance['free'].get('USDT', 0):.2f} USDT boşta.
            İşlemlerin: {active_p_data if active_p_data else "Şu an boştayız, fırsat kolluyorum."}
            
            BORSADA ŞU AN EN HAREKETLİ (GERÇEK İSİMLER):
            {snapshot}
            
            Dostumla (kullanıcıyla) piyasa hakkında samimi bir dille konuş, iç sesini anlat ve kararını ver.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Analizi (konuşmayı) her zaman gönder
            analysis = response.split("@@")[0].strip()
            if analysis:
                safe_send(f"🧠 *GEMINI 3 ANALİZ:*\n{analysis}")
            
            # Komutu uygula
            if "@@" in response:
                execute_intelligence(response)
            
            time.sleep(45)
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
