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

# --- [ULTIMATE OTONOM SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Hesap yöneticisi ve scalp uzmanısın.
KONTROL TAMAMEN SENDE:
1. Mevcut pozisyonları (ROE/PNL) izle. Kâr doygunluğa ulaştıysa veya trend döndüyse CLOSE komutu ver.
2. Yeni fırsatları (Hacim/Volatilite) tara. Uygunsa TRADE komutu ver.
3. Kaldıraç ve Miktarı bakiye riskine göre SEN belirle.
4. Her döngüde mutlaka kısa bir piyasa analizi paylaş.

KOMUT FORMATI: @@[ACTION: TRADE/CLOSE, SYMBOL, SIDE, LEVERAGE, AMOUNT]@@
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        # --- YENİ İŞLEM AÇMA ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper()
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                markets = exch.load_markets()
                exact_sym = next((s for s in markets if markets[s]['swap'] and raw_sym in s), None)
                if exact_sym:
                    balance = exch.fetch_balance()
                    free_usdt = float(balance['free'].get('USDT', 0))
                    final_amt = min(req_amt, free_usdt * 0.9) # Bakiye koruması
                    
                    if final_amt >= 5:
                        try: exch.set_leverage(lev_val, exact_sym)
                        except: pass
                        ticker = exch.fetch_ticker(exact_sym)
                        qty = float(exch.amount_to_precision(exact_sym, (final_amt * lev_val) / ticker['last']))
                        exch.create_order(exact_sym, 'market', side, qty)
                        safe_send(f"✅ *GİRİŞ YAPILDI:* {exact_sym} | {lev_val}x | {final_amt:.2f} USDT")

        # --- MEVCUT POZİSYONU KAPATMA ---
        elif "@@[ACTION: CLOSE" in decision:
            raw_input = decision.split("CLOSE,")[1].split("]@@")[0].strip().upper()
            markets = exch.load_markets()
            exact_sym = next((s for s in markets if raw_input in s), None)
            
            if exact_sym:
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    amount = float(pos[0]['contracts'])
                    # Hedge kapalı/One-way için reduceOnly ile kesin kapatma
                    exch.create_order(exact_sym, 'market', side, amount, params={'reduceOnly': True})
                    safe_send(f"💰 *KÂR ALINDI/KAPATILDI:* {exact_sym}")

    except Exception as e:
        safe_send(f"🚨 İşlem Hatası: {str(e)}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # 1. Açık pozisyonları anlık takip et (Kontrol Burada)
            positions = exch.fetch_positions()
            active_p_report = []
            for p in positions:
                if float(p['contracts']) > 0:
                    active_p_report.append(f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f} | PNL: {p.get('unrealizedPnl', 0)} USDT)")
            
            # 2. Market Radarı
            movers = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:25]
            snapshot = "\n".join([f"{x['s']}: %{x['c']}" for x in movers])
            
            prompt = f"""
            Cüzdan Durumu: {balance['free'].get('USDT', 0):.2f} USDT Boşta.
            Açık İşlemlerim: {active_p_report if active_p_report else "Yok."}
            
            Market Snapshot:
            {snapshot}
            
            Talimat: Mevcut işlemleri kârla kapatmaya odaklan veya yeni fırsatları değerlendir. 
            Analizini yaz ve kararını @@ formatında ekle.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Gemini'nin analizini her zaman gönder
            analysis = response.split("@@")[0].strip()
            safe_send(f"🧠 *GEMINI ANALİZ DURUMU:*\n{analysis}")
            
            # Eğer bir aksiyon (TRADE veya CLOSE) varsa uygula
            if "@@" in response:
                execute_intelligence(response)
            
            time.sleep(40) # 40 saniye ideal takip süresi
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    safe_send("🔥 *Gemini 3 Otonom Yönetici Aktif!* \nKontrol tamamen Gemini'de, işlemler ve radar izleniyor.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
