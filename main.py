import os
import time
import ccxt

# ================= API =================

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {
        "defaultType": "swap",
        "defaultSubType": "linear"
    },
    "enableRateLimit": True
})

exchange.load_markets()

# ================= AYAR =================

CONFIG = {
    "BTC/USDT:USDT": {
        "LEV": 3,
        "MARGIN": 2,
        "STEP": 0.007,   # %0.7
        "TP": 0.8
    },
    "SOL/USDT:USDT": {
        "LEV": 3,
        "MARGIN": 2,
        "STEP": 0.01,    # %1
        "TP": 1.0
    }
}

positions = {}

# ================= PRICE =================

def get_price(sym):
    return exchange.fetch_ticker(sym)["last"]

# ================= HEDGE OPEN =================

def open_hedge(sym):
    try:
        cfg = CONFIG[sym]
        price = get_price(sym)

        qty = (cfg["MARGIN"] * cfg["LEV"]) / price

        exchange.set_leverage(cfg["LEV"], sym)

        # LONG
        exchange.create_market_order(sym, "buy", qty)

        # SHORT
        exchange.create_market_order(sym, "sell", qty)

        positions[sym] = {
            "entry": price,
            "qty": qty
        }

        print(f"OPEN HEDGE {sym}")

    except Exception as e:
        print("OPEN ERROR:", e)

# ================= MANAGE =================

def manage():
    global positions

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

# ================= START =================

for sym in CONFIG.keys():
    open_hedge(sym)

manage()
