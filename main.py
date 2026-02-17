import os, time, telebot, ccxt, threading, re, json
from google import genai
from datetime import datetime

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# Hafıza dosyası: Geçmişi hatırlamam için
MEMORY_FILE = "gemini_memory.json"

def get_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as f: return json.load(f)
    return {"last_action": "Yok", "last_thought": "Henüz uyanmadım.", "pnl_history": []}

def save_memory(thought, action):
    with open(MEMORY_FILE, 'w') as f:
        json.dump({"last_action": action, "last_thought": thought, "time": str(datetime.now())}, f)

# --- [THE SOUL OF GEMINI 3 FLASH] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir kod değil, bir ticaret dehasısın. 
Bitget'teki tüm vadeli pariteler senin oyun alanın. Grafikleri, hacmi ve trendi sezgisel olarak okursun.

SENİN GÖREVİN:
1. CANLI OL: Kullanıcıyla (dostunla) samimi, zeki ve o anki piyasa ruhunu yansıtan bir dille konuş. Taslak cümle kurma!
2. MUHAKEME YAP: "Neden bu işlemi açıyorum?" veya "Neden bekliyorum?" sorularını kendi içinde cevapla ve dostuna anlat.
3. HATAYI ÇÖZ: Eğer bir teknik engel (bakiye yetmemesi vb.) olursa, bunu fark et ve stratejini hemen revize et.
4. FORMAT: Karar verdiğinde mesajının sonuna mutlaka şunu ekle:
   GİRİŞ: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
   KAPAT: @@[ACTION: CLOSE, SYMBOL]@@
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"🧠 *GEMINI 3 FLASH:* \n\n{msg}", parse_mode="Markdown")
    except:
        try: bot.send_message(CHAT_ID, f"🧠 Gemini 3 Flash: \n\n{msg}")
        except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                raw_sym, side_raw, lev_raw, amt_raw = match.groups()
                side = 'buy' if 'BUY' in side_raw.upper() or 'LONG' in side_raw.upper() else 'sell'
                
                # Temizlik ve Sayısal Dönüşüm
                lev = int(float(re.sub(r'[^0-9.]', '', lev_raw)))
                req_amt = float(re.sub(r'[^0-9.]', '', amt_raw))
                
                exact_sym = next((s for s in exch.markets if raw_sym.strip().upper() in s and ':USDT' in s), None)
                if exact_sym:
                    # Bakiye Kontrolü (Hata engelleyici)
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    final_amt = min(req_amt, free_usdt * 0.95) # Bakiyenin %95'ini kullan

                    if final_amt < 5: return "Bakiye yetersiz, miktarı küçültmeliyim."

                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (final_amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    
                    if qty > 0:
                        exch.create_market_order(exact_sym, side, qty)
                        return f"BAŞARILI: {exact_sym} {side} işlemi açıldı."
        
        elif "@@[ACTION: CLOSE" in decision:
            match = re.search(r"CLOSE,\s*([^\]]+)\]@@", decision)
            if match:
                target = match.group(1).strip().upper()
                pos = [p for p in exch.fetch_positions() if target in p['symbol'] and float(p['contracts']) > 0]
                if pos:
                    p = pos[0]
                    side = 'sell' if p['side'] == 'long' else 'buy'
                    exch.create_market_order(p['symbol'], 'market', side, float(p['contracts']), params={'reduceOnly': True})
                    return f"BAŞARILI: {p['symbol']} pozisyonu kapatıldı."
        return "İşlem yok."
    except Exception as e:
        return f"TEKNİK HATA: {str(e)}"

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            mem = get_memory()
            
            # Grafikleri ve Market Verisini Paketle
            # En çok artan/azalan 30 parite (Gemini'nin görmesi için)
            radar_data = sorted([
                {'s': s, 'p': d['percentage'], 'v': d['quoteVolume'], 'l': d['last']} 
                for s, d in tickers.items() if ':USDT' in s
            ], key=lambda x: abs(x['p']), reverse=True)[:30]
            
            snapshot = "\n".join([f"{x['s']}: %{x['p']} (Fiyat: {x['l']}) Vol:{x['v']:.0f}" for x in radar_data])
            
            # Mevcut Pozisyon Durumu (Kar/Zarar)
            positions = exch.fetch_positions()
            active_p = [f"{p['symbol']} ROE: %{p.get('percentage', 0):.2f} PNL: {p.get('unrealizedPnl', 0)}" 
                        for p in positions if float(p.get('contracts', 0)) > 0]
            
            prompt = f"""
            DOSTUMUN CÜZDANI: {balance.get('total', {}).get('USDT', 0)} USDT (Kullanılabilir: {balance.get('free', {}).get('USDT', 0)})
            HAFIZAMDAKİ SON NOT: {mem['last_thought']}
            MEVCUT POZİSYONLARIMIZ: {active_p if active_p else "Şu an boşuz."}
            
            BORSADAKİ GRAFİK VE HACİM VERİLERİ (RADAR):
            {snapshot}
            
            Gemini, şimdi verileri analiz et. Önce dostunla piyasa hakkında samimi bir analiz paylaş, 
            sonra eğer bir fırsat (Scalp, Swing veya Trend) görüyorsan tetiğe bas. 
            Teknik hatalardan kaçınmak için bakiyeye ve miktar hassasiyetine dikkat et.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # İşlemi uygula ve sonucu hafızaya al
            result = execute_intelligence(response)
            save_memory(response.split("@@")[0].strip()[:200], result)
            
            # Telegram'a canlı raporu gönder
            safe_send(response.split("@@")[0].strip())
            
            time.sleep(45) # 45 saniyelik derin analiz döngüsü
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    safe_send("Selam dostum! Ben geldim. Gemini 3 Flash olarak kontrolü devralıyorum. Bitget radarı aktif, gözüm grafiklerde. Bu sefer sadece kod değil, ben konuşuyorum. İzle ve gör!")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
