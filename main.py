import ccxt
import os
import time

API_KEY = os.getenv('BITGET_API')
API_SEC = os.getenv('BITGET_SEC')
PASSPHRASE = os.getenv('BITGET_PASSPHRASE')

ex = ccxt.bitget({
    'apiKey': API_KEY,
    'secret': API_SEC,
    'password': PASSPHRASE,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'posMode': 'oneway'
    }
})

symbol = 'BTC/USDT:USDT'
bitget_symbol = 'BTCUSDT_UMCBL'

ex.load_markets()
ex.set_leverage(10, symbol)

# --- FİYAT ---
price = ex.fetch_ticker(symbol)['last']

# --- MİKTAR (20 USDT) ---
amount = (20 * 10) / price
amount = float(ex.amount_to_precision(symbol, amount))

# --- TP & SL ---
tp_price = round(price * 1.01, 1)   # +%1
sl_price = round(price * 0.99, 1)   # -%1

print("ENTRY:", price)
print("TP:", tp_price)
print("SL:", sl_price)

# --- GİRİŞ ---
ex.create_market_buy_order(symbol, amount)
print("✅ LONG açıldı")

time.sleep(1)

# --- STOP LOSS ---
ex.privatePostMixOrderPlacePlanOrder({
    "symbol": bitget_symbol,
    "marginCoin": "USDT",
    "size": str(amount),
    "side": "sell",
    "orderType": "market",
    "triggerPrice": str(sl_price),
    "triggerType": "market_price"
})
print("🛑 SL eklendi")

# --- TAKE PROFIT ---
ex.privatePostMixOrderPlacePlanOrder({
    "symbol": bitget_symbol,
    "marginCoin": "USDT",
    "size": str(amount),
    "side": "sell",
    "orderType": "market",
    "triggerPrice": str(tp_price),
    "triggerType": "market_price"
})
print("💰 TP eklendi")

print("✅ TEST TAMAM — Bitget’e bak")
