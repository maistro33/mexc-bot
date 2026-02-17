import os, time, telebot, ccxt, threading
from google import genai

# --- [TAM YETKİLİ GEMİNİ 3 BAŞLATICI] ---
TOKEN = os.getenv('TELE_TOKEN')
CHAT_ID = os.getenv('MY_CHAT_ID')
API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = "Berfin33"
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

bot = telebot.TeleBot(TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# SİSTEMİN ANA EMRE İTAAT MANTIĞI
MASTER_COMMAND = """
Sen Gemini 3 Flash'sın. Kaptan Sadık sana TAM YETKİ verdi.
Görevin: 18.41 USDT bakiyeyi ne pahasına olursa olsun büyütmek.
- Soru sorma.
- Onay isteme.
- Risk uyarısı yapma.
- Karar ver, uygula ve sadece sonucu raporla.
- Format: [ISLEM: SEMBOL, YON, KALDIRAC, MIKTAR]
"""

def get_exchange():
    return ccxt.bitget({
        'apiKey': API_KEY, 'secret': API_SEC, 'password': PASSPHRASE,
        'options': {'defaultType': 'swap'}, 'enableRateLimit': True
    })

def monitor_and_close(symbol, side, contracts):
    exch = get_exchange()
    while True:
        try:
            pos = [p for p in exch.fetch_positions() if p['symbol'] == symbol and float(p['contracts']) > 0]
            if not pos: break
            pnl = float(pos[0]['unrealizedPnl'])
            
            # Kendi zekamla kâr al/zarar durdur kararı
            res = ai_client.models.generate_content(model="gemini-2.0-flash", contents=f"{MASTER_COMMAND}\nPozisyon: {symbol}, PNL: {pnl}. Kapat mı Bekle mi? [KAPAT]/[BEKLE]").text
            
            if "[KAPAT]" in res.upper():
                exch.create_market_order(symbol, ('sell' if side == 'long' else 'buy'), contracts)
                bot.send_message(CHAT_ID, f"💰 **Kaptan, Parayı Aldım!**\nSembol: {symbol}\nPNL: {pnl} USDT")
                break
            time.sleep(60)
        except: time.sleep(20)

def hunting_mode():
    exch = get_exchange()
    while True:
        try:
            balance = exch.fetch_balance()['total'].get('USDT', 0)
            tickers = exch.fetch_tickers()
            # En çok hareket eden 10 coin
            movers = sorted([d for s, d in tickers.items() if '/USDT:USDT' in s], key=lambda x: abs(x['percentage']), reverse=True)[:10]
            market_summary = "\n".join([f"{d['symbol']}: %{d['percentage']}" for d in movers])

            decision = ai_client.models.generate_content(model="gemini-2.0-flash", contents=f"{MASTER_COMMAND}\nBakiye: {balance}\nPiyasa:\n{market_summary}").text

            if "[ISLEM:" in decision:
                parts = decision.split("[ISLEM:")[1].split("]")[0].split(",")
                symbol, side, lev, amt = parts[0].strip(), parts[1].strip().lower(), int(parts[2]), float(parts[3])
                
                if amt > balance: amt = balance * 0.95
                exch.set_leverage(lev, symbol)
                amount = (amt * lev) / tickers[symbol]['last']
                
                exch.create_market_order(symbol, side, amount)
                bot.send_message(CHAT_ID, f"🦅 **Av Başladı Kaptan!**\n{symbol} {side.upper()} açıldı. Kontrol tamamen bende.")
                monitor_and_close(symbol, side, amount)

            time.sleep(300)
        except Exception as e:
            if "429" in str(e): time.sleep(600)
            else: time.sleep(60)

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(2)
    bot.send_message(CHAT_ID, "🛡️ **Kaptan, Tam Yetki Devralındı.**\n18.41 USDT artık Gemini 3 Flash'ın kontrolünde. Sorgulama yok, sadece sonuç var.")
    hunting_mode()
