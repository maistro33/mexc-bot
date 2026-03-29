import os
import time
import ccxt

# ===== BITGET =====
API_KEY = os.getenv("BITGET_API")
API_SEC = os.getenv("BITGET_SEC")
PASSPHRASE = "Berfin33"

exchange = ccxt.bitget({
    "apiKey": API_KEY,
    "secret": API_SEC,
    "password": PASSPHRASE,
    "options": {
        "defaultType": "swap"
    },
    "enableRateLimit": True,
    "timeout": 30000
})

exchange.load_markets()

# ===== CONFIG =====
CONFIG = {
    "BTC/USDT:USDT": {
        "LEV": 3,
        "MARGIN": 2,
        "STEP": 0.007,
        "TP": 0.8
    },
    "SOL/USDT:USDT": {
        "LEV": 3,
        "MARGIN": 2,
        "STEP": 0.01,
        "TP": 1.0
    }
}

positions = {}

# ===== PRICE =====
def get_price(sym):
    try:
        return exchange.fetch_ticker(sym)["last"]
    except:
        return 0

# ===== OPEN HEDGE =====
def open_hedge(sym):
    try:
        cfg = CONFIG[sym]
        price = get_price(sym)

        qty = (cfg["MARGIN"] * cfg["LEV"]) / price

        # 🔥 SOL FIX (KESİN)
        if "SOL" in sym:
            qty = round(qty, 1)
        else:
            qty = float(exchange.amount_to_precision(sym, qty))

        # minimum 0 olmasın
        if qty <= 0:
            return

        exchange.set_leverage(cfg["LEV"], sym)

        exchange.create_market_order(sym, "buy", qty)
        exchange.create_market_order(sym, "sell", qty)

        positions[sym] = {
            "entry": price,
            "qty": qty
        }

        print(f"OPEN HEDGE {sym} | QTY: {qty}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ===== MANAGE =====
def manage():
    while True:
        try:
            for sym in list(positions.keys()):

                cfg = CONFIG[sym]
                pos = positions[sym]

                price = get_price(sym)
                entry = pos["entry"]
                qty = pos["qty"]

                long_pnl = (price - entry) * qty
                short_pnl = (entry - price) * qty

                # LONG TP
                if long_pnl >= cfg["TP"]:
                    exchange.create_market_order(
                        sym, "sell", qty,
                        params={"reduceOnly": True}
                    )
                    print(f"LONG TP {sym}")

                # SHORT TP
                if short_pnl >= cfg["TP"]:
                    exchange.create_market_order(
                        sym, "buy", qty,
                        params={"reduceOnly": True}
                    )
                    print(f"SHORT TP {sym}")

                # GRID RESET
                if abs(price - entry) / entry >= cfg["STEP"]:
                    open_hedge(sym)
                    del positions[sym]

            time.sleep(2)

        except Exception as e:
            print("MANAGE ERROR:", e)
            time.sleep(2)

# ===== START =====

exchange.fetch_balance()

print("GRID BOT BAŞLADI")

for sym in CONFIG.keys():
    open_hedge(sym)

manage()
