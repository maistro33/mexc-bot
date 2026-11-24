# 🟢 Elle GERÇEK işlem — Dip Bulucu'daki "İşlemi aç" düğmesi (Sadık basınca açar; kendiliğinden ASLA açmaz)
# Sürüm E1.2 (24.11) — 10x açılmış LISTA/IRYS: marj eklenip 3x'e getirilir, likidasyon kontrol edilip stop %15'e geri konur (Sadık: B)
# Sürüm E1.1 (24.11) — DÜZELTME: kaldıraç 3x yerine 10x açılıyordu (3x çapraz moda yazılıyordu, emir izole açılıyordu → izolede Bitget varsayılanı 10x).
#   Artık önce izole moda geçer, 3x'i long+short için ayarlar ve borsadan OKUYUP DOĞRULAR; 3x değilse emir VERMEZ. Bekleyen eski emirler bir kez iptal edilip doğru kaldıraçla yeniden verilir.
# Sürüm E1.0 (23.11)
#   Railway değişkenleri (Sadık kendisi girer, sohbete yazılmaz): BITGET_API, BITGET_SEC, BITGET_PASS, ISLEM_SIFRE (en az 6 karakter)
#   • Açarken sinyal sunucuda yeniden kontrol edilir (✅ değilse açmaz) · limit emir, 2 gün dolmazsa iptal
#   • Dolunca borsaya STOP (mark fiyatı) · LONG (dip): TP merdiveni — TP'ler senin ayarın (%), son TP'den sonra aynı aralıkla devam;
#     TP1'de stop yerinde, TP2'de TP1'e, TP3'te TP2'ye… (▲ tik) · SHORT (tepe): borsaya %15 hedef + %15 stop (testte merdiven kötüydü)
#   • En çok 7 gün · 3 $ marj × 3x izole · en çok 3 işlem · toplam gerçekleşen zarar 6 $'a ulaşırsa yeni işlem açmaz
import hmac, json, math, os, threading, time, traceback
import dip

V = "E1.2 (24.11 02:10)"
MJ, LEV, MAXA, ZARAR_LIM, GUN, BEKLE_GUN = 3.0, 3, 3, 6.0, 7, 2
KLASOR = os.getenv("DATA_DIR") or ("/data" if os.path.isdir("/data") else ".")
DOSYA = os.path.join(KLASOR, "elle.json")
KIL = threading.RLock()
E = {"v": 1, "islem": {}, "gecmis": [], "log": [], "zarar": 0.0}
X = {"ex": None, "mt": 0, "fiyat": {}, "hata": "", "yanlis": []}

def log(m):
    with KIL: E["log"].append([int(time.time()), m]); del E["log"][:-80]
    print("ELLE", m, flush=True); kaydet()

def kaydet():
    with KIL:
        tmp = DOSYA + ".tmp"
        with open(tmp, "w") as f: json.dump(E, f, ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, DOSYA)

def yukle():
    try:
        d = json.load(open(DOSYA))
        if d.get("v") == 1: E.update(d)
    except Exception: pass

def hazir(): return bool(os.getenv("BITGET_API") and os.getenv("BITGET_SEC") and os.getenv("BITGET_PASS"))
def sifre_var(): return len(os.getenv("ISLEM_SIFRE", "")) >= 6

def sifre_dogru(s):
    now = time.time(); X["yanlis"] = [t for t in X["yanlis"] if now - t < 600]
    if len(X["yanlis"]) >= 5: return False, "Çok fazla yanlış şifre — 10 dk bekle."
    if sifre_var() and hmac.compare_digest(str(s or ""), os.getenv("ISLEM_SIFRE", "")): return True, ""
    X["yanlis"].append(now); return False, "İşlem şifresi yanlış."

def ex():
    if X["ex"] is None:
        import ccxt
        x = ccxt.bitget({"apiKey": os.getenv("BITGET_API"), "secret": os.getenv("BITGET_SEC"), "password": os.getenv("BITGET_PASS"),
                         "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 20000})
        x.load_markets(); X["ex"] = x; X["mt"] = time.time()
        try: x.set_position_mode(False, None, {"productType": "USDT-FUTURES"})          # tek yönlü mod (açık pozisyon varsa borsa reddeder, sorun değil)
        except Exception: pass
    elif time.time() - X["mt"] > 3600:
        try: X["ex"].load_markets(True); X["mt"] = time.time()
        except Exception: pass
    return X["ex"]

def cs_(s): return s[:-4] + "/USDT:USDT"
def ad(s): return s[:-4]

def poz(x, cs):
    return next((p for p in x.fetch_positions([cs]) if float(p.get("contracts") or 0) > 0), None)

def plan_iptal(x, cs, oid):
    if not oid: return
    for prm in ({"trigger": True, "planType": "pos_loss"}, {"trigger": True, "planType": "pos_profit"}, {"trigger": True, "planType": "loss_plan"},
                {"trigger": True, "planType": "profit_plan"}, {"trigger": True, "planType": "normal_plan"}):
        try: x.cancel_order(oid, cs, prm); return
        except Exception: pass

def plan_koy(x, cs, adet, fiyat, yon, tur="pos_loss"):
    """Pozisyon stopu/hedefi (mark fiyatıyla). Döner (id, fiyat) ya da (None, hata)."""
    fy = x.price_to_precision(cs, fiyat)
    try:
        r = x.private_mix_post_v2_mix_order_place_tpsl_order({"symbol": cs.split("/")[0] + "USDT", "productType": "USDT-FUTURES", "marginCoin": "USDT",
                                                              "planType": tur, "triggerPrice": fy, "triggerType": "mark_price", "holdSide": "buy" if yon == "long" else "sell"})
        oid = (r.get("data") or {}).get("orderId")
        if str(r.get("code")) == "00000" and oid: return oid, float(fy)
        hata = str(r)[:140]
    except Exception as e: hata = str(e)[:140]
    if tur != "pos_loss": return None, hata
    try:
        o = x.create_order(cs, "market", "sell" if yon == "long" else "buy", adet, None, {"stopLossPrice": fy, "reduceOnly": True, "marginMode": "isolated"})
        return o.get("id") or (o.get("info") or {}).get("orderId"), float(fy)
    except Exception as e: return None, str(e)[:140]

def kaldirac(x, cs, yon):
    """E1.1: izole + 3x (long ve short), sonra borsadan okuyup doğrula. Döner (True, "") ya da (False, neden)."""
    sym = cs.split("/")[0] + "USDT"; base = {"symbol": sym, "productType": "USDT-FUTURES", "marginCoin": "USDT"}; hata = ""
    try: x.private_mix_post_v2_mix_account_set_margin_mode(dict(base, marginMode="isolated"))
    except Exception as e: hata = "izole mod: " + str(e)[:80]
    for hs in ("long", "short", None):
        try: x.private_mix_post_v2_mix_account_set_leverage(dict(base, leverage=str(LEV), **({"holdSide": hs} if hs else {})))
        except Exception as e: hata = (hata + " · " if hata else "") + f"kaldıraç {hs or ''}: " + str(e)[:80]
    try:
        d = x.private_mix_get_v2_mix_account_account(base).get("data") or {}
        mm = d.get("marginMode"); lv = float(d.get("isolatedLongLever" if yon == "long" else "isolatedShortLever") or 0)
        if mm == "isolated" and abs(lv - LEV) < 0.01: return True, ""
        return False, f"borsada mod {mm}, izole {yon} kaldıraç {lv:g}x (istenen {LEV}x){' · ' + hata if hata else ''}"
    except Exception as e: return False, "kaldıraç okunamadı: " + str(e)[:100]

def plana_cevir(x):
    """E1.2: E1.0'da 10x açılmış işlemler → marj ekle (3x), likidasyonu borsadan oku, güvenliyse stopu %15'e taşı."""
    for s, q in list(E["islem"].items()):
        if q["durum"] != "acik" or q.get("lev_ok"): continue
        cs = cs_(s); sym = s; u = q["u"]
        try:
            p = poz(x, cs)
            if not p: continue
            g = q["giris"]; nom = q["adet"] * q["csz"] * g; mj = float(p.get("initialMargin") or p.get("collateral") or 0)
            ek = round(max(0.0, nom / LEV - mj) + 0.05, 2)
            if ek > 0.1:
                if ek > 3: log(f"⚠️ {ad(s)} eklenecek marj {ek:g} $ çok — 3 $ ile sınırlandı"); ek = 3.0
                tamam = False; hata = ""
                for hs in (q["yon"], None):
                    try:
                        x.private_mix_post_v2_mix_account_set_margin({"symbol": sym, "productType": "USDT-FUTURES", "marginCoin": "USDT", "amount": f"{ek:.2f}", **({"holdSide": hs} if hs else {})})
                        tamam = True; break
                    except Exception as e: hata = str(e)[:100]
                if not tamam: log(f"⚠️ {ad(s)} marj eklenemedi ({hata}) — stop yerinde kalıyor"); q["lev_ok"] = 1; continue
                log(f"🔧 {ad(s)} pozisyona {ek:g} $ marj eklendi (3x'e getirmek için)"); time.sleep(1.5)
                p = poz(x, cs)
            liq = float((p or {}).get("liquidationPrice") or 0); hedef = g * (1 - u * q["sl_y"] / 100)
            yeni = hedef if (liq and u * (hedef - liq) > 0 and abs(hedef / liq - 1) >= 0.02) else (liq * (1 + u * 0.03) if liq else q["stop"])
            if u * (q["stop"] - yeni) > 0 and stop_tasi(s, q, x, cs, yeni):     # stopu genişlet (daha uzağa)
                q["stop0"] = q["stop"]
                log(f"🔧 {ad(s)} stop {'%' + format(q['sl_y'], 'g') if yeni == hedef else 'likidasyonun önüne'} taşındı → {q['stop']:g} (likidasyon {liq:g})")
            q["lev_ok"] = 1
        except Exception as e: log(f"⚠️ {ad(s)} plana çevrilemedi: {str(e)[:100]}")
    kaydet()

def bekleyen_duzelt(x):
    """E1.1: E1.0'dan kalan bekleyen limit emirleri bir kez iptal et, 3x'i doğrula, aynı fiyattan yeniden ver."""
    for s, q in list(E["islem"].items()):
        if q["durum"] != "bekliyor" or q.get("lev_ok"): continue
        cs = cs_(s)
        try:
            o = x.fetch_order(q["oid"], cs)
            if float(o.get("filled") or 0) > 0 or o.get("status") == "closed": continue      # dolmuşsa normal akış
            x.cancel_order(q["oid"], cs); time.sleep(1)
            ok, h = kaldirac(x, cs, q["yon"])
            if not ok:
                with KIL: E["islem"].pop(s, None)
                log(f"✖️ {ad(s)} bekleyen emir iptal edildi — 3x ayarlanamadı: {h}"); continue
            o = x.create_order(cs, "limit", "buy" if q["u"] == 1 else "sell", q["adet"], q["lim"], {"marginMode": "isolated", "timeInForce": "GTC"})
            q["oid"] = o.get("id") or (o.get("info") or {}).get("orderId"); q["lev_ok"] = 1
            log(f"🔧 {ad(s)} bekleyen emir 3x ile yeniden verildi @ {q['lim']:g}")
        except Exception as e: log(f"⚠️ {ad(s)} bekleyen emir düzeltilemedi: {str(e)[:100]}")
    kaydet()

# ───────────────────────── AÇ ─────────────────────────
def ac(s, yon, tps, sl_y):
    s = s.upper().replace("/", "").replace("-", "").strip()
    if not s.endswith("USDT"): s += "USDT"
    if not hazir(): return False, "Bitget API anahtarı Railway'de yok (BITGET_API / BITGET_SEC / BITGET_PASS)."
    with KIL:
        if s in E["islem"]: return False, f"{ad(s)} zaten açık/bekleyen işlemlerde."
        if len(E["islem"]) >= MAXA: return False, f"En çok {MAXA} işlem — önce birini kapat."
        if E["zarar"] <= -ZARAR_LIM: return False, f"Toplam gerçek zarar {E['zarar']:.2f} $ — {ZARAR_LIM:g} $ sınırına ulaştı, yeni işlem kapalı."
    r = dip.analiz(s)                                                   # sinyal sunucuda yeniden kontrol
    if r.get("hata"): return False, r["hata"]
    if r.get("k") != "✅" or r.get("yon") != yon: return False, f"Sinyal artık geçerli değil: {r.get('k', '')} {r.get('baslik', '')}"
    u = 1 if yon == "long" else -1
    try:
        tps = sorted({round(float(t), 3) for t in tps if 0 < float(t) < 500})[:10] or [5, 10, 15, 20, 25]
        sl_y = float(sl_y)
    except Exception: return False, "TP/stop ayarı okunamadı."
    if not (2 <= sl_y <= 30): return False, "Stop %2 ile %30 arası olmalı (3x'te likidasyon ~%33)."
    if yon == "short": tps, sl_y = [dip.TP * 100], dip.SL * 100        # short: testteki gibi tek hedef %15, stop %15
    x = ex(); cs = cs_(s)
    if cs not in x.markets: return False, f"{ad(s)} Bitget'te bulunamadı."
    try:
        if poz(x, cs): return False, f"{ad(s)} için borsada zaten açık pozisyon var."
    except Exception as e: return False, f"Borsaya ulaşılamadı: {str(e)[:80]}"
    ok, h = kaldirac(x, cs, yon)
    if not ok: return False, f"Emir VERİLMEDİ — 3x kaldıraç doğrulanamadı: {h}"
    lim = float(x.price_to_precision(cs, r["plan"]["lim"])); mk = x.market(cs); csz = mk.get("contractSize") or 1
    adet = float(x.amount_to_precision(cs, MJ * LEV / lim / csz))
    if adet * csz * lim < 5.5:
        adim = float((mk.get("precision") or {}).get("amount") or 0) or adet or 1
        en_az = max(float(((mk.get("limits") or {}).get("amount") or {}).get("min") or 0), 5.6 / (lim * csz))
        a2 = math.ceil(en_az / adim - 1e-9) * adim
        if a2 * csz * lim <= 2 * MJ * LEV: adet = float(x.amount_to_precision(cs, a2 * 1.0000001))
    if adet * csz * lim < 5.5: return False, f"Pozisyon borsanın en küçük emrinden küçük ({adet * csz * lim:.2f} $)."
    try:
        o = x.create_order(cs, "limit", "buy" if u == 1 else "sell", adet, lim, {"marginMode": "isolated", "timeInForce": "GTC"})
    except Exception as e: return False, f"Emir reddedildi: {str(e)[:140]}"
    oid = o.get("id") or (o.get("info") or {}).get("orderId")
    with KIL:
        E["islem"][s] = {"s": s, "yon": yon, "u": u, "durum": "bekliyor", "oid": oid, "lim": lim, "adet": adet, "csz": csz, "t": int(time.time()),
                         "son": int(time.time()) + BEKLE_GUN * 86400, "tps_y": tps, "sl_y": sl_y, "tik": 0, "lev": LEV, "lev_ok": 1}
    log(f"🟢 {ad(s)} {yon.upper()} LİMİT emir verildi @ {lim:g} · {adet:g} adet (~{adet * csz * lim:.2f} $ · {LEV}x) · stop %{sl_y:g} · "
        + ("TP'ler %" + ", ".join(f"{t:g}" for t in tps) + " sonra devam" if yon == "long" else "hedef %15") + f" · {BEKLE_GUN} gün geçerli")
    return True, f"{ad(s)} {yon.upper()} limit emri verildi @ {lim:g}. Dolunca borsaya stop konacak."

# ───────────────────────── DOLUNCA ─────────────────────────
def doldu(s, q, x, cs, p):
    u = q["u"]; g = float(p.get("entryPrice") or q["lim"]); adet = float(p["contracts"]); st = g * (1 - u * q["sl_y"] / 100)
    liq = float(p.get("liquidationPrice") or 0); plev = float(p.get("leverage") or 0)
    if plev and abs(plev - LEV) > 0.01: log(f"⚠️ {ad(s)} borsada kaldıraç {plev:g}x (istenen {LEV}x)")
    q.update({"durum": "acik", "giris": g, "adet": adet, "t_ac": int(time.time()), "stop0": st, "stop": st, "tik": 0, "lev_ok": 1})
    if liq and u * (st - liq) <= 0:
        log(f"⚠️ {ad(s)} likidasyon {liq:g} stoptan ({st:g}) önce — stop likidasyonun önüne çekiliyor")
        st = liq * (1 + u * 0.03); q["stop"] = q["stop0"] = st
    sid, fy = plan_koy(x, cs, adet, st, q["yon"])
    if sid: q["sid"], q["stop"] = sid, fy; q["stop0"] = fy
    else: log(f"🚨 {ad(s)} STOP KONAMADI ({fy}) — tekrar denenecek; gerekirse Bitget'ten elle stop koy!")
    if q["yon"] == "long":
        d = q["tps_y"]; adim = (d[-1] - d[-2]) if len(d) > 1 else d[0]
        q["tp"] = [g * (1 + t / 100) for t in d]; q["adim"] = adim
    else:
        hd = g * (1 - q["tps_y"][0] / 100); q["tp"] = [hd]
        hid, hf = plan_koy(x, cs, adet, hd, "short", "pos_profit")
        if hid: q["hid"] = hid
        else: log(f"⚠️ {ad(s)} borsaya hedef konamadı ({hf}) — bot fiyatı izleyip kapatacak")
    log(f"✅ {ad(s)} {q['yon'].upper()} AÇILDI @ {g:g} · {adet:g} adet · borsada stop {q['stop']:g}" + (f" · hedef {q['tp'][0]:g}" if q["yon"] == "short" else f" · TP1 {q['tp'][0]:g}"))

def stop_tasi(s, q, x, cs, yeni):
    eski = q.get("sid")
    if eski: plan_iptal(x, cs, eski)
    sid, fy = plan_koy(x, cs, q["adet"], yeni, q["yon"])
    if not sid:
        sid, fy2 = plan_koy(x, cs, q["adet"], q["stop"], q["yon"])
        log(f"⚠️ {ad(s)} stop taşınamadı ({fy}) — eski stop geri kondu" if sid else f"🚨 {ad(s)} STOP YOK ({fy2}) — Bitget'ten elle stop koy!")
        q["sid"] = sid; return False
    q["sid"], q["stop"] = sid, fy; return True

def kapandi(s, q, x, cs, neden):
    pnl = None
    try:
        r = x.private_mix_get_v2_mix_position_history_position({"symbol": s, "productType": "USDT-FUTURES", "limit": "5"})
        for h in ((r.get("data") or {}).get("list") or []):
            if int(h.get("ctime") or 0) // 1000 >= q.get("t_ac", q["t"]) - 60:
                pnl = float(h.get("netProfit") if h.get("netProfit") not in (None, "") else h.get("pnl") or 0); break
    except Exception: pass
    c = X["fiyat"].get(s) or q.get("stop") or q["giris"]
    if pnl is None: pnl = q["adet"] * q["csz"] * q["u"] * (c - q["giris"]); neden += " (tahmini kâr)"
    for k in ("sid", "hid"):
        if q.get(k): plan_iptal(x, cs, q[k])
    with KIL:
        E["islem"].pop(s, None); E["zarar"] += pnl                 # net gerçekleşen (−6 $'da yeni işlem kapanır)
        E["gecmis"].append({"s": ad(s), "yon": q["yon"], "giris": q["giris"], "t": q.get("t_ac", q["t"]), "tk": int(time.time()), "pnl": round(pnl, 3), "neden": neden, "tik": q.get("tik", 0)})
        del E["gecmis"][:-100]
    log(f"{'💰' if pnl > 0 else '🔻'} {ad(s)} KAPANDI · {neden} · {pnl:+.3f} $")

def kapat(s, neden="✋ elle kapatıldı"):
    s = s.upper()
    if not s.endswith("USDT"): s += "USDT"
    q = E["islem"].get(s)
    if not q: return False, "Böyle bir işlem yok."
    if q.get("kapaniyor") and time.time() - q["kapaniyor"] < 30: return False, "Zaten kapatılıyor."
    q["kapaniyor"] = time.time()
    x = ex(); cs = cs_(s)
    if q["durum"] == "bekliyor":
        try: x.cancel_order(q["oid"], cs)
        except Exception as e: log(f"⚠️ {ad(s)} emir iptali: {str(e)[:80]}")
        try:
            p = poz(x, cs)
            if p: q["durum"] = "acik"; q.setdefault("giris", float(p.get("entryPrice") or q["lim"])); q["adet"] = float(p["contracts"])
        except Exception: pass
        if q["durum"] == "bekliyor":
            with KIL: E["islem"].pop(s, None)
            log(f"✖️ {ad(s)} bekleyen limit emir iptal edildi"); return True, "Emir iptal edildi."
    try:
        p = poz(x, cs)
        if p: x.create_order(cs, "market", "sell" if q["u"] == 1 else "buy", float(p["contracts"]), None, {"reduceOnly": True})
    except Exception as e: return False, f"Kapatılamadı: {str(e)[:120]} — Bitget'ten elle kapat!"
    time.sleep(1.5); kapandi(s, q, x, cs, neden); return True, "Kapatıldı."

# ───────────────────────── DÖNGÜ ─────────────────────────
def adim():
    if not E["islem"]: return
    tk = dip.get("tickers") or []
    if tk: X["fiyat"] = {t["symbol"]: float(t["lastPr"]) for t in tk if t.get("lastPr")}
    x = ex(); now = time.time()
    for s, q in list(E["islem"].items()):
        cs = cs_(s); c = X["fiyat"].get(s)
        if q.get("kapaniyor") and now - q["kapaniyor"] < 30: continue
        try:
            if q["durum"] == "bekliyor":
                if now - q.get("kont", 0) < 6: continue
                q["kont"] = now; o = x.fetch_order(q["oid"], cs); dol = float(o.get("filled") or 0); st = o.get("status")
                if st == "closed" or (dol > 0 and now > q["son"]):
                    if st != "closed":
                        try: x.cancel_order(q["oid"], cs)
                        except Exception: pass
                    p = None
                    for _ in range(5):
                        p = poz(x, cs)
                        if p: break
                        time.sleep(0.8)
                    if p: doldu(s, q, x, cs, p); kaydet()
                    else: log(f"🚨 {ad(s)} emir doldu ama pozisyon görünmedi — Bitget'ten kontrol et!")
                elif st == "canceled":
                    with KIL: E["islem"].pop(s, None)
                    log(f"✖️ {ad(s)} limit emir borsada iptal edilmiş (elle?) — listeden çıkarıldı")
                elif now > q["son"]:
                    x.cancel_order(q["oid"], cs)
                    with KIL: E["islem"].pop(s, None)
                    log(f"⌛ {ad(s)} limit emir {BEKLE_GUN} günde dolmadı — iptal edildi")
                continue
            # ── açık işlem ──
            if now - q.get("kont", 0) > 12:
                q["kont"] = now
                if not poz(x, cs):
                    u = q["u"]; c0 = c or q["stop"]
                    neden = "🎯 hedef (borsa)" if q["yon"] == "short" and u * (c0 - q["tp"][0]) >= 0 else ("🔒 kâr kilidi stopu (borsa)" if u * (q["stop"] - q["giris"]) > 0 else "⛔ stop (borsa)")
                    kapandi(s, q, x, cs, neden); continue
                if not q.get("sid"):
                    sid, fy = plan_koy(x, cs, q["adet"], q["stop"], q["yon"])
                    if sid: q["sid"] = sid; log(f"✅ {ad(s)} borsaya stop kondu {fy:g}")
            if not c: continue
            u = q["u"]
            if now - q.get("t_ac", q["t"]) > GUN * 86400: kapat(s, f"⌛ süre ({GUN} gün)"); continue
            if q["yon"] == "short":
                if not q.get("hid") and u * (c - q["tp"][0]) >= 0: kapat(s, "🎯 hedef (bot)")
                continue
            k = q["tik"]; yk = k
            while u * (c - q["tp"][k]) >= 0:
                k += 1
                if k >= len(q["tp"]) - 1: q["tp"].append(q["tp"][-1] + q["giris"] * q["adim"] / 100)      # son TP'den sonra aynı aralıkla devam
            if k > yk:
                q["tik"] = k; q["tik_t"] = int(now)
                yeni = q["tp"][k - 2] if k >= 2 else None
                if yeni and u * (yeni - q["stop"]) > 0:
                    if stop_tasi(s, q, x, cs, yeni):
                        log(f"▲ {ad(s)} TP{k} ✓ · stop → {q['stop']:g} (TP{k - 1}) · kilitli {q['adet'] * q['csz'] * u * (q['stop'] - q['giris']):+.3f} $")
                    else: q["tik"] = yk                                 # olmadıysa sonra tekrar dener
                else: log(f"▲ {ad(s)} TP{k} ✓ · stop yerinde ({q['stop']:g})")
                kaydet()
        except Exception as e:
            X["hata"] = f"{ad(s)}: {str(e)[:120]}"; traceback.print_exc()

def dongu():
    yukle()
    if hazir() and any(q["durum"] == "bekliyor" and not q.get("lev_ok") for q in E["islem"].values()):
        try: bekleyen_duzelt(ex())
        except Exception as e: log(f"⚠️ bekleyen emir düzeltme: {str(e)[:100]}")
    if hazir() and any(q["durum"] == "acik" and not q.get("lev_ok") for q in E["islem"].values()):
        try: plana_cevir(ex())
        except Exception as e: log(f"⚠️ plana çevirme: {str(e)[:100]}")
    while True:
        try: X["hata"] = ""; adim()
        except Exception as e: X["hata"] = str(e)[:140]; traceback.print_exc()
        time.sleep(3)

def basla(): threading.Thread(target=dongu, daemon=True).start()

def veri():
    P = []
    with KIL:
        for s, q in E["islem"].items():
            c = X["fiyat"].get(s); d = {k: q.get(k) for k in ("yon", "durum", "lim", "giris", "stop", "stop0", "tp", "tik", "tik_t", "t", "son", "sl_y", "tps_y")}
            d["s"] = ad(s); d["c"] = c
            if q["durum"] == "acik" and c:
                d["pnl"] = round(q["adet"] * q["csz"] * q["u"] * (c - q["giris"]), 3)
                d["kilit"] = round(q["adet"] * q["csz"] * q["u"] * (q["stop"] - q["giris"]), 3)
            P.append(d)
        G = E["gecmis"][-20:][::-1]
    return {"v": V, "hazir": hazir(), "sifre": sifre_var(), "P": P, "son": G, "log": E["log"][-25:][::-1], "zarar": round(E["zarar"], 3),
            "toplam": round(sum(g["pnl"] for g in E["gecmis"]), 3), "n": len(E["gecmis"]), "hata": X["hata"], "lim": {"mj": MJ, "lev": LEV, "max": MAXA, "zarar": ZARAR_LIM}}
