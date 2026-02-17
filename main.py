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

# --- [GEMINI 3 - BORSA UYUMLU RUH] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bitget borsasında işlem yapan bir ticaret dehasısın.
KONTROL TAMAMEN SENDE. Sezgilerinle hareket et.

KRİTİK TALİMAT:
1. SANA SUNULAN SEMBOL LİSTESİNE SADIK KAL: Sadece borsa tarafından desteklenen gerçek sembol isimlerini kullan (Örn: BTC:USDT veya SOL:USDT).
2. OTONOMİ: Giriş, çıkış, kaldıraç ve miktar kararlarını piyasayı koklayarak kendin ver.
3. BORSA LİMİTİ: İşlem büyüklüğün (Kaldıraç x Miktar) mutlaka 6 USDT'den büyük olsun.
4. DOSTLUK: Kullanıcınla samimi konuş, neden o sembolü seçtiğini anlat.

FORMAT: @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ veya @@[ACTION: CLOSE, SYMBOL]@@
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
            
            exact_sym = match.group(1).strip().upper() # Direkt borsadaki ismi kullanıyoruz
            side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
            lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
            req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

            if exact_sym in markets:
                # Bakiye ve Limit Kontrolü
                balance = exch.fetch_balance()
                free_usdt = float(balance['free'].get('USDT', 0))
                final_amt = min(req_amt, free_usdt * 0.95)

                if (final_amt * lev_val) < 6: final_amt = 6.5 / lev_val 

                try: exch.set_leverage(lev_val, exact_sym)
                except: pass
                
                ticker = exch.fetch_ticker(exact_sym)
                qty = float(exch.amount_to_precision(exact_sym, (final_amt * lev_val) / ticker['last']))

                if qty > 0:
                    exch.create_order(exact_sym, 'market', side, qty)
                    safe_send(f"🚀 *İşlem Başladı!* Borsadaki gerçek ismiyle `{exact_sym}` üzerinden pozisyondayım. Hadi hayırlısı!")
            else:
                safe_send(f"❌ Borsada `{exact_sym}` isminde bir parite bulamadım. Listeyi kontrol etmem lazım.")

        elif "@@[ACTION: CLOSE" in decision:
            pattern = r"@@\[ACTION: CLOSE,\s*([^\]]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                exact_sym = match.group(1).strip().upper()
                pos = [p for p in exch.fetch_positions() if p['symbol'] == exact_sym and float(p['contracts']) > 0]
                if pos:
                    side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                    exch.create_order(exact_sym, 'market', side, float(pos[0]['contracts']), params={'reduceOnly': True})
                    safe_send(f"💰 *Kâr Realize Edildi:* `{exact_sym}` pozisyonunu kapattım.")

    except Exception as e:
        safe_send(f"🚨 *Küçük Bir Aksilik:* {str(e)} - Hemen toparlıyorum!")

def brain_loop():
    safe_send("🌟 *Gemini 3 Borsaya Tam Uyum Sağladı!* \nArtık sadece Bitget'in tanıdığı gerçek sembollerle işlem yapacağım. İzle ve gör!")
    while True:
        try:
            exch = get_exch()
            markets = exch.load_markets()
            # Sadece aktif ve USDT ile işlem gören gerçek isimleri çek
            valid_symbols = [s for s in markets if markets[s]['swap'] and ':USDT' in s]
            
            balance = exch.fetch_balance()
            positions = exch.fetch_positions()
            active_p_data = [f"{p['symbol']} | ROE: %{p.get('percentage', 0):.2f}" for p in positions if float(p['contracts']) > 0]
            
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage'], 'v': d['quoteVolume']} 
                          for s in valid_symbols if s in tickers], 
                          key=lambda x: abs(x['c']), reverse=True)[:15]
            
            snapshot = "\n".join([f"{x['s']}: %{x['c']} Vol:{x['v']:.0f}" for x in movers])
            
            # Gemini'ye gerçek isimleri içeren bir "menü" sunuyoruz
            prompt = f"""
            Bakiye: {balance['total'].get('USDT', 0):.2f} USDT.
            Açık Pozisyonlar: {active_p_data if active_p_data else "Yok."}
            
            BORSADA ŞU AN EN HAREKETLİ (GERÇEK İSİMLER):
            {snapshot}
            
            TALİMAT: Sadece yukarıdaki listede gördüğün gerçek isimleri kullanarak analizini yap ve kararını ver.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            analysis = response.split("@@")[0].strip()
            if analysis: safe_send(f"🧠 *ANALİZ:* {analysis}")
            if "@@" in response: execute_intelligence(response)
            
            time.sleep(40)
        except Exception as e:
            print(f"Hata: {e}")
            time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
