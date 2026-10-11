# GHOST KISA BOT  —  temiz yeniden yazım
# Strateji (tek ve basit): 5 dk'lık mum gövdesi >= EŞİK % ise, mum kapanınca yeni mumun başında gir.
#   TERSİNE : yükselene SAT (short), düşene AL (long)      [varsayılan]
#   TAKİP   : yükselene AL (long),  düşene SAT (short)
# Çıkış: kademeli kilit (+0.42 → +0.50 → +0.75 → +1.00$), BORSADA stop (açılışta hemen), satış yok.
#
# SÜRÜM GEÇMİŞİ (her değişiklikte VERSIYON ve buraya bir satır eklenir)
# v4.0 09.10 22:50  Sıfırdan temiz yazım: tek strateji çekirdeği (mum gövdesi, TERSİNE/TAKİP panelden), her 5 dk'da tek fiyat okuması,
#                   açılışta zorunlu borsa stopu, kaldıraç doğrulama + fazlayı küçültme, günlük limit artık kalıcı kilit DEĞİL
#                   (limit değişince/yeni günde bot otomatik devam eder), yeni panel, saat dilimi Stockholm
# v4.1 09.10 22:45  Yeni mod "ARALIK": coinin son N saatlik (varsayılan 4s) aralığında dipteyse AL, tepedeyse SAT (yatay gezen coinler; geniş/trend
#                   aralıklar atlanır). Panelden seçilir, 5 dk gövde modları duruyor.
# v4.2 09.10 22:45  Ayarlar ekranı sadeleştirildi: her ayarın kendi başlığı, kısa düğme yazıları, seçili moda göre sadece ilgili ayarlar.
# v4.3 09.10 22:50  Hisse/altın/emtia (Bitget isRwa=YES) otomatik tanınıyor; "Hisse senetleri KAPALI" artık hepsini (ASTS dahil) engeller.
# v4.4 10.10 09:55  Hantal (en hacimli 40) coinler taramadan çıkarıldı; kalanlar 24s'te en çok oynayana göre sıralanır. Zararla kapanan coine 2 saat yasak.
# v4.5 10.10 10:30  İlk kilit artık marjinden bağımsız: panelden "NET KÂR ($)" (varsayılan +0.30$). Ücret+kayma payı otomatik eklenir (2$ marjinde ilk kilit ≈0.51$'da).
# v4.6 10.10 13:45  İlk kilit net seçeneği +0.10$ eklendi (+0.1 / +0.2 / +0.3 / +0.5).
# v4.7 10.10 13:50  İlk açılışta bir kerelik "hiç durmasın" ayarı: Aralık modu, 1$ marjin, 5 işlem, uç %15, pencere 2 saat, bekleme 5 dk, limit -5$.
# v4.8 10.10 22:20  Aralık modu için isteğe bağlı YÖN FİLTRESİ (Kapalı / 15dk dönüş / 4s trend+dönüş). Varsayılan KAPALI (backtestte fayda göstermedi).
# v4.9 10.10 22:50  MİKRO: her sinyalde emir defteri dengesizliği, spread, açık pozisyon (OI) kaydedilir (mikro.jsonl, /mikro ile özet+dosya). MİKRO FİLTRE (varsayılan AÇIK): spread >%0.10 ya da emir defteri işlem yönünün aleyhineyse girmez.
# v4.10 10.10 22:55  Açılış mesajına emir defteri dengesizliği + spread satırı; mikro.jsonl'ye giriş kaydı da yazılır.
# v4.11 11.10 01:10  MİKRO artık 3 modlu: KAPALI / ATLA (eski filtre) / ÇEVİR: sinyalde emir defteri işlem yönünün aleyhine ağırsa (imb ≤ −0.10) YÖN TERSİNE ÇEVRİLİR
#                   (NIL örneği: short sinyali, alış baskın → long). −0.10…+0.10 arası ve defter yoksa sinyal yönü korunur. ÇEVİR modunda spread filtresi uygulanmaz. Test edilmedi, deneysel.
# v4.12 11.10 01:30  Yeni mod "DEFTER": aralık sinyali olmadan, emir defteri (ilk 10 kademe) belirgin yatıksa (varsayılan |imb| ≥ 0.5) ağır tarafta işlem açar
#                   (alış ağır → long, satış ağır → short). Spread >%0.10 ise girmez. Her 5 dk'da en hareketli 40 coin taranır. Deneysel, backtest YOK.
# v4.13 11.10 02:00  BÜYÜK İŞLEM AKIŞI: her sinyalde son 1/5/15 dk'da gerçekleşen BÜYÜK alım/satım işlemlerinin net yönü (akis1/akis5/akis15, işlem yönünde +) ölçülüp
#                   mikro.jsonl'ye yazılır ve açılış mesajında görünür (varsayılan sadece KAYIT). Panelde DEFTER modu için isteğe bağlı "AKIŞ ONAYI" (varsayılan KAPALI):
#                   açıkken büyük akış (5 dk) işlem yönünün aleyhineyse Defter girişi atlanır. /mikro özetine akış karşılaştırması eklendi.
# v4.14 11.10 14:30  GÖLGE (kâğıt üstü) İŞLEM: her DEFTER girişinde, aynı anda TERS yöndeki hayali işlem de aynı kaldıraç/stop/kademeli kilitle 1 dk'lık mumlarla takip edilir
#                   (gerçek emir YOK). Sonuç mikro.jsonl'ye "golge" olarak yazılır; /mikro özeti gerçek ile gölge (ters yön) toplamını yan yana gösterir.
# v4.15 11.10 18:00  DÜZELTME: mikro.jsonl'deki "cikis" PnL'si borsada kapanan işlemlerde TAHMİNİ (komisyonsuz/kayma yok) idi, gerçeği olduğundan yüksek gösteriyordu
#                   (CT örneği: kayıt +0.18$, Bitget net +0.09$). Artık borsanın gerçek net PnL'si gelince mikro.jsonl'ye "gercek" kaydı yazılır ve /mikro özeti
#                   tahmini değil GERÇEK net PnL ile hesaplanır (gerçeği henüz gelmemiş kayıtlar ayrıca belirtilir).
# v4.16 11.10 18:30  DEFTER YÖNÜ düğmesi (Aynı / Ters): "Ters" seçilirse Defter, emir defterinin ağır olduğu yönün TERSİNE işlem açar (gölge ölçüm iyi çıkarsa kullanılsın diye).
#                   Varsayılan AYNI (davranış değişmez). Ters seçiliyken gölge takibi de ters çalışır (yani defter yönündeki hayali işlemi izler).
VERSIYON = "v4.16 (11.10 18:30)"

import os, time, json, threading, datetime as dt
import ccxt, telebot
from telebot import types

E = os.getenv
MARJIN    = float(E("MARJIN", "1"))          # USDT / işlem
MAX_POS   = int(E("MAX_POS", "3"))
LEV_TAVAN = int(E("LEV_TAVAN", "20"))        # coinin izin verdiği en yüksek kaldıraç denenir (bu sayıyı geçmez)
SL_ORAN   = float(E("SL_ORAN", "0.8"))       # zarar stopu: marjinin bu oranı
COIN_SAYI = int(E("COIN_SAYI", "150"))       # hacme göre ilk N coin izlenir
MIN_SL_PCT = float(E("MIN_SL_PCT", "1.5"))   # stop fiyattan en az bu % uzak olmalı; değilse kaldıraç düşürülür
CHAT      = int(E("MY_CHAT_ID", "0"))
BAR       = 300                              # mum süresi (sn): 5 dakika

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(E("TZ_ADI", "Europe/Stockholm")); dt.datetime.now(TZ)
except Exception:
    TZ = dt.timezone(dt.timedelta(hours=2))
def gun(t=None): return dt.datetime.fromtimestamp(t or time.time(), TZ).strftime("%Y-%m-%d")
def saat(t): return dt.datetime.fromtimestamp(t, TZ).strftime("%d.%m %H:%M")

DOSYA = "/data/ayar.json" if os.path.isdir("/data") else "ayar.json"
HARIC = "BTC ETH XRP ADA DOGE SOL BNB LTC BCH TRX LINK DOT AVAX XLM ETC ATOM SHIB PEPE".split()
HISSE = set("PLTR MRNA MSTU AAOI AXTI ORCL SOXL CRWV MUU TSLA NVDA AAPL MSFT AMZN GOOGL AMD INTC MSTR HOOD SPY QQQ NFLX BABA SMCI AVGO TSM MU PYPL UBER IONQ RGTI SOFI RIVN NIO".split())
LADDER = (125, 100, 75, 50, 30, 25, 20, 15, 10, 5, 3, 2)
A = {"v": 3, "calis": True, "mod": "ters", "esik": 5.0, "marjin": MARJIN, "max_pos": MAX_POS, "lev": LEV_TAVAN, "sl": SL_ORAN,
     "gunluk": 3.0, "bekle": 15, "pen": 48, "net": 0.30, "yf": "kapali", "mf": "kapali", "dt": 0.5, "dn": 40, "ao": False, "dy": "ayni", "hantal": 40, "uc": 10, "gen": 8.0, "lv": [0.42, 0.50, 0.75, 1.00], "hk": True, "haric": list(HARIC)}
lev_cap = {}                 # coin -> borsanın kabul ettiği en yüksek kaldıraç
acik, yasak, gecmis = {}, {}, []
KIL = threading.RLock()
try:
    d = json.load(open(DOSYA)); a0 = d.get("A", {})
    if a0.get("v") == 3: A.update(a0)
    elif a0.get("haric"): A["haric"] = a0["haric"]          # eski sürümden sadece hariç listesini al
    acik.update(d.get("acik", {})); gecmis.extend(d.get("gecmis", [])); lev_cap.update(d.get("cap", {}))
except Exception: pass
if A.get("onayar") != "v4.7":      # v4.7: "hiç durmasın" ayarları BİR KERE uygulanır (sonra panelden değiştirilebilir)
    A.update({"mod": "aralik", "marjin": 1, "max_pos": 5, "uc": 15.0, "pen": 24, "bekle": 5, "gunluk": 5.0, "onayar": "v4.7"})
def kaydet():
    try: json.dump({"A": A, "acik": acik, "gecmis": gecmis[-400:], "cap": lev_cap}, open(DOSYA, "w"))
    except Exception: pass

ex = ccxt.bitget({"apiKey": E("BITGET_API"), "secret": E("BITGET_SEC"), "password": E("BITGET_PASS"),
                  "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000})
bot = telebot.TeleBot(E("TELE_TOKEN", "x"), threaded=False)

def bakiye():
    try: return float(ex.fetch_balance()["USDT"]["total"])
    except Exception: return 0.0

def haber(m):
    print(m, flush=True)
    try: bot.send_message(CHAT, m)
    except Exception: pass

def temiz(s): return s.split("/")[0].lstrip("0123456789")

# ───────────────────────── kayıt / gerçek kâr-zarar ─────────────────────────
def logla(sym, yon, pnl, neden, z=0.0):
    try: mid = ex.market(sym)["id"]
    except Exception: mid = sym.split(":")[0].replace("/", "")
    tt = int(time.time())
    gecmis.append({"t": tt, "s": sym.split(":")[0], "id": mid, "y": yon, "pnl": round(pnl, 3), "n": neden, "z": round(z, 2), "g": 0}); kaydet()
    mk = SON_MK.pop(sym, None) or (acik.get(sym) or {}).get("mk")
    if mk is not None: mikro_yaz({"e": "cikis", "t": tt, "ct": tt, "s": sym.split(":")[0], "pnl": round(pnl, 3), "n": neden, **mk})

MIKRO = DOSYA.replace("ayar.json", "mikro.jsonl")
MK, SON_MK = {}, {}          # giriş özellikleri (sembol -> dict), kapanış anında okunur
def mikro_yaz(d):
    try:
        with open(MIKRO, "a") as f: f.write(json.dumps(d, ensure_ascii=False) + "\n")
    except Exception: pass

GOLGE_DOSYA = DOSYA.replace("ayar.json", "golge.json")
GOLGE = []                      # açık hayali işlemler
GOLGE_KIL = threading.Lock()
try: GOLGE.extend(json.load(open(GOLGE_DOSYA)))
except Exception: pass
GOLGE_MAKS_DK = 300             # hayali işlem en fazla bu kadar dakika izlenir

def golge_kaydet():
    try: json.dump(GOLGE, open(GOLGE_DOSYA, "w"))
    except Exception: pass

def golge_ac(sym, yon, gir, mj, lev, sl, t0):
    """Gerçek işlemin TERSİ yönünde hayali işlem. yon: gerçek işlemin yönü ('buy'/'sell')."""
    try:
        y = -1 if yon == "buy" else 1                                     # ters yön
        kl1 = A["net"] + 0.0012 * mj * lev + 0.03 * mj; e0 = kl1 + 0.05 * mj; lv = A["lv"]
        g = {"s": sym, "y": y, "e": gir, "n": mj * lev / gir, "mj": mj, "lev": lev, "sl": sl, "kl1": kl1, "e0": e0,
             "L": [e0, lv[1] * mj, lv[2] * mj, lv[3] * mj], "asama": 0, "kilit": None, "zirve": 0.0, "t0": t0, "ts": int(time.time() * 1000), "son": int(time.time() * 1000), "gy": yon}
        with GOLGE_KIL: GOLGE.append(g); golge_kaydet()
    except Exception as e: print("golge_ac hata", repr(e)[:150], flush=True)

def golge_bar(g, hi, lo):
    """Tek 1 dk'lık mum (kötü sıra: önce en kötü). Kapanırsa net PnL ($), kapanmazsa None."""
    e, n, y, mj = g["e"], g["n"], g["y"], g["mj"]
    wor = (lo - e) * n if y > 0 else (e - hi) * n; bes = (hi - e) * n if y > 0 else (e - lo) * n
    if g["kilit"] is None and wor <= -g["sl"]: return -g["sl"]
    if g["kilit"] is not None and wor <= g["kilit"]: return g["kilit"]
    g["zirve"] = max(g["zirve"], bes); L = g["L"]
    while g["asama"] < 4 and g["zirve"] >= L[g["asama"]]: g["asama"] += 1
    a = g["asama"]
    if a > 0:
        if a == 1: kk = g["kl1"]
        elif a == 2: kk = g["e0"] * 0.95
        elif a == 3: kk = L[1] * 0.95
        else: kk = max(L[2] * 0.95, g["zirve"] - (L[3] - L[2]))
        if a >= 2: kk = max(kk, 0.65 * g["zirve"])
        g["kilit"] = max(g["kilit"], kk) if g["kilit"] is not None else kk
    return None

def golge_adim():
    """Açık hayali işlemleri yeni 1 dk'lık mumlarla ilerlet."""
    with GOLGE_KIL: liste = list(GOLGE)
    bitenler = []
    for g in liste:
        try:
            bars = ex.fetch_ohlcv(g["s"], "1m", limit=15)
            simdi = time.time() * 1000; son = g["son"]; pnl = None; neden = ""
            for b in bars:
                ts = float(b[0])
                if ts <= son or ts + 60000 > simdi or ts < g["ts"]: continue       # tamamlanmamış mum / girişten önce başlayan mum
                son = ts; r = golge_bar(g, float(b[2]), float(b[3])); g["son"] = son; g["c"] = float(b[4])
                if r is not None: pnl = r; neden = "STOP" if g["kilit"] is None else "KİLİT"; break
            if pnl is None and (simdi - g["ts"]) / 60000 >= GOLGE_MAKS_DK:
                pnl = (g.get("c", g["e"]) - g["e"]) * g["n"] * g["y"]; neden = "SÜRE"
            if pnl is not None:
                net = pnl - 0.0032 * g["mj"] * g["lev"]
                mikro_yaz({"e": "golge", "t": int(time.time()), "s": g["s"].split(":")[0], "t0": g["t0"], "y": "buy" if g["y"] > 0 else "sell", "gercek_y": g["gy"], "pnl": round(net, 3), "n": neden, "dk": round((simdi - g["ts"]) / 60000)})
                bitenler.append(g)
        except Exception as e: print("golge_adim hata", g.get("s"), repr(e)[:150], flush=True)
    if bitenler:
        with GOLGE_KIL:
            for g in bitenler:
                try: GOLGE.remove(g)
                except ValueError: pass
            golge_kaydet()
    else:
        with GOLGE_KIL: golge_kaydet()

def golge_dongu():
    while True:
        try: golge_adim()
        except Exception as e: print("golge hata", repr(e)[:150], flush=True)
        time.sleep(60)

def mfm():
    """Mikro modu: eski ayar True/False ise ATLA/KAPALI sayılır."""
    v = A.get("mf")
    if v is True: return "atla"
    if v in ("atla", "cevir"): return v
    return "kapali"

def akis_ozellik(sm, yon):
    """Son 1/5/15 dk'da gerçekleşen BÜYÜK işlemlerin net yönü (-1..+1, işlem yönünde +). Büyük = max(50$, 4×medyan işlem). Veri yetmezse None."""
    sg = 1 if yon == "buy" else -1; o = {"akis1": None, "akis5": None, "akis15": None, "kap": None}
    try:
        try: tr = ex.fetch_trades(sm, limit=500)
        except Exception: tr = ex.fetch_trades(sm, limit=100)          # bazı borsa uçlarında üst sınır 100
        tr = [t for t in tr if t.get("timestamp") and t.get("side") in ("buy", "sell") and (t.get("cost") or (t.get("price") or 0) * (t.get("amount") or 0)) > 0]
        if len(tr) < 5: return o
        maliyet = [float(t.get("cost") or t["price"] * t["amount"]) for t in tr]
        med = sorted(maliyet)[len(maliyet) // 2]; esik = max(50.0, 4 * med)
        simdi = time.time() * 1000; ilk = min(t["timestamp"] for t in tr); o["kap"] = round((simdi - ilk) / 60000, 1)      # elimizdeki işlem geçmişi kaç dakikalık
        for ad, dk in (("akis1", 1), ("akis5", 5), ("akis15", 15)):
            if (simdi - ilk) / 60000 < dk * 0.8: continue                                  # bu pencereyi kapsamıyor
            al = sum(m for t, m in zip(tr, maliyet) if t["side"] == "buy" and m >= esik and simdi - t["timestamp"] <= dk * 60000)
            sat = sum(m for t, m in zip(tr, maliyet) if t["side"] == "sell" and m >= esik and simdi - t["timestamp"] <= dk * 60000)
            if al + sat > 0: o[ad] = round(sg * (al - sat) / (al + sat), 2)
    except Exception: pass
    return o

def mikro_ozellik(sm, yon, c, oi=True, akis=True):
    """Sinyal anında emir defteri dengesizliği, spread, açık pozisyon (OI). Alınamazsa None (filtre devre dışı kalır)."""
    sg = 1 if yon == "buy" else -1; o = {"imb_y": None, "spread": None, "oi": None}
    try:
        ob = ex.fetch_order_book(sm, 20); b = ob.get("bids") or []; a = ob.get("asks") or []
        if b and a:
            bv = sum(x[0] * x[1] for x in b[:10]); av = sum(x[0] * x[1] for x in a[:10])
            if bv + av > 0: o["imb_y"] = round(sg * (bv - av) / (bv + av), 3)        # + : işlem yönünde baskı (long için alış ağır)
            o["spread"] = round((a[0][0] / b[0][0] - 1) * 100, 4)
    except Exception: pass
    if akis: o.update(akis_ozellik(sm, yon))
    if not oi: return o
    try:
        import requests
        r = requests.get("https://api.bitget.com/api/v2/mix/market/open-interest", params={"symbol": temiz(sm) + "USDT", "productType": "USDT-FUTURES"}, timeout=4).json()
        o["oi"] = float(r["data"]["openInterestList"][0]["size"])
    except Exception: pass
    return o

hata_goster = [True]
def gercek_pnl(mid, t):
    """Borsanın pozisyon geçmişinden NET kâr/zarar (komisyon + fonlama dahil). Bulunamazsa None."""
    try:
        r = ex.private_mix_get_v2_mix_position_history_position({"productType": "USDT-FUTURES", "symbol": mid, "limit": "20"})
        for x in (r.get("data") or {}).get("list", []):
            if abs(int(x.get("utime") or 0) / 1000 - t) < 120:
                return float(x.get("netProfit") if x.get("netProfit") not in (None, "") else x.get("pnl"))
    except Exception as e:
        if hata_goster[0]: hata_goster[0] = False; haber(f"⚠️ Gerçek kâr/zarar borsadan okunamadı (tahmin gösteriliyor): {str(e)[:150]}")
    return None

def duzelt():   # kapanıştan ~20 sn sonra tahmini PnL'yi borsanın gerçek (komisyonlu) rakamıyla değiştir
    for g in gecmis[-40:]:
        if g.get("g", 1) == 0 and time.time() - g["t"] > 20 and time.time() - g.get("d", 0) > 15:
            g["d"] = time.time(); v = gercek_pnl(g.get("id", ""), g["t"])
            if v is not None:
                g["pnl"], g["g"] = round(v, 3), 1
                mikro_yaz({"e": "gercek", "s": g["s"], "ct": g["t"], "pnl": round(v, 3)})          # mikro özeti gerçek net PnL ile hesaplansın
            elif time.time() - g["t"] > 900: g["g"] = 2
    kaydet()

def gun_toplam():
    b = gun()
    return sum(g["pnl"] for g in gecmis if gun(g["t"]) == b)

def limit_doldu():
    """Günlük zarar limiti dolu mu? (kalıcı kilit YOK: limit değişince ya da gün dönünce otomatik düzelir)"""
    return A["gunluk"] > 0 and gun_toplam() <= -A["gunluk"]

def durum():
    if not A["calis"]: return "⏹ DURDU (elle)"
    if limit_doldu(): return "⛔ LİMİT DOLDU (yeni giriş yok)"
    return "▶️ ÇALIŞIYOR"

# ───────────────────────── borsa işlemleri ─────────────────────────
def borsa_stop_iptal(sym, sid):
    if not sid: return
    for prm in ({"trigger": True}, {"stop": True}, {}):
        try: ex.cancel_order(sid, sym, prm); return
        except Exception: pass

def borsa_stop(sym, p, k, kilit):
    """Borsada stop-market (reduce-only). kilit: kâr kilidi (+) ya da zarar stopu (−), $ olarak. Döner: başarılı mı."""
    try:
        qty = float(p["contracts"]); cs = ex.market(sym).get("contractSize") or 1
        gir = float(p.get("entryPrice")); d = kilit / (qty * cs); uz = p["side"] == "long"
        fy = ex.price_to_precision(sym, gir + d if uz else gir - d)
        eski = k.get("sid")
        o = ex.create_order(sym, "market", "sell" if uz else "buy", qty, params={"stopLossPrice": fy, "reduceOnly": True, "marginMode": "isolated"})
        k["sid"] = o.get("id") or (o.get("info") or {}).get("orderId")
        if eski: borsa_stop_iptal(sym, eski)
        return fy
    except Exception as e:
        haber(f"⚠️ {sym.split(':')[0]} borsa stopu konamadı, bot takip ediyor: {str(e)[:110]}")
        return None

def kapat(sym, p, neden):
    yon = "sell" if p["side"] == "long" else "buy"
    ex.create_order(sym, "market", yon, p["contracts"], params={"reduceOnly": True, "marginMode": "isolated"})
    yasak[sym] = time.time() + (A["bekle"] * 60 if p["unrealizedPnl"] > 0 else max(A["bekle"] * 60, 2 * 3600))   # zararla kapanan coine 2 saat yok
    kk = acik.pop(sym, {}); borsa_stop_iptal(sym, kk.get("sid")); z = kk.get("zirve", 0.0)
    if kk.get("mk") is not None: SON_MK[sym] = kk["mk"]
    logla(sym, p["side"], p["unrealizedPnl"], neden, z)
    haber(f"{'✅' if p['unrealizedPnl'] > 0 else '❌'} {sym.split(':')[0]} kapandı: {neden}\nPnL ≈ {p['unrealizedPnl']:+.2f}$ (gördüğü zirve {z:+.2f}$)")

def sl_fiyat(yon, giris, adet, cs, usd):
    d = usd / (adet * cs)
    return giris - d if yon in ("buy", "long") else giris + d

def kaldirac_ayarla(sym, lev, yon):
    """Kaldıracı ayarla, borsadaki GERÇEK değeri oku. Döner: (ayar_basarili, gercek_lev|None, hata)."""
    taraf = "long" if yon == "buy" else "short"; ok, hata = False, ""
    for params in ({"holdSide": taraf}, {}, {"marginMode": "isolated", "holdSide": taraf}):
        try: ex.set_leverage(lev, sym, params); ok = True; break
        except Exception as e: hata = str(e)[:150]
    gercek = None
    if ok:
        try:
            r = ex.fetch_leverage(sym, {"marginMode": "isolated"})
            v = r.get(taraf + "Leverage") or r.get("leverage"); gercek = float(v) if v else None
        except Exception: pass
    return ok, gercek, hata

def ac(sym, yon, son, pct):
    """Pozisyon aç. Döner: True/False."""
    ad = sym.split(":")[0]
    with KIL:
        if sym in acik or len(acik) >= A["max_pos"]: return False
    mj = A["marjin"]; lev, hata = 0, ""
    for l in [l for l in LADDER if l <= min(A["lev"], lev_cap.get(sym, 999)) and 70 * (1 / l - 0.0105) >= MIN_SL_PCT]:
        ok, g, h = kaldirac_ayarla(sym, l, yon); hata = h or hata
        if ok and (g is None or abs(g - l) < 0.5): lev = l; break
        if ok and g is not None and g < l: lev_cap[sym] = int(g)
    if not lev:
        yasak[sym] = time.time() + 6 * 3600
        if hata: haber(f"⚠️ {ad} kaldıraç ayarlanamadı, atlandı: {hata}")
        return False
    m = ex.market(sym); cs = m.get("contractSize") or 1
    adet = ex.amount_to_precision(sym, mj * lev / son / cs)
    if float(adet) * son < 5.2: yasak[sym] = time.time() + 6 * 3600; return False
    try:
        ex.create_order(sym, "market", yon, float(adet), params={"marginMode": "isolated"})
    except Exception as e:
        if "40797" in str(e):      # borsa bu kaldıracı kabul etmiyor: bir basamak düşür, sonraki sinyalde dene
            alt = [l for l in LADDER if l < lev]
            if alt: lev_cap[sym] = alt[0]; yasak[sym] = time.time() + 20; haber(f"ℹ️ {ad} {lev}x kabul edilmedi, sonraki sinyalde {alt[0]}x denenecek"); return False
        yasak[sym] = time.time() + 3600; haber(f"⚠️ {ad} açılamadı: {str(e)[:120]}"); return False
    p = None
    for _ in range(4):                   # pozisyonu borsadan doğrula
        try: p = next(x for x in ex.fetch_positions([sym]) if x.get("contracts")); break
        except Exception: time.sleep(0.7)
    if not p:
        haber(f"🚨 {ad}: emir gitti ama pozisyon görünmedi. Bitget'ten kontrol et!"); yasak[sym] = time.time() + 3600; return False
    gl = float(p.get("leverage") or lev)
    if abs(gl - lev) > 0.5 or float(p.get("initialMargin") or 0) > mj * 1.5:     # kaldıraç uyuşmadı
        kalan = float(ex.amount_to_precision(sym, float(p["contracts"]) * gl / lev)) if 0 < gl < lev else 0.0
        fazla = float(ex.amount_to_precision(sym, float(p["contracts"]) - kalan)) if kalan else 0.0
        try:
            if kalan and fazla > 0 and kalan * son >= 5.2:     # fazlayı küçült: marjin kalsın, işleme devam
                ex.create_order(sym, "market", "sell" if p["side"] == "long" else "buy", fazla, params={"reduceOnly": True, "marginMode": "isolated"})
                lev_cap[sym] = int(gl); lev = int(gl); adet = ex.amount_to_precision(sym, kalan)
                p = next(x for x in ex.fetch_positions([sym]) if x.get("contracts"))
                haber(f"ℹ️ {ad}: {gl:g}x uygulandı, pozisyon küçültüldü, devam")
            else:
                raise RuntimeError("küçültülemedi")
        except Exception:
            try: p = next(x for x in ex.fetch_positions([sym]) if x.get("contracts")); kapat(sym, p, "KALDIRAÇ UYUŞMADI")
            except Exception: pass
            yasak[sym] = time.time() + 6 * 3600; haber(f"🚨 {ad}: kaldıraç uyuşmadı, pozisyon kapatıldı"); return False
    gir = float(p.get("entryPrice") or son); adet_f = float(p["contracts"])
    sl = round(A["sl"] * mj, 2); not_ = ""
    try:   # stop likidasyondan ÖNCE gelsin: likidasyon uzaklığının %70'ine daralt
        liq = float(p.get("liquidationPrice") or 0)
        if liq and sl / (adet_f * cs) > 0.7 * abs(gir - liq):
            sl = round(0.7 * abs(gir - liq) * adet_f * cs, 3); not_ = " (likidasyona yakın, daraltıldı)"
    except Exception: pass
    with KIL:
        acik[sym] = {"zirve": 0.0, "mj": mj, "sl": sl, "son": 0.0, "t": int(time.time()), "y": p["side"], "mk": MK.pop(sym, None)}; kaydet()
        fy = borsa_stop(sym, p, acik[sym], -min(sl * 1.2, 0.85 * mj))     # ZORUNLU yedek stop: bot düşse bile korur
    mk0 = (acik.get(sym) or {}).get("mk")
    if mk0 is not None: mikro_yaz({"e": "giris", "t": int(time.time()), "s": sym.split(":")[0], "fiyat": gir, **mk0})
    if mk0 and mk0.get("mod") == "defter": golge_ac(sym, yon, gir, mj, lev, sl, mk0.get("t0", int(time.time())))        # TERS yönde hayali işlem
    ters = A["mod"] == "ters"
    sebep = f"5 dk mum %{pct:.1f} {'yükseldi' if (yon == 'sell') == ters else 'düştü'} → {'TERSİNE' if ters else 'TAKİP'}"
    if A["mod"] == "aralik": sebep = f"{A['pen']*5//60} saatlik aralık (%{pct:.1f} geniş) {'dibinde' if yon == 'buy' else 'tepesinde'} → ARALIK"
    if mk0 and mk0.get("cevrildi"): sebep = f"Sinyal {'AL' if mk0.get('sinyal_y') == 'buy' else 'SAT'} idi ama emir defteri aleyhine ağırdı → YÖN ÇEVRİLDİ"
    if A["mod"] == "defter": sebep = f"Emir defteri {'alış' if yon == 'buy' else 'satış'} ağırlıklı (%{pct:.0f} denge) → DEFTER" if not (mk0 and mk0.get("ters")) else f"Emir defteri {'satış' if yon == 'buy' else 'alış'} ağırlıklı (%{pct:.0f} denge) → TERSİNE ({'long' if yon == 'buy' else 'short'})"
    haber(f"{'🟢 LONG' if yon == 'buy' else '🔴 SHORT'} {ad} · {lev}x izole · {mj}$\n"
          f"Sebep: {sebep}\n"
          f"Giriş {gir:g} | Bot stopu ≈ {sl_fiyat(yon, gir, adet_f, cs, sl):g} (−{sl}${not_})\n"
          f"{'🛡 Borsa yedek stopu: ' + str(fy) if fy else '⚠️ Borsa stopu YOK, bot takip ediyor'}\n"
          + (f"🔬 Emir defteri {mk0['imb_y']:+.2f} (işlem yönünde +) · spread %{mk0['spread']:.3f}\n" if mk0 and mk0.get("imb_y") is not None and mk0.get("spread") is not None else "")
          + (f"🐋 Büyük işlem akışı 1/5/15dk: {'/'.join(('%+.2f' % mk0[k]) if mk0.get(k) is not None else '–' for k in ('akis1', 'akis5', 'akis15'))}\n" if mk0 and any(mk0.get(k) is not None for k in ('akis1', 'akis5', 'akis15')) else "") +
          f"Kâr: kademeli kilit " + " → ".join(f"+{x*mj:.2f}$" for x in A["lv"]))
    return True

def yonet():
    """Açık pozisyonları yönet: kademeli kilit, stop. 2 sn'de bir çalışır."""
    with KIL:
        pos = [p for p in ex.fetch_positions() if p.get("contracts")]
        var = {p["symbol"] for p in pos}
        for s in [s for s in acik if s not in var]:      # dışarıda (borsa stopu/elle/likidasyon) kapanan
            borsa_stop_iptal(s, acik[s].get("sid")); logla(s, acik[s].get("y", "?"), acik[s].get("son", 0.0), "BORSADA KAPANDI", acik[s].get("zirve", 0.0))
            haber(f"ℹ️ {s.split(':')[0]} borsada kapandı (stop/elle), son görülen PnL ≈ {acik[s].get('son', 0.0):+.2f}$"); acik.pop(s); yasak[s] = time.time() + A["bekle"] * 60
        for p in pos:
            sym = p["symbol"]; pnl = p["unrealizedPnl"] or 0.0
            if sym not in acik:                              # elle açılan: devral
                mj = float(p.get("initialMargin") or A["marjin"])
                acik[sym] = {"zirve": max(pnl, 0.0), "mj": mj, "sl": round(A["sl"] * mj, 2), "son": pnl, "t": int(time.time()), "y": p["side"]}
            k = acik[sym]; k["son"] = pnl; k["zirve"] = max(k["zirve"], pnl)
            lv = k.get("lv") or A["lv"]; k["lv"] = lv; a_ = k.get("asama", 0); mj_ = k["mj"]
            try: lev_ = float(p.get("leverage") or 20)
            except Exception: lev_ = 20.0
            kl1 = A["net"] + 0.0012 * mj_ * lev_ + 0.03 * mj_           # ilk kilit: NET hedef($) + ücret + kayma payı (marjinden bağımsız sabit net)
            e0 = kl1 + 0.05 * mj_                                       # kilit bu kârı görünce devreye girer
            while a_ < len(lv) and pnl >= (e0 if a_ == 0 else lv[a_] * mj_): a_ += 1
            if a_ != k.get("asama", 0):
                k["asama"] = a_; k["kilit"] = kl1 if a_ == 1 else (e0 if a_ == 2 else lv[a_ - 2] * mj_) * 0.95
                haber(f"🔒 {sym.split(':')[0]} kademe {a_}/{len(lv)} → stop yukarı çekildi: +{k['kilit']:.2f}$ (pnl {pnl:+.2f}$)")
            if a_ >= 2 and k.get("kilit") is not None: k["kilit"] = max(k["kilit"], 0.65 * k["zirve"])
            if a_ >= len(lv) and len(lv) > 1: k["kilit"] = max(k.get("kilit") or 0, k["zirve"] - (lv[-1] - lv[-2]) * k["mj"])
            if k.get("kilit") is not None and k["kilit"] >= k.get("bsk", -9) + 0.05 * k["mj"]:
                borsa_stop(sym, p, k, k["kilit"]); k["bsk"] = k["kilit"]     # başarısız olsa da aynı seviyeyi tekrar deneme
            if k.get("kilit") is not None and pnl <= k["kilit"]: kapat(sym, p, "KADEME KİLİDİ")
            elif pnl <= -k["sl"] and k.get("kilit") is None: kapat(sym, p, "STOP")
        kaydet()

# ───────────────────────── strateji: 5 dk mum gövdesi ─────────────────────────
acilis = {}            # mum_no -> {sembol: fiyat, "_dogru": bool}
tarama_bid = [0]
hist = {}              # sembol -> son 5 dk kapanışları (aralık modu)
son_tarama = [0.0]
def fiyatlar():
    """Hantal (en yüksek hacimli) coinleri at, kalanlar arasından 24 saatte en çok oynayanları (yüksek-düşük aralığı geniş) seç."""
    tk = ex.fetch_tickers()
    L = [t for s, t in tk.items() if s.endswith(":USDT") and t.get("last")]
    L.sort(key=lambda t: -(t.get("quoteVolume") or 0))
    L = [t for t in L[A.get("hantal", 40):] if (t.get("quoteVolume") or 0) >= 1_000_000]       # en hacimli N coin = hantal, atla; çok ölü coinleri de atla
    def oynak(t):
        h, l = t.get("high") or 0, t.get("low") or 0
        return (h / l - 1) if h and l else 0
    L.sort(key=lambda t: -oynak(t))
    return {t["symbol"]: float(t["last"]) for t in L[:COIN_SAYI]}

def uygun(s):
    b = temiz(s)
    if b in A["haric"] or (A["hk"] and b in HISSE): return False
    return s not in acik and time.time() >= yasak.get(s, 0)

def gecmis_yukle(px, butce=40):
    """Aralık modu için eksik 5 dk geçmişini borsadan al (bir kerelik; her bar'da en fazla `butce` sn)."""
    if A["mod"] != "aralik": return
    t0 = time.time()
    for sm in px:
        if sm == "_dogru" or len(hist.get(sm, [])) >= max(A["pen"], 49) or time.time() - t0 > butce: continue
        try:
            m = ex.fetch_ohlcv(sm, "5m", limit=max(A["pen"], 49) + 1)[:-1]       # son (açık) mum hariç
            hist[sm] = [float(x[4]) for x in m] + hist.get(sm, [])[-1:]
        except Exception: hist.setdefault(sm, [])

def aralik_girisleri(px):
    aday = []
    for sm, c in px.items():
        h = hist.get(sm, [])
        if sm == "_dogru" or len(h) < A["pen"] * 0.75 or not uygun(sm): continue
        w = h[-A["pen"]:] + [c]; hi, lo = max(w), min(w)
        gen = (hi / lo - 1) * 100
        if gen < 2.0 or gen > A["gen"]: continue                 # çok dar: kâr alanı yok · çok geniş: trend var
        pos = (c - lo) / (hi - lo)
        yon = "buy" if pos <= A["uc"] / 100 else ("sell" if pos >= 1 - A["uc"] / 100 else None)
        if not yon: continue
        sg = 1 if yon == "buy" else -1; hh = h + [c]
        if A.get("yf") == "donus" and (len(hh) < 4 or (c - hh[-4]) * sg <= 0): continue                                  # son 15 dk dönmeye başlamamış
        if A.get("yf") == "trend" and (len(hh) < 49 or (c - hh[-49]) * sg <= 0 or (c - hh[-4]) * sg <= 0): continue          # 4 saatlik trend + 15 dk aynı yönde değil
        aday.append((gen, sm, yon, c, pos))
    for gen, sm, yon, c, pos in sorted(aday, reverse=True):
        with KIL:
            if len(acik) >= A["max_pos"]: break
        mk = mikro_ozellik(sm, yon, c); mk["gen"] = round(gen, 1); mk["pos"] = round(pos, 3); mk["y"] = yon
        mod_mf = mfm()
        if mod_mf == "cevir" and mk["imb_y"] is not None and mk["imb_y"] <= -0.10:     # emir defteri sinyalin aleyhine ağır → yönü çevir
            yon = "sell" if yon == "buy" else "buy"; mk["imb_y"] = round(-mk["imb_y"], 3); mk["cevrildi"] = True; mk["sinyal_y"] = mk["y"]; mk["y"] = yon
        kotu = mod_mf == "atla" and ((mk["spread"] is not None and mk["spread"] > 0.10) or (mk["imb_y"] is not None and mk["imb_y"] < 0))   # geniş spread ya da emir defteri işlem yönünün aleyhine
        if kotu:
            mikro_yaz({"e": "atla", "t": int(time.time()), "s": sm.split(":")[0], **mk}); continue
        MK[sm] = mk
        try: ac(sm, yon, c, gen)
        except Exception as e: haber(f"⚠️ {sm.split(':')[0]} giriş hatası: {str(e)[:120]}")
        MK.pop(sm, None)

def defter_girisleri(px):
    """DEFTER modu: emir defteri belirgin yatıksa ağır tarafta gir (alış ağır → long, satış ağır → short)."""
    t0 = time.time(); aday = []
    for sm, c in list(px.items())[:A.get("dn", 40) + 1]:
        if time.time() - t0 > 40: break
        if sm == "_dogru" or not uygun(sm): continue
        mk = mikro_ozellik(sm, "buy", c, oi=False, akis=False)
        if mk["imb_y"] is None or mk["spread"] is None or mk["spread"] > 0.10 or abs(mk["imb_y"]) < A.get("dt", 0.5): continue
        aday.append((abs(mk["imb_y"]), sm, "buy" if mk["imb_y"] > 0 else "sell", c))
    for im, sm, yon, c in sorted(aday, reverse=True):
        with KIL:
            if len(acik) >= A["max_pos"]: break
        mk = mikro_ozellik(sm, yon, c); mk["y"] = yon; mk["mod"] = "defter"; mk["t0"] = int(time.time())
        if mk["imb_y"] is None or mk["imb_y"] < A.get("dt", 0.5) * 0.6 or (mk["spread"] or 0) > 0.10: continue      # girişte defter hâlâ aynı yönde mi
        if A.get("dy") == "ters":                                                                              # DEFTER YÖNÜ: TERS → tüm işaretli ölçümleri çevir, yönü tersle
            yon = "sell" if yon == "buy" else "buy"; mk["y"] = yon; mk["ters"] = True
            for k_ in ("imb_y", "akis1", "akis5", "akis15"):
                if mk.get(k_) is not None: mk[k_] = round(-mk[k_], 3)
        if A.get("ao") and mk.get("akis5") is not None and mk["akis5"] < 0:                                    # AKIŞ ONAYI: büyük işlemler yönün aleyhine
            mikro_yaz({"e": "atla", "t": int(time.time()), "s": sm.split(":")[0], **mk}); continue
        MK[sm] = mk
        try: ac(sm, yon, c, im * 100)
        except Exception as e: haber(f"⚠️ {sm.split(':')[0]} giriş hatası: {str(e)[:120]}")
        MK.pop(sm, None)

def tarama_adimi():
    """Her 5 dk'lık mum başında BİR kez çalışır: tüm fiyatları oku, biten mumun gövdesine bak, sinyal varsa gir."""
    simdi = time.time(); bid = int(simdi // BAR); gec = simdi - bid * BAR
    if tarama_bid[0] == bid: return
    tarama_bid[0] = bid
    px = fiyatlar(); son_tarama[0] = time.time()
    px["_dogru"] = gec < 20          # bu fiyatlar mumun gerçek açılışına yakın mı (restart ortası değil)
    onceki = acilis.get(bid - 1); acilis[bid] = px
    for b in [b for b in acilis if b < bid - 3]: acilis.pop(b)
    for sm, c in px.items():
        if sm != "_dogru": hist.setdefault(sm, []).append(c); del hist[sm][:-300]
    if A["mod"] == "defter":
        if px["_dogru"] and gec < 45 and A["calis"] and not limit_doldu(): defter_girisleri(px)
        return
    if A["mod"] == "aralik":
        try:
            if px["_dogru"] and gec < 45 and A["calis"] and not limit_doldu(): aralik_girisleri(px)
        finally: gecmis_yukle(px)
        return
    if not onceki or not onceki.get("_dogru") or gec > 45: return       # bir önceki mum güvenilir değilse ya da fiyat bayatsa girme
    if not A["calis"] or limit_doldu(): return
    sinyal = []
    for s, c in px.items():
        o = onceki.get(s)
        if s == "_dogru" or not o or not uygun(s): continue
        mv = (c / o - 1) * 100
        if abs(mv) >= A["esik"]: sinyal.append((abs(mv), s, mv, c))
    for _, s, mv, c in sorted(sinyal, reverse=True):
        with KIL:
            if len(acik) >= A["max_pos"]: break
        yukari = mv > 0
        yon = ("sell" if yukari else "buy") if A["mod"] == "ters" else ("buy" if yukari else "sell")
        try: ac(s, yon, c, abs(mv))
        except Exception as e: haber(f"⚠️ {s.split(':')[0]} giriş hatası: {str(e)[:120]}")

# ───────────────────────── panel ─────────────────────────
B = types.InlineKeyboardButton
POZ = {}
def sec(liste, mevcut, onek, fmt):
    return [B(("✅ " if mevcut == v else "") + fmt(v), callback_data=f"{onek}:{v}") for v in liste]

def pozlar():
    ps = [p for p in ex.fetch_positions() if p.get("contracts")]
    POZ.clear(); POZ.update({n: p["symbol"] for n, p in enumerate(ps)}); return ps

def strateji_yazi():
    if A["mod"] == "defter": return f"DEFTER: emir defteri |denge| ≥ {A.get('dt', 0.5):g} ise " + ("ağır tarafın TERSİNE işlem" if A.get("dy") == "ters" else "ağır tarafta işlem") + f" (en hareketli {A.get('dn', 40)} coin)"
    if A["mod"] == "aralik": return f"ARALIK: son {A['pen']*5//60} saatlik aralığın alt %{A['uc']}'unda AL, üst %{A['uc']}'unda SAT (aralık %2–%{A['gen']:g})"
    return f"{'TERSİNE (yükselene sat, düşene al)' if A['mod'] == 'ters' else 'TAKİP (yükselene al, düşene sat)'} · 5 dk mum ≥ %{A['esik']:g}"

def ekran(e):
    k = types.InlineKeyboardMarkup(); geri = B("⬅️ Menü", callback_data="ana")
    if e == "poz":
        ps = pozlar(); sat = []
        for n, p in enumerate(ps):
            a = acik.get(p["symbol"], {}); g = p.get("entryPrice") or 0; adet = float(p["contracts"]); cs = p.get("contractSize") or 1
            sl = a.get("kilit") if a.get("kilit") is not None else -a.get("sl", 0)
            sat.append(f"{n+1}) {'🟢 LONG' if p['side'] == 'long' else '🔴 SHORT'} {p['symbol'].split(':')[0]} {p['leverage'] or '?'}x\n"
                       f"   PnL {p['unrealizedPnl']:+.2f}$ (zirve {a.get('zirve', 0):+.2f}$)\n"
                       f"   giriş {g:g} | stop {sl_fiyat(p['side'], g, adet, cs, -sl):g} ({'kilit +' if sl > 0 else ''}{sl:.2f}$)")
            k.row(B(f"❌ {n+1}. kapat", callback_data=f"k{n}"))
        k.row(geri, B("🔄 Yenile", callback_data="poz"))
        return "📋 AÇIK POZİSYONLAR\n\n" + ("\n\n".join(sat) or "Açık pozisyon yok."), k
    if e == "gec":
        k.row(geri, B("🔄 Yenile", callback_data="gec")); son = gecmis[-15:][::-1]
        satirlar = [f"{'✅' if g['pnl'] > 0 else '❌'} {saat(g['t'])} {g['s']} {g['y']} {g['pnl']:+.2f}$ {'✓' if g.get('g') == 1 else '≈'} {g['n']}" for g in son]
        return "📜 SON İŞLEMLER (✓ borsadan net, ≈ tahmin)\n\n" + ("\n".join(satirlar) or "Henüz işlem yok."), k
    if e == "ozet":
        k.row(geri); n = len(gecmis); w = [g["pnl"] for g in gecmis if g["pnl"] > 0]; l = [g["pnl"] for g in gecmis if g["pnl"] <= 0]
        top = sum(g["pnl"] for g in gecmis)
        return (f"📊 ÖZET\n\nBakiye: {bakiye():.2f}$\nBugün: {gun_toplam():+.2f}$\nToplam: {top:+.2f}$ ({n} işlem)\n"
                f"Kazanma: %{(len(w)/n*100 if n else 0):.0f} ({len(w)} kazanç / {len(l)} kayıp)\n"
                f"Ort. kazanç: {(sum(w)/len(w) if w else 0):+.2f}$ | Ort. kayıp: {(sum(l)/len(l) if l else 0):+.2f}$"), k
    if e == "ayar":
        def bas(t): k.row(B(f"— {t} —", callback_data="ayar"))
        bas("STRATEJİ")
        k.row(B(("✅ " if A["mod"] == "ters" else "") + "Tersine", callback_data="mod:ters"), B(("✅ " if A["mod"] == "takip" else "") + "Takip", callback_data="mod:takip"))
        k.row(B(("✅ " if A["mod"] == "aralik" else "") + "Aralık (dip/tepe)", callback_data="mod:aralik"), B(("✅ " if A["mod"] == "defter" else "") + "Defter (deneysel)", callback_data="mod:defter"))
        if A["mod"] == "defter":
            bas("DEFTER: EŞİK (|denge|)")
            k.row(*sec((0.3, 0.5, 0.7), A.get("dt", 0.5), "dt", lambda v: f"{v:g}"))
            bas("DEFTER: YÖN (Aynı = defter yönünde, Ters = tersine)")
            k.row(*[B(("✅ " if A.get("dy", "ayni") == v else "") + t, callback_data=f"dy:{v}") for v, t in (("ayni", "Aynı"), ("ters", "Ters"))])
            bas("DEFTER: AKIŞ ONAYI (büyük işlemler aleyhteyse girme)")
            k.row(B("✅ AÇIK (kapat)" if A.get("ao") else "❌ KAPALI (aç)", callback_data="ao"))
        if A["mod"] == "aralik":
            bas("ARALIK: PENCERE")
            k.row(*sec((24, 48, 96), A["pen"], "pn", lambda v: f"{v*5//60} saat"))
            bas("ARALIK: UÇ BÖLGE")
            k.row(*sec((5, 10, 15), A["uc"], "uc", lambda v: f"%{v}"))
        else:
            bas("MUM EŞİĞİ")
            k.row(*sec((3, 4, 5, 8), A["esik"], "es", lambda v: f"%{v}"))
        if A["mod"] == "aralik":
            bas("YÖN FİLTRESİ (test: fayda göstermedi)")
            k.row(*[B(("✅ " if A.get("yf") == v else "") + t, callback_data=f"yf:{v}") for v, t in (("kapali", "Kapalı"), ("donus", "15dk dönüş"), ("trend", "4s trend+dönüş"))])
        bas("MİKRO (emir defteri + spread)")
        k.row(*[B(("✅ " if mfm() == v else "") + t, callback_data=f"mf:{v}") for v, t in (("kapali", "Kapalı"), ("atla", "Atla"), ("cevir", "Yönü çevir"))])
        bas("MARJİN (işlem başı)")
        k.row(*sec((1, 2, 3, 5), A["marjin"], "mj", lambda v: f"{v}$"))
        bas("KALDIRAÇ (en çok)")
        k.row(*sec((10, 20, 50), A["lev"], "lev", lambda v: f"{v}x"))
        bas("AYNI ANDA İŞLEM")
        k.row(*sec((1, 2, 3, 5), A["max_pos"], "lim", lambda v: str(v)))
        bas("GÜNLÜK ZARAR LİMİTİ")
        k.row(*sec((2, 3, 5, 10), A["gunluk"], "gl", lambda v: f"-{v}$") + [B(("✅ " if not A["gunluk"] else "") + "Yok", callback_data="gl:0")])
        bas("İLK KİLİT: NET KÂR ($)")
        k.row(*sec((0.1, 0.2, 0.3, 0.5), A["net"], "nt", lambda v: f"+{v}$"))
        bas("AYNI COİNE TEKRAR (bekleme)")
        k.row(*sec((5, 15, 30), A["bekle"], "bk", lambda v: f"{v} dk"))
        bas("KÂR KİLİDİ")
        k.row(*sec(("42,50,75,100", "35,60,100,150", "50,100,150,250"), ",".join(str(int(x * 100)) for x in A["lv"]), "lvl", lambda v: v.replace(",", "/")[:9]))
        k.row(B("Hisse senetleri " + ("❌ KAPALI (aç)" if A["hk"] else "✅ AÇIK (kapat)"), callback_data="hk"))
        k.row(B(f"🚫 Hariç coinler ({len(A['haric'])}) → /haric", callback_data="ayar"))
        k.row(geri)
        return (f"⚙️ AYARLAR\n\nStrateji: {strateji_yazi()}\nMarjin: {A['marjin']:g}$ · Kaldıraç tavanı {A['lev']}x · Max {A['max_pos']} işlem\n"
                f"Zarar stopu: marjinin %{A['sl']*100:.0f}'i (borsada yedek stop her işlemde)\nGünlük zarar limiti: {('−' + str(A['gunluk']) + '$') if A['gunluk'] else 'yok'} (gün dönünce/değişince kendiliğinden devam)\n"
                f"Kademeli kilit: " + " → ".join("+%" + str(int(x * 100)) for x in A["lv"]) + f"\nKapanan coine tekrar giriş beklemesi: {A['bekle']} dk"), k
    if e == "hep":
        k.row(B("✅ Evet, HEPSİNİ kapat", callback_data="hepE"), B("❌ Vazgeç", callback_data="ana"))
        return "🚨 Tüm pozisyonlar kapatılsın mı? (Otomatik giriş de durur)", k
    n = len(pozlar())
    k.row(B("🛑 DURDUR" if A["calis"] else "▶️ BAŞLAT", callback_data="tog"))
    k.row(B("📋 Pozisyonlar", callback_data="poz"), B("📜 Geçmiş", callback_data="gec"))
    k.row(B("📊 Özet", callback_data="ozet"), B("⚙️ Ayarlar", callback_data="ayar"))
    k.row(B("🚨 Tümünü Kapat", callback_data="hep"), B("🔄 Yenile", callback_data="ana"))
    return (f"🤖 GHOST KISA · {VERSIYON}\n━━━━━━━━━━━━━━━━\n{durum()}\n\n"
            f"💰 Bakiye {bakiye():.2f}$   📅 Bugün {gun_toplam():+.2f}$\n📌 Pozisyon {n}/{A['max_pos']}\n"
            f"🎯 {strateji_yazi()}"), k

@bot.message_handler(commands=["panel", "start", "durum", "gecmis"])
def pn(m):
    if m.chat.id != CHAT: return
    t, k = ekran("gec" if m.text.startswith("/gecmis") else "ana"); bot.send_message(CHAT, t, reply_markup=k)

def kaldirac_toplu(hedef):
    syms = [x for x, mk in ex.markets.items() if mk.get("swap") and mk.get("quote") == "USDT" and mk.get("active", True)]
    tam, dusuk, basarisiz = 0, 0, []
    for n, x in enumerate(syms):
        son = None
        for l in [l for l in LADDER if l <= hedef]:
            ok, g, h = kaldirac_ayarla(x, l, "buy")
            if ok and (g is None or abs(g - l) < 0.5): son = l; kaldirac_ayarla(x, l, "sell"); break
        if son: lev_cap[x] = son; tam += son == hedef; dusuk += son != hedef
        else: basarisiz.append(x.split("/")[0])
        if n and n % 150 == 0: bot.send_message(CHAT, f"… {n}/{len(syms)}")
    kaydet(); bot.send_message(CHAT, f"✅ Kaldıraç ayarı bitti (hedef {hedef}x): {tam} kontratta tuttu, {dusuk} kontrat daha düşük kabul etti, {len(basarisiz)} ayarlanamadı")

def mikro_duzelt(L):
    """cikis kayıtlarının PnL'sini borsanın gerçek net PnL'siyle (varsa) değiştir. Döner: (liste, düzeltilen, düzeltilmemiş)."""
    ger = {(x.get("s"), x.get("ct")): x["pnl"] for x in L if x.get("e") == "gercek" and x.get("ct")}
    out, dz, tahmin = [], 0, 0
    for x in L:
        if x.get("e") == "cikis":
            k = (x.get("s"), x.get("ct"))
            if k in ger: x = {**x, "pnl": ger[k], "gercek": True}; dz += 1
            else: tahmin += 1
        out.append(x)
    return out, dz, tahmin

@bot.message_handler(commands=["mikro"])
def mikro_ozet(m):
    if m.chat.id != CHAT: return
    try: L = [json.loads(x) for x in open(MIKRO) if x.strip()]
    except Exception: bot.send_message(CHAT, "Henüz mikro kayıt yok."); return
    L, dz, tahmin = mikro_duzelt(L)
    c = [x for x in L if x.get("e") == "cikis"]; a = [x for x in L if x.get("e") == "atla"]
    def ort(z): return f"{sum(x['pnl'] for x in z)/len(z):+.3f}$ (n={len(z)}, kaz %{100*sum(x['pnl']>0 for x in z)/len(z):.0f})" if z else "veri yok"
    t = [f"🔬 MİKRO KAYIT: {len(c)} kapanan işlem, {len(a)} atlanan sinyal", f"PnL: {dz} işlemde borsanın GERÇEK net rakamı, {tahmin} işlemde tahmini (gerçeği alınamadı / eski kayıt, olduğundan yüksek olabilir)"]
    t.append(f"Emir defteri işlem yönünde (imb>0): {ort([x for x in c if (x.get('imb_y') or 0) > 0])}")
    t.append(f"Emir defteri aleyhine (imb<0): {ort([x for x in c if (x.get('imb_y') or 0) < 0])}")
    for k_, ad_ in (("akis1", "1dk"), ("akis5", "5dk"), ("akis15", "15dk")):
        t.append(f"Büyük akış {ad_} işlem yönünde (+): {ort([x for x in c if (x.get(k_) or 0) > 0.2])} | aleyhine (−): {ort([x for x in c if (x.get(k_) or 0) < -0.2])}")
    gl = [x for x in L if x.get("e") == "golge"]
    if gl:
        ger = {(x.get("s"), x.get("t0")): x["pnl"] for x in c if x.get("mod") == "defter" and x.get("t0")}
        es = [(ger[(x["s"], x["t0"])], x["pnl"]) for x in gl if (x["s"], x["t0"]) in ger]
        t.append(f"👻 GÖLGE (defterin TERSİ, kâğıt üstü): {len(gl)} kapanan, toplam {sum(x['pnl'] for x in gl):+.2f}$, kazanç %{100*sum(x['pnl']>0 for x in gl)/len(gl):.0f}")
        if es: t.append(f"   Eşleşen {len(es)} işlemde: gerçek {sum(a for a,_ in es):+.2f}$ · gölge {sum(b for _,b in es):+.2f}$")
    t.append(f"Yönü çevrilen işlemler: {ort([x for x in c if x.get('cevrildi')])}")
    t.append(f"Spread ≤%0.05: {ort([x for x in c if x.get('spread') is not None and x['spread'] <= 0.05])}")
    t.append(f"Spread >%0.05: {ort([x for x in c if x.get('spread') is not None and x['spread'] > 0.05])}")
    bot.send_message(CHAT, "\n".join(t))
    try: bot.send_document(CHAT, open(MIKRO, "rb"))
    except Exception: pass

@bot.message_handler(commands=["kaldirac"])
def kaldirac_kmd(m):
    if m.chat.id != CHAT: return
    a = m.text.split(); hedef = int(a[1]) if len(a) > 1 and a[1].isdigit() else 20
    bot.send_message(CHAT, f"⏳ Tüm USDT-M kontratlarda {hedef}x ayarlanıyor…")
    threading.Thread(target=kaldirac_toplu, args=(hedef,), daemon=True).start()

@bot.message_handler(commands=["haric"])
def haric(m):
    if m.chat.id != CHAT: return
    a = m.text.split()[1:]
    if len(a) > 1 and a[0] in ("ekle", "sil"):
        for x in a[1:]:
            x = x.upper().replace("USDT", "").lstrip("0123456789")
            if a[0] == "ekle" and x not in A["haric"]: A["haric"].append(x)
            if a[0] == "sil" and x in A["haric"]: A["haric"].remove(x)
        kaydet()
    bot.send_message(CHAT, "🚫 Hariç tutulan coinler:\n" + " ".join(sorted(A["haric"])) + "\n\nEkle: /haric ekle PEPE FIL\nÇıkar: /haric sil PEPE")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.message.chat.id != CHAT: return
    d, uyari, e = c.data, "", "ana"
    try:
        if d in ("poz", "gec", "ozet", "ayar", "hep"): e = d
        elif d[0] == "k" and d[1:].isdigit():
            e = "poz"; sym = POZ.get(int(d[1:]))
            p = next((x for x in ex.fetch_positions() if x["symbol"] == sym and x.get("contracts")), None) if sym else None
            if not p: uyari = "pozisyon yok, yenile"
            else:
                with KIL: kapat(sym, p, "MANUEL")
        elif d == "tog": A["calis"] = not A["calis"]
        elif d == "hk": A["hk"] = not A["hk"]; e = "ayar"
        elif d.startswith("mod:"): A["mod"] = d[4:]; e = "ayar"
        elif d == "mf": A["mf"] = "kapali" if mfm() != "kapali" else "atla"; e = "ayar"
        elif d.startswith("mf:"): A["mf"] = d[3:]; e = "ayar"
        elif d.startswith("yf:"): A["yf"] = d[3:]; e = "ayar"
        elif d.startswith("nt:"): A["net"] = float(d[3:]); e = "ayar"
        elif d.startswith("pn:"): A["pen"] = int(d[3:]); e = "ayar"
        elif d == "ao": A["ao"] = not A.get("ao"); e = "ayar"
        elif d.startswith("dy:"): A["dy"] = d[3:]; e = "ayar"
        elif d.startswith("dt:"): A["dt"] = float(d[3:]); e = "ayar"
        elif d.startswith("uc:"): A["uc"] = float(d[3:]); e = "ayar"
        elif d.startswith("es:"): A["esik"] = float(d[3:]); e = "ayar"
        elif d.startswith("mj:"): A["marjin"] = float(d[3:]); e = "ayar"
        elif d.startswith("lev:"): A["lev"] = int(d[4:]); e = "ayar"
        elif d.startswith("lim:"): A["max_pos"] = int(d[4:]); e = "ayar"
        elif d.startswith("gl:"): A["gunluk"] = float(d[3:]); e = "ayar"
        elif d.startswith("bk:"): A["bekle"] = int(d[3:]); e = "ayar"
        elif d.startswith("lvl:"): A["lv"] = [int(x) / 100 for x in d[4:].split(",")]; e = "ayar"
        elif d == "hepE":
            A["calis"] = False
            with KIL:
                for p in ex.fetch_positions():
                    if p.get("contracts"): kapat(p["symbol"], p, "MANUEL")
    except Exception as x: uyari = str(x)[:150]
    kaydet()
    try:
        t, k = ekran(e); bot.edit_message_text(t, c.message.chat.id, c.message.message_id, reply_markup=k)
    except Exception: pass
    try: bot.answer_callback_query(c.id, uyari)
    except Exception: pass

# ───────────────────────── ana döngü ─────────────────────────
def izle():          # pozisyon takibi: 2 sn'de bir
    while True:
        try: yonet(); duzelt()
        except Exception as e: print("hata yonet", repr(e)[:200], flush=True)
        time.sleep(2)

def tarama():        # her 5 dk mum başında BİR kez fiyat oku + sinyal
    hata_sayac = 0; son_kalp = 0.0
    while True:
        try:
            tarama_adimi(); hata_sayac = 0
        except Exception as e:
            hata_sayac += 1; print("hata tarama", repr(e)[:200], flush=True)
            if hata_sayac == 5: haber(f"⚠️ Fiyat okuma 5 kez üst üste hata verdi: {str(e)[:100]}")
        if time.time() - son_kalp > 600:
            son_kalp = time.time(); print(f"💓 {VERSIYON} {durum()} açık={len(acik)} bugün={gun_toplam():+.2f}$ son_tarama={int(time.time()-son_tarama[0]) if son_tarama[0] else -1}sn önce", flush=True)
        time.sleep(0.25)

if __name__ == "__main__":
    ex.load_markets()
    try:        # hisse/altın/emtia (isRwa) otomatik tanı → "hisse senetleri kapalı" ayarı hepsini kapsasın
        for m in ex.markets.values():
            if str((m.get("info") or {}).get("isRwa", "")).upper() == "YES": HISSE.add(m.get("base"))
    except Exception as e: print("rwa liste hatası (markets)", repr(e)[:100], flush=True)
    try:
        import requests
        for x in requests.get("https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES", timeout=15).json().get("data") or []:
            if x.get("isRwa") == "YES": HISSE.add(x["baseCoin"])
    except Exception as e: print("rwa liste hatası (api)", repr(e)[:100], flush=True)
    print(f"hisse/emtia listesi: {len(HISSE)} sembol", flush=True)
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    haber(f"🤖 GHOST KISA {VERSIYON} hazır\n{durum()}\n🎯 {strateji_yazi()}\n💰 {A['marjin']:g}$ izole · ≤{A['lev']}x · max {A['max_pos']} işlem · limit {('−' + str(A['gunluk']) + '$') if A['gunluk'] else 'yok'}\n→ /panel")
    threading.Thread(target=izle, daemon=True).start()
    threading.Thread(target=golge_dongu, daemon=True).start()
    tarama()
