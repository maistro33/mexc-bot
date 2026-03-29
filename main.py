import os
import time
import ccxt

exchange = ccxt.bitget({
    "apiKey": os.getenv("BITGET_API"),
    "secret": os.getenv("BITGET_SEC"),
    "password": os.getenv("BITGET_PASS"),
    "options": {"defaultType": "swap"},
    "enableRateLimit": True
})

# ================= AYAR =================

CONFIG = {
    "BTC/USDT:USDT": {
        "LEV": 3,
        "MARGIN": 2,
        "GRID_STEP": 0.007,   # %0.7
        "TP": 0.8
    },
    "SOL/USDT:USDT": {
        "LEV": 3,
        "MARGIN": 2,
        "GRID_STEP": 0.01,    # %1
        "TP": 1.0
    }
}

positions = {}

# ================= PRICE =================

def get_price(sym):
    try:
        return exchange.fetch_ticker(sym)["last"]
    except:
        return 0

# ================= OPEN =================

def open_hedge(sym):
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

# ================= MANAGE =================

def manage():
    global positions

    while True:
        try:
            for sym in list(positions.keys()):

                cfg = CONFIG[sym]
                pos = positions[sym]

                entry = pos["entry"]
                qty = pos["qty"]

                p = get_price(sym)

                long_pnl = (p - entry) * qty
                short_pnl = (entry - p) * qty

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

                # GRID yeniden aç
                if abs(p - entry) / entry >= cfg["GRID_STEP"]:
                    open_hedge(sym)
                    del positions[sym]

            time.sleep(2)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(2)

# ================= START =================

for s in CONFIG.keys():
    open_hedge(s)

manage()
