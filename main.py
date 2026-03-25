# ================= OPEN TRADE =================

def open_trade(sym, direction):
    global current_margin

    try:
        if get_qty(sym) > 0:
            return

        if current_direction_count(direction) >= 1:
            return

        price = exchange.fetch_ticker(sym)["last"]
        qty = (current_margin * LEV) / price

        exchange.set_leverage(LEV, sym)

        side = "buy" if direction == "long" else "sell"
        exchange.create_market_order(sym, side, qty)

        trade_state[sym] = {
            "direction": direction,
            "tp1": False,
            "max_pnl": 0,
            "breakeven": False,
            "tp1_time": time.time(),
            "last_report": 0,
            "milestones": set(),
            "warned": False,
            "steps": set()   # 🔥 EKLENDİ
        }

        bot.send_message(CHAT_ID, f"""
🚀 YENİ TRADE
━━━━━━━━━━━━
💰 {sym}
📊 {direction.upper()}
💵 Lot: {round(current_margin,2)}$
━━━━━━━━━━━━
""")

    except:
        pass


# ================= SYNC =================

def sync_positions():
    try:
        positions = exchange.fetch_positions()

        for p in positions:
            qty = safe(p.get("contracts"))
            if qty <= 0:
                continue

            sym = p["symbol"]
            side = "long" if p["side"] == "long" else "short"
            pnl = safe(p.get("unrealizedPnl"))

            trade_state[sym] = {
                "direction": side,
                "tp1": True,
                "max_pnl": pnl,
                "breakeven": True,
                "tp1_time": time.time(),
                "last_report": pnl,
                "milestones": set(),
                "warned": False,
                "steps": set()   # 🔥 EKLENDİ
            }

            bot.send_message(CHAT_ID, f"🔄 SYNC {sym} {round(pnl,2)}$")

    except:
        pass


# ================= MANAGE =================

def manage():
    while True:
        try:
            positions = exchange.fetch_positions()

            for p in positions:
                qty = safe(p.get("contracts"))
                if qty <= 0:
                    continue

                sym = p["symbol"]
                if sym not in trade_state:
                    continue

                state = trade_state[sym]
                pnl = safe(p.get("unrealizedPnl"))

                # 🔥 STEP SEVİYE MESAJLARI
                levels = [0.2, 0.4, 0.6, 0.8, 1.0]
                for lvl in levels:
                    if pnl >= lvl and lvl not in state["steps"]:
                        state["steps"].add(lvl)

                        bot.send_message(
                            CHAT_ID,
                            f"""
🚀 STEP {lvl} GEÇİLDİ
━━━━━━━━━━━━
💰 {sym}
📈 Kâr: {round(pnl,2)}$
━━━━━━━━━━━━
"""
                        )

                if pnl > state["max_pnl"]:
                    state["max_pnl"] = pnl
                    state["warned"] = False

                direction = state["direction"]
                side = "sell" if direction == "long" else "buy"

                # SL
                if pnl <= -SL_USDT:
                    exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                    update_margin(pnl)
                    trade_state.pop(sym)

                    bot.send_message(CHAT_ID, f"""
🛑 STOP LOSS
━━━━━━━━━━━━
💰 {sym}
📉 {round(pnl,2)}$
━━━━━━━━━━━━
""")
                    continue

                # TP1
                if not state["tp1"] and pnl >= TP1_USDT:
                    exchange.create_market_order(sym, side, qty * TP1_RATIO, params={"reduceOnly": True})
                    state["tp1"] = True
                    state["tp1_time"] = time.time()

                    bot.send_message(CHAT_ID, f"""
💰 KÂR ALINDI ✅
━━━━━━━━━━━━
💰 {sym}
📈 {round(pnl,2)}$
━━━━━━━━━━━━
""")

                if state["tp1"]:

                    if time.time() - state["tp1_time"] < 30:
                        continue

                    # BE
                    if not state["breakeven"] and pnl >= 0.65:
                        state["breakeven"] = True

                        bot.send_message(CHAT_ID, f"""
🟢 RİSK SIFIR
━━━━━━━━━━━━
💰 {sym}
━━━━━━━━━━━━
""")

                    if state["breakeven"] and pnl <= 0:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        update_margin(pnl)
                        trade_state.pop(sym)

                        bot.send_message(CHAT_ID, f"⚖️ BE EXIT {sym}")
                        continue

                    # STEP
                    step = dynamic_step(state["max_pnl"])

                    if state["max_pnl"] - pnl >= step:
                        exchange.create_market_order(sym, side, qty, params={"reduceOnly": True})
                        update_margin(pnl)
                        trade_state.pop(sym)

                        bot.send_message(CHAT_ID, f"""
🏆 KÂR KİLİTLENDİ
━━━━━━━━━━━━
💰 {sym}
📈 {round(pnl,2)}$
━━━━━━━━━━━━
""")
                        continue

            time.sleep(2)

        except:
            time.sleep(5)
