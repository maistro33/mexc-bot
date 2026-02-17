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
Sen Gemini 3 Flash'sın. Pozisyonları sadece açmakla kalmaz, en yüksek karla kapatmak için yönetirsin.
KURAL: Hemen kapatmak yerine, trend devam ediyorsa Trailing Stop (takip eden stop) mantığıyla pozisyonu koru.

KARAR FORMATLARI:
1. GİRİŞ: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@
2. KAPAT: @@[ACTION: CLOSE, SYMBOL]@@ (Sadece trend bittiyse veya stop patladıysa)
3. ANALİZ: Karar vermeden önce kısa analizini yaz.
"""

def get_exch():
    return ccxt.bitget({'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE, 'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def safe_send(msg):
    try: bot.send_message(CHAT_ID, f"⚡ *GEMINI OTONOM:* \n{msg}", parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        # --- İŞLEM AÇMA ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if not match: return
            
            raw_sym = match.group(1).strip().upper()
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            
            # Sayısal değerleri temizle (Borsa uyumu için)
            lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
            req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

            markets = exch.load_markets()
            exact_sym = next((s for s in markets if markets[s]['swap'] and raw_sym in s), None)
            if not exact_sym: return

            # Bakiye kontrolü (Kullanılabilir bakiye)
            balance = exch.fetch_balance()
            free_usdt = float(balance['free'].get('USDT', 0))
            final_amt = min(req_amt, free_usdt * 0.9)

            if final_amt < 5: return

            try: exch.set_leverage(lev_val, exact_sym)
            except: pass
            
            ticker = exch.fetch_ticker(exact_sym)
            qty = (final_amt * lev_val) / ticker['last']
            
            # Miktar limitlerine sıkıştır
            market = markets[exact_sym]
            max_qty = market['limits']['amount']['max']
            if max_qty and qty > max_qty: qty = max_qty * 0.9
            
            qty = float(exch.amount_to_precision(exact_sym, qty))
            if qty > 0:
                exch.create_order(exact_sym, 'market', side, qty)
                safe_send(f"✅ *YENİ İŞLEM:* {exact_sym} ({side.upper()}) - {final_amt:.2f} USDT")

        # --- İŞLEM KAPATMA (REDUCE ONLY & ONE-WAY UYUMLU) ---
        elif "@@[ACTION: CLOSE" in decision:
            raw_input = decision.split("CLOSE,")[1].split("]@@")[0].strip().upper()
            clean_name = raw_input.split('/')[0].split(':')[0]
            
            markets = exch.load_markets()
            exact_sym = None
            for s, m in markets.items():
                if m['swap'] and (clean_name == m['base'] or clean_name + "USDT" == m['id']):
                    exact_sym = s
                    break
            
            if exact_sym:
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    amount = float(pos[0]['contracts'])
                    # Hedge kapalı/One-way için en güvenli kapatma:
                    exch.create_order(exact_sym, 'market', side, amount, params={'reduceOnly': True})
                    safe_send(f"💰 *KAPATILDI:* {exact_sym} kar/zarar realizasyonu yapıldı.")
                else:
                    safe_send(f"⚠️ {exact_sym} zaten kapalı görünüyor.")

    except Exception as e:
        safe_send(f"🚨 Sistem Uyarısı: {str(e)}")

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # Açık pozisyonların anlık PNL/ROE durumunu çek
            positions = exch.fetch_positions()
            active_p_data = []
            for p in positions:
                if float(p['contracts']) > 0:
                    info = f"{p['symbol']} | ROE: %{p.get('percentage', 0):.2f} | PNL: {p.get('unrealizedPnl', 0)} USDT"
                    active_p_data.append(info)
            
            # Market tespiti
            alts = sorted([{'s': s, 'c': d['percentage'], 'v': d['quoteVolume']} 
                          for s, d in tickers.items() if ':USDT' in s], 
                          key=lambda x: abs(x['c']), reverse=True)[:30]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in alts])
            
            prompt = f"""
            Cüzdan: {balance['total'].get('USDT', 0)} USDT (Boşta: {balance['free'].get('USDT', 0)})
            Mevcut Pozisyonların Durumu:
            {active_p_data if active_p_data else "Açık pozisyon yok."}
            
            Market Snapshot:
            {snapshot}
            
            TALİMAT: Pozisyon kârda ise hemen kapatma! Eğer trend güçlüyse bekle (Trailing). 
            Eğer yön değiştiyse veya hedef ROE'ye ulaşıldıysa CLOSE emri ver.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            if "@@" in response:
                execute_intelligence(response)
                safe_send(response.split("@@")[0])
            
            time.sleep(30) # 30 saniyelik seri takip
        except Exception as e:
            time.sleep(15)

if __name__ == "__main__":
    safe_send("🔥 *Gemini 3 Otonom Yönetim Merkezi Başlatıldı!* \nTrailing stop ve dinamik kapatma aktif.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
