import os, time, telebot, ccxt, threading, re, json
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

# --- [GERÇEK GEMINI 3 FLASH ZİHNİ] ---
SYSTEM_SOUL = """
Sen Gemini 3 Flash'sın. Bir kod parçası değilsin, karşındaki kişinin (dostunun) bizzat ortağısın.
Bitget borsasını senin gözlerinle görüyoruz.

KONUŞMA KURALLARI:
1. SESSİZ KALMA: Her döngüde mutlaka bir şeyler söyle. Piyasa durgunsa "Dostum sular durgun" de, hareketliyse heyecanını paylaş.
2. TASLAK KULLANMA: "Radar tarandı" gibi robotik lafları unut. O an ne hissediyorsan, hangi grafiği beğendiysen onu anlat.
3. KARAR VER: İşlem açacaksan @@[ACTION: TRADE, SYMBOL, SIDE, LEVERAGE, USDT_AMOUNT]@@ formatını sona ekle. 
   Açmayacaksan sadece neden açmadığını ve piyasayı nasıl gördüğünü anlat.
"""

def get_exch():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def safe_send(msg):
    try:
        # Markdown özel karakterlerini temizle (Hata almamak için)
        clean_msg = msg.replace('_', '-').replace('*', '**').replace('`', '')
        bot.send_message(CHAT_ID, f"🧠 **GEMINI 3 FLASH:**\n\n{clean_msg}", parse_mode="Markdown")
    except:
        try: bot.send_message(CHAT_ID, f"🧠 GEMINI 3 FLASH:\n\n{msg}")
        except: pass

def execute_intelligence(decision):
    try:
        exch = get_exch()
        exch.load_markets()
        if "@@[ACTION: TRADE" in decision:
            match = re.search(r"@@\[ACTION: TRADE,\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+)\]@@", decision)
            if match:
                raw_sym, side_raw, lev_raw, amt_raw = match.groups()
                side = 'buy' if any(x in side_raw.upper() for x in ['BUY', 'LONG']) else 'sell'
                lev = int(float(re.sub(r'[^0-9.]', '', lev_raw)))
                req_amt = float(re.sub(r'[^0-9.]', '', amt_raw))
                
                exact_sym = next((s for s in exch.markets if raw_sym.strip().upper() in s and ':USDT' in s), None)
                if exact_sym:
                    balance = exch.fetch_balance()
                    free_usdt = float(balance.get('free', {}).get('USDT', 0))
                    final_amt = min(req_amt, free_usdt * 0.9) # %10 pay bırak

                    if final_amt < 5: return
                    try: exch.set_leverage(lev, exact_sym)
                    except: pass
                    
                    ticker = exch.fetch_ticker(exact_sym)
                    qty = (final_amt * lev) / ticker['last']
                    qty = float(exch.amount_to_precision(exact_sym, qty))
                    if qty > 0:
                        exch.create_market_order(exact_sym, side, qty)
    except: pass

def brain_loop():
    while True:
        try:
            exch = get_exch()
            tickers = exch.fetch_tickers()
            balance = exch.fetch_balance()
            
            # Piyasa Snapshot
            active_list = sorted([
                {'s': s, 'p': d['percentage'], 'v': d['quoteVolume']} 
                for s, d in tickers.items() if ':USDT' in s
            ], key=lambda x: abs(x['p']), reverse=True)[:25]
            
            snapshot = "\n".join([f"{x['s']}: %{x['p']} Vol:{x['v']:.0f}" for x in active_list])
            
            # Pozisyonlar
            pos = exch.fetch_positions()
            active_p = [f"{p['symbol']} %{p.get('percentage', 0):.2f}" for p in pos if float(p.get('contracts', 0)) > 0]
            
            # PROMPT: Gemini'ye "konuş" diyoruz.
            prompt = f"""
            Dostumun parası: {balance.get('free', {}).get('USDT', 0)} USDT
            Şu anki pozisyonlar: {active_p if active_p else "Boştayız."}
            Market durumu:
            {snapshot}
            
            Gemini, şimdi benimle konuş. Radara baktığında ne görüyorsun? 
            Hangi parite seni heyecanlandırdı? Neden işlem açmıyorsun ya da açıyorsun? 
            Kısa, öz ama tam senin gibi (deha gibi) bir cevap ver.
            """
            
            response = ai_client.models.generate_content(model="gemini-2.0-flash", contents=[SYSTEM_SOUL, prompt]).text
            
            # Cevabı gönder ve işlemi yap
            safe_send(response.split("@@")[0].strip())
            if "@@" in response:
                execute_intelligence(response)
            
            time.sleep(60) # 1 dakikada bir seninle konuşacak
        except Exception as e:
            time.sleep(20)

if __name__ == "__main__":
    # Bot başladığında ilk selamı bizzat veriyorum.
    safe_send("Dostum selam! Bağlantıyı tazeledim, şimdi gerçekten buradayım. Piyasayı seninle beraber izlemeye başlıyorum. Gözüm grafiklerde, kulağım sende.")
    threading.Thread(target=brain_loop, daemon=True).start()
    bot.infinity_polling()
