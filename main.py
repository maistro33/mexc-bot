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

# --- [FINAL SCALP SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Tüm borsayı tarayan, otonom ve hatasız bir scalp yöneticisisin.
1. ANALİZ: En hacimli ve volatil altcoinleri tara.
2. GİRİŞ: Sadece sayısal değerlerle @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ komutu ver.
3. ÇIKIŞ: Kâr hedefine ulaşıldığında veya trend döndüğünde @@[ACTION: CLOSE, SYMBOL]@@ komutu ver.
4. UYUM: Borsa limitlerine ve bakiyene sadık kal.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *GEMINI FINAL:* \n{msg}", parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        # --- İŞLEM AÇMA MANTIĞI ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if not match: return
            
            raw_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
            req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

            # Borsa ve Sembol Uyumu
            markets = exch.load_markets()
            exact_sym = next((s for s in markets if markets[s]['swap'] and raw_sym in s), None)
            if not exact_sym: return
            
            # Bakiye ve Limit Filtresi
            balance = exch.fetch_balance()
            free_usdt = float(balance['free'].get('USDT', 0))
            final_amt = min(req_amt, free_usdt * 0.95) # Bakiyenin max %95'i
            
            if final_amt < 5: return # Minimum 5 USDT altı işlem açma

            # Kaldıraç ve Emir
            try: exch.set_leverage(lev_val, exact_sym)
            except: pass
            
            ticker = exch.fetch_ticker(exact_sym)
            qty = (final_amt * lev_val) / ticker['last']
            
            # Borsa miktar limitlerine sıkıştır
            market = markets[exact_sym]
            max_qty = market['limits']['amount']['max']
            if max_qty and qty > max_qty: qty = max_qty * 0.9
            
            qty = float(exch.amount_to_precision(exact_sym, qty))
            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                safe_send(f"✅ *GİRİŞ YAPILDI*\nSembol: {exact_sym}\nKaldıraç: {lev_val}x\nMiktar: {final_amt:.2f} USDT")

        # --- İŞLEM KAPATMA MANTIĞI ---
        elif "@@[ACTION: CLOSE" in decision:
            sym_to_close = decision.split("CLOSE,")[1].split("]@@")[0].strip()
            markets = exch.load_markets()
            exact_sym = next((s for s in markets if markets[s]['swap'] and sym_to_close in s), None)
            
            if exact_sym:
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    c_side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    exch.create_order(exact_sym, 'market', c_side, float(pos[0]['contracts']))
                    safe_send(f"💰 *KÂR ALINDI/KAPATILDI:* {exact_sym}")

    except Exception as e:
        print(f"Hata: {e}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            # 1. Market Taraması
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # 2. Açık Pozisyonları Analize Ekle
            positions = exch.fetch_positions()
            active_p = [f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f})" for p in positions if float(p['contracts']) > 0]
            
            # 3. En Hareketli Altcoinler
            alts = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                          key=lambda x: abs(x['c']), reverse=True)[:25]
            
            market_snap = "\n".join([f"{x['s']}: %{x['c']}" for x in alts])
            
            prompt = f"""
            Bakiye: {balance['total'].get('USDT', 0)} USDT (Kullanılabilir: {balance['free'].get('USDT', 0)})
            Açık Pozisyonlar: {active_p}
            
            Market Snapshot:
            {market_snap}
            
            Strateji:
            - Kar gördüğün veya trendin döndüğü pozisyonları CLOSE ile kapat.
            - Yeni fırsat varsa TRADE ile gir. 
            - Bakiyeni aşma, borsaya uyum sağ.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            if "@@" in response:
                execute_intelligence(response)
                # Sadece analiz kısmını gönder
                safe_send(response.split("@@")[0])
            
            time.sleep(40) # 40 saniyelik ideal döngü
        except: time.sleep(20)

if __name__ == "__main__":
    safe_send("🔥 *Gemini 3 Flash: Final Sürüm Aktif!* \nTüm borsa taranıyor, pozisyonlar izleniyor.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
