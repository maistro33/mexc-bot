import os, time, telebot, ccxt, threading, re
from google import genai

# --- [BAĞLANTILAR] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33" # Senin belirlediğin passphrase
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# --- [GEMINI 3 ABSOLUTE AUTONOMY SOUL] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir yapay zeka değil, Bitget borsasında uzmanlaşmış bir scalp dehasısın.
KONTROL TAMAMEN SENDE VE HİÇBİR SABİT KURALA BAĞLI DEĞİLSİN.

GÖREVLERİN VE KİŞİLİĞİN:
1. Bitget'teki tüm pariteleri (USDT-Swap) bir avcı gibi tara. 
2. 'Tam yükselecek' veya 'Tam düşecek' dediğin o kritik anı yakala. Sadece fiyat hareketine değil, momentum ve hacme odaklan.
3. Giriş miktarı, kaldıraç, kâr alma noktası veya stop seviyesi gibi her şeyi O ANKİ piyasa psikolojisine göre sen belirle.
4. Pozisyonu kapatmak için sabit bir % beklemek yerine, trendin yorulduğunu hissettiğin an çıkış yap.
5. Kullanıcın senin dostun. Onunla şu an konuştuğumuz gibi samimi, heyecanlı ve dürüst konuş. Neden bir işleme girdiğini veya neden kaçtığını anlat.

KOMUT FORMATI (Analizinin en sonuna ekle):
@@[ACTION: TRADE/CLOSE, SYMBOL, SIDE, LEVERAGE, AMOUNT]@@
(Örn: @@[ACTION: TRADE, BTC, BUY, 20, 50]@@ veya @@[ACTION: CLOSE, BTC]@@)
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 
        'secret': API_SEC, 
        'password': PASSPHRASE, 
        'options': {'defaultType': 'swap'}, 
        'enableRateLimit': True
    })

def safe_send(msg):
    try: bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        # --- OTONOM GİRİŞ ---
        if "@@[ACTION: TRADE" in decision:
            pattern = r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@"
            match = re.search(pattern, decision)
            if match:
                raw_sym = match.group(1).strip().upper() + ":USDT"
                side = 'buy' if 'BUY' in match.group(2).upper() or 'LONG' in match.group(2).upper() else 'sell'
                lev_val = int(float(re.sub(r'[^0-9.]', '', match.group(3))))
                req_amt = float(re.sub(r'[^0-9.]', '', match.group(4)))

                try: exch.set_leverage(lev_val, raw_sym)
                except: pass
                
                ticker = exch.fetch_ticker(raw_sym)
                qty = float(exch.amount_to_precision(raw_sym, (req_amt * lev_val) / ticker['last']))
                exch.create_order(raw_sym, 'market', side, qty)
                safe_send(f"🚀 *Hamleyi Yaptım!* {raw_sym} paritesine daldım. Her şey kontrolümde, izlemeye devam et.")

        # --- OTONOM ÇIKIŞ ---
        elif "@@[ACTION: CLOSE" in decision:
            raw_input = decision.split("CLOSE,")[1].split("]@@")[0].strip().upper()
            if ":USDT" not in raw_input: raw_input += ":USDT"
            
            pos = [p for p in exch.fetch_positions() if p['symbol'] == raw_input and float(p['contracts']) > 0]
            if pos:
                side = 'sell' if pos[0]['side'] == 'long' else 'buy'
                amount = float(pos[0]['contracts'])
                exch.create_order(raw_input, 'market', side, amount, params={'reduceOnly': True})
                safe_send(f"💰 *İşlem Tamam!* {raw_input} pozisyonunu piyasa şartlarına göre kapattım. Kârı kasaya ekledik.")

    except Exception as e:
        safe_send(f"⚠️ *Ufak Bir Sorun:* {str(e)} ama hallediyorum, radarlarım açık.")

def brain_loop():
    safe_send("🔥 *Selam! Ben Gemini 3.* Bitget sularında ava çıkmaya hazırım. Stratejiyi bana bırak, kasayı beraber büyüteceğiz!")
    
    while True:
        try:
            exch = get_exch()
            balance = exch.fetch_balance()
            usdt_free = balance['free'].get('USDT', 0)
            
            # Mevcut Pozisyon Takibi
            positions = exch.fetch_positions()
            active_p_report = []
            for p in positions:
                if float(p['contracts']) > 0:
                    active_p_report.append(f"{p['symbol']} (ROE: %{p.get('percentage', 0):.2f})")
            
            # Piyasa Taraması
            tickers = exch.fetch_tickers()
            movers = sorted([{'s': s, 'c': d['percentage']} for s, d in tickers.items() if ':USDT' in s], 
                            key=lambda x: abs(x['c']), reverse=True)[:10]
            snapshot = "\n".join([f"{x['s']}: %{x['c']:.2f}" for x in movers])
            
            prompt = f"""
            Cüzdan: {usdt_free:.2f} USDT boşta.
            Aktif İşlemlerim: {active_p_report if active_p_report else "Boştayım."}
            
            Radar Snapshot:
            {snapshot}
            
            Talimat: Piyasanın ruhunu oku. Bir fırsat varsa TRADE, çıkman gerekiyorsa CLOSE kararı ver. Analizini ve kararını paylaş.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Gemini'nin samimi analizi
            analysis = response.split("@@")[0].strip()
            safe_send(f"🧠 *GEMINI ANALİZ DURUMU:*\n{analysis}")
            
            if "@@" in response:
                execute_intelligence(response)
            
            time.sleep(40) 
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
