# 📡 SİNYAL KAĞIT BOTU — v1.0 (06.11.2026)
# Sadık: Telegram sinyal kanalını kağıtta test et. GERÇEK EMİR YOK: Bitget anahtarları hiç okunmaz, sadece herkese açık fiyat kullanılır.
# Kanal mesajı gelir gelmez o anki gerçek fiyattan (alış/satış fiyatı) sanal işlem açar; sonradan düzenlenen/silinen mesajlar sonucu değiştirmez.
# Kural (v1.3): 100 $ kasa · işlem başı 10 $ marj × 10x · kanaldan SADECE coin + yön · stop / iz süren stopu bot seçer (çıkış yarışı) · 24 sa en uzun.
import os, json, time, re, threading, asyncio, html, math, socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import requests

VERSIYON = "v1.29 (13.11 01:00)"
KLASOR = (os.getenv("DATA_DIR") or ".").rstrip("/") + "/"
DOSYA = KLASOR + "sinyal.json"; OTURUM = KLASOR + "tg_oturum.txt"
API = "https://api.bitget.com/api/v2/mix/market/"
MJ, LEV, KASA, MAXA, UCRET, KAYMA, SURE = 10.0, 10, 100.0, 20, 0.0006, 0.0005, 7 * 86400
KIL = threading.RLock()
S = {"v": 1, "nakit": KASA, "baslangic": KASA, "acik": [], "gecmis": [], "mesaj": [], "egri": [], "kur": int(time.time())}
try:
    _d = json.load(open(DOSYA))
    if _d.get("v") == 1: S.update(_d)
except Exception: pass
if any("iz" not in p for p in S["acik"]) or any("ayar" not in g for g in S["gecmis"]):        # v1.3: eski biçim (kanal TP/DCA) → arşivle, sıfırdan başla
    S.setdefault("arsiv", []).append({"kanal": S.get("kanal", "Signals - Bitcoin and Ethereum"), "gecmis": S["gecmis"], "acik": S["acik"], "nakit": S["nakit"], "bitis": int(time.time())})
    S.update({"nakit": KASA, "acik": [], "gecmis": [], "mesaj": [], "egri": [], "kur": int(time.time()), "islenen": [], "golge": [], "yaris": []})
if not S.get("geri_v18"):                                                          # v1.8: hatayla arşivlenen lider takibi verisini geri yükle (bir kerelik)
    A = [a for a in S.get("arsiv", []) if a.get("kanal") == "" and a.get("gecmis") is not None]
    if A:
        a = A[-1]; S["arsiv"].remove(a)
        eski = a.get("gecmis", []); S["gecmis"] = sorted(eski + S["gecmis"], key=lambda g: g.get("t", 0))[-500:]
        var = {p["sym"] for p in S["acik"]}; S["acik"] = [p for p in a.get("acik", []) if p.get("sym") not in var] + S["acik"]
        S["nakit"] = KASA + sum(g["pnl"] for g in S["gecmis"]) - MJ * len(S["acik"])
        if eski: S["kur"] = min(S["kur"], min(g.get("t0", g.get("t", S["kur"])) for g in eski))
    S["geri_v18"] = 1
D = {"tg": "başlamadı", "kanal": "", "hata": "", "fiyat": {}, "bid": {}, "ask": {}, "semboller": set(), "adim": None, "telefon": "", "hash": "", "oturum_goster": ""}

def kaydet():
    with KIL:
        try: tmp = DOSYA + ".tmp"; json.dump(S, open(tmp, "w")); os.replace(tmp, DOSYA)
        except Exception as e: print("kayıt hatası", e, flush=True)

def log_mesaj(metin, sonuc):
    S["mesaj"].append({"t": int(time.time()), "m": metin[:400], "s": sonuc}); del S["mesaj"][:-40]

# ───────────── fiyat (herkese açık Bitget) ─────────────
def fiyat_dongu():
    while True:
        try:
            d = requests.get(API + "tickers", params={"productType": "USDT-FUTURES"}, timeout=10).json()["data"]
            with KIL:
                for x in d:
                    s = x["symbol"]; D["fiyat"][s] = float(x["lastPr"]); D["bid"][s] = float(x.get("bidPr") or x["lastPr"]); D["ask"][s] = float(x.get("askPr") or x["lastPr"])
                D["semboller"] = set(D["fiyat"])
            yonet()
        except Exception as e: D["hata"] = "fiyat: " + str(e)[:120]
        time.sleep(4)

# ───────────── mesaj çözümleme ─────────────
YASAK = {"TP", "SL", "I", "USDT", "LONG", "SHORT", "ENTRY", "STOP", "TARGET", "TARGETS", "LET", "THE", "AND", "IS", "PRICE", "LOSS", "CROSS", "PERP", "X"}
def sayi(t):
    t = t.strip().replace(" ", "")
    if "," in t and "." not in t: t = t.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", t) else t.replace(",", ".")
    else: t = t.replace(",", "")
    return float(t)

DCA_PAY = 0.015                                                                   # v1.2: kanal stop vermezse stop = son DCA'nın %1,5 ötesi (bizim kuralımız)
def coz_bullets(metin):
    """v1.2: '#OP | Open Short / Current price / TP 1..6 / DCA: 1. x 2. y 3. z' biçimi (Bitcoin Bullets / Predictum)."""
    m = re.search(r"#([A-Z0-9]{2,15})\s*\|\s*Open\s+(Long|Short)", metin, re.I); m_c = re.search(r"Current\s*price\s*:\s*([\d.,]+)", metin, re.I)
    if not (m and m_c): return None
    coin = m.group(1).upper().replace("USDT", ""); yon = m.group(2).lower(); giris = sayi(m_c.group(1))
    hed = [sayi(x) for x in re.findall(r"TP\s*\d+\s*:\s*([\d.,]+)", metin, re.I)]
    m_d = re.search(r"DCA\s*:(.*?)(?:\n\s*\n|ID:|$)", metin, re.I | re.S)
    dca = [sayi(x) for x in re.findall(r"\d\.\s+([\d]+\.[\d]+|[\d]+)", m_d.group(1))] if m_d else []
    if coin + "USDT" not in D["semboller"]: return {"hata": f"{coin} Bitget'te yok"}
    hed = [h for h in hed if (h < giris if yon == "short" else h > giris)]
    dca = [x for x in dca if (x > giris if yon == "short" else x < giris)]
    son = dca[-1] if dca else giris * (1.05 if yon == "short" else 0.95)
    stop = son * (1 + DCA_PAY if yon == "short" else 1 - DCA_PAY)
    return {"coin": coin, "yon": yon, "giris": giris, "hedefler": hed[:6], "stop": stop, "dca": dca[:3]}

def coz(metin):
    """Döner: dict(coin, yon, giris, hedefler, stop) ya da None."""
    if re.search(r"Report\s+on\s+#", metin, re.I): return None
    b = coz_bullets(metin)
    if b: return b
    m_g = re.search(r"(?:entry|enter)(?:\s*price)?\s*[:\-–]?\s*([\d][\d.,]*)", metin, re.I)       # v1.1: "Enter - 225.68" de
    m_s = re.search(r"(?:stop(?:\s*loss)?|\bSL\b)\s*[:\-–]?\s*([\d][\d.,]*)", metin, re.I)
    m_t = re.search(r"(?:targets?|\bTPs?\b)\s*[:\-–]?\s*([\d][\d.,/\s|;-]*)", metin, re.I)
    if not (m_g and m_s and m_t): return None
    try:
        giris = sayi(re.split(r"[\s/]", m_g.group(1).strip())[0]); stop = sayi(m_s.group(1))
        hed = [sayi(x) for x in re.split(r"[/|;\s]+|-(?=\s)", m_t.group(1).strip()) if re.fullmatch(r"[\d][\d.,]*", x.strip() or "x")]
    except Exception: return None
    if not hed or giris <= 0 or stop <= 0: return None
    coin = None
    m_c = re.search(r"\b([A-Z0-9]{2,12})(?:USDT)?\s*(?:[–\-:]|\s)\s*(LONG|SHORT)\b", metin)
    if m_c and m_c.group(1) + "USDT" in D["semboller"]: coin = m_c.group(1)
    if not coin:
        for w in re.findall(r"\b([A-Z0-9]{2,12})(?:USDT)?\b", metin):
            if w not in YASAK and w + "USDT" in D["semboller"]: coin = w; break
    if not coin: return {"hata": "coin bulunamadı / Bitget'te yok"}
    yon = "short" if stop > giris else "long"
    m_y = re.search(r"\b(LONG|SHORT)\b", metin, re.I)
    if m_y and m_y.group(1).lower() != yon: return {"hata": f"yön çelişkili ({m_y.group(1)} ama stop {'üstte' if yon == 'short' else 'altta'})"}
    hed = [h for h in hed if (h < giris if yon == "short" else h > giris)]
    if not hed: return {"hata": "hedefler girişin yanlış tarafında"}
    hed.sort(reverse=(yon == "short"))
    return {"coin": coin, "yon": yon, "giris": giris, "hedefler": hed[:6], "stop": stop}

# ───────────── kağıt işlem (v1.3: kanaldan sadece coin + yön; stop / iz'i bot kendisi seçer) ─────────────
# Çıkış yarışı (Tepe gibi): her sinyal 27 ayarla gölgede takip edilir; en az 10 sinyal bitince son 50 sinyalde toplamı en iyi ayar kullanılır.
AYARLAR = [(sl, akt, iz) for sl in (2.0, 3.0, 5.0) for akt in (1.0, 2.0, 3.0) for iz in (0.5, 1.0, 2.0)]
VARSAYILAN, YARIS_MIN, YARIS_PENCERE, SURE = (3.0, 2.0, 1.0), 10, 50, 24 * 3600

def secili_ayar():
    Y = S.get("yaris", [])[-YARIS_PENCERE:]
    if len(Y) < YARIS_MIN: return VARSAYILAN
    top = [sum(y["r"][i] for y in Y) for i in range(len(AYARLAR))]
    return AYARLAR[max(range(len(AYARLAR)), key=lambda i: top[i])]

def iz_baslat(yon, giris, ayar):
    u = 1 if yon == "long" else -1
    return {"stop": giris * (1 - u * ayar[0] / 100), "en": giris, "aktif": False, "bitti": None}

def iz_adim(st, yon, giris, ayar, yuksek, dusuk):
    """Bir fiyat aralığı: önce stop (temkinli), sonra en iyi fiyat + iz. Döner: çıkış fiyatı ya da None."""
    sl, akt, iz = ayar; uzun = yon == "long"
    if (uzun and dusuk <= st["stop"]) or (not uzun and yuksek >= st["stop"]): return st["stop"] * (1 - KAYMA if uzun else 1 + KAYMA)
    st["en"] = max(st["en"], yuksek) if uzun else min(st["en"], dusuk)
    if not st["aktif"] and ((uzun and st["en"] >= giris * (1 + akt / 100)) or (not uzun and st["en"] <= giris * (1 - akt / 100))): st["aktif"] = True
    if st["aktif"]:
        yeni = max(giris * (1 + 2 * UCRET), st["en"] * (1 - iz / 100)) if uzun else min(giris * (1 - 2 * UCRET), st["en"] * (1 + iz / 100))
        st["stop"] = max(st["stop"], yeni) if uzun else min(st["stop"], yeni)
        son = st.get("tik_stop") or 0                                                       # v1.7: stop her %0,1 lehte ilerleyişte bir tik
        if not son or (uzun and st["stop"] >= son * 1.001) or (not uzun and st["stop"] <= son * 0.999):
            st["tik_stop"] = st["stop"]; st.setdefault("adim", []).append(int(time.time()))
    return None

def yuzde(yon, giris, cikis): return ((cikis / giris - 1) * (1 if yon == "long" else -1) - 2 * UCRET) * 100

def poz_ac(sg, metin, c, t):
    sym = sg["coin"] + "USDT"; yon = sg["yon"]
    if any(p["sym"] == sym for p in S["acik"]): return None, "bu coinde açık işlem var"
    ayar = secili_ayar()
    S.setdefault("golge", []).append({"sym": sym, "coin": sg["coin"], "yon": yon, "giris": c, "t": int(t), "g": [iz_baslat(yon, c, a) for a in AYARLAR]})
    if len(S["acik"]) >= MAXA: return None, f"en çok {MAXA} açık (yarışa yine de eklendi)"
    if S["nakit"] < MJ: return None, "nakit yetmiyor (yarışa yine de eklendi)"
    S["nakit"] -= MJ
    p = {"sym": sym, "coin": sg["coin"], "yon": yon, "giris": c, "sinyal_giris": sg.get("giris", c), "t": int(t), "ayar": list(ayar), "iz": iz_baslat(yon, c, ayar), "metin": metin[:200], "kaynak": sg.get("kaynak", "Telegram")}
    S["acik"].append(p)
    return p, f"✅ AÇILDI {sg['coin']} {yon.upper()} @ {c:g} · bizim ayar: stop %{ayar[0]:g}, %{ayar[1]:g} kârda iz, %{ayar[2]:g} geriden"

def ac(sg, metin):
    with KIL:
        c = D["ask"].get(sg["coin"] + "USDT") if sg["yon"] == "long" else D["bid"].get(sg["coin"] + "USDT")
        if not c: return "fiyat yok"
        return poz_ac(sg, metin, c, time.time())[1]

def kapat(p, f, neden, t=None):
    r = yuzde(p["yon"], p["giris"], f); pnl = MJ * LEV * r / 100
    S["nakit"] += MJ + pnl; S["acik"].remove(p)
    S["gecmis"].append({"coin": p["coin"], "yon": p["yon"], "giris": p["giris"], "sinyal_giris": p["sinyal_giris"], "cikis": f, "t0": p["t"], "t": int(t or time.time()),
                        "pnl": round(pnl, 3), "yuzde": round(r, 2), "neden": neden, "ayar": p["ayar"], "kaynak": p.get("kaynak", "")})
    del S["gecmis"][:-500]; S["egri"].append([int(time.time()), round(ozsermaye(), 2)]); del S["egri"][:-800]

def adim_hepsi(sym, yuksek, dusuk, kapanis, t=None):
    """Gerçek pozisyon + gölgeler için bir fiyat aralığı."""
    simdi = t or time.time()
    for p in [x for x in S["acik"] if x["sym"] == sym]:
        f = iz_adim(p["iz"], p["yon"], p["giris"], p["ayar"], yuksek, dusuk)
        if f: kapat(p, f, ("iz süren stop" if p["iz"]["aktif"] else "stop"), t)
        elif simdi - p["t"] > SURE: kapat(p, kapanis, "süre doldu (24 sa)", t)
    for g in [x for x in S.get("golge", []) if x["sym"] == sym]:
        for i, st in enumerate(g["g"]):
            if st["bitti"] is not None: continue
            f = iz_adim(st, g["yon"], g["giris"], AYARLAR[i], yuksek, dusuk)
            if f is None and simdi - g["t"] > SURE: f = kapanis
            if f is not None: st["bitti"] = round(yuzde(g["yon"], g["giris"], f), 3)
        if all(st["bitti"] is not None for st in g["g"]):
            S["golge"].remove(g); S.setdefault("yaris", []).append({"coin": g["coin"], "t": g["t"], "r": [st["bitti"] for st in g["g"]]}); del S["yaris"][:-200]

def gecmis_oynat(sg, metin, t_msg):
    """Kaçırılan sinyali mesaj saatinden itibaren 1 dk mumlarla oynat (giriş = mesajdan sonraki ilk dakikanın açılışı)."""
    sym = sg["coin"] + "USDT"; mum = []; bas = int(t_msg // 60 * 60 + 60) * 1000
    while bas < time.time() * 1000 - 60000 and len(mum) < 3000:
        d = requests.get(API + "history-candles", params={"symbol": sym, "productType": "USDT-FUTURES", "granularity": "1m", "startTime": str(bas),
                                                          "endTime": str(bas + 200 * 60000), "limit": "200"}, timeout=15).json().get("data") or []
        if not d: break
        d = sorted([[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in d]); mum += [x for x in d if not mum or x[0] > mum[-1][0]]
        bas = d[-1][0] + 60000; time.sleep(0.2)
    if not mum: return "geçmiş mum alınamadı"
    with KIL:
        p, sonuc = poz_ac(sg, metin, mum[0][1], mum[0][0] / 1000)
        for x in mum: adim_hepsi(sym, x[2], x[3], x[4], x[0] / 1000)
    return sonuc + " · geçmişten oynatıldı" + ((" → kapandı" if p not in S["acik"] else " → açık, takipte") if p else "")

def yonet():
    with KIL:
        for sym in set([p["sym"] for p in S["acik"]] + [g["sym"] for g in S.get("golge", [])]):
            c = D["fiyat"].get(sym)
            if c: adim_hepsi(sym, c, c, c)
        if not S["egri"] or time.time() - S["egri"][-1][0] >= 3600: S["egri"].append([int(time.time()), round(ozsermaye(), 2)])

def ozsermaye():
    t = S["nakit"]
    for p in S["acik"]:
        c = D["fiyat"].get(p["sym"]) or p["giris"]; t += MJ + MJ * LEV * yuzde(p["yon"], p["giris"], c) / 100
    return t

def yaris_veri():
    Y = S.get("yaris", [])[-YARIS_PENCERE:]; sec = secili_ayar()
    top = [round(sum(y["r"][i] for y in Y), 2) for i in range(len(AYARLAR))]
    kaz = [sum(1 for y in Y if y["r"][i] > 0) for i in range(len(AYARLAR))]
    L = sorted([{"k": list(AYARLAR[i]), "top": top[i], "kaz": kaz[i], "secili": AYARLAR[i] == sec} for i in range(len(AYARLAR))], key=lambda x: -x["top"])
    return {"n": len(Y), "min": YARIS_MIN, "secili": list(sec), "liste": L[:8], "takipte": len(S.get("golge", []))}

# ───────────── Telegram (Telethon, kullanıcı hesabıyla okur) ─────────────
LOOP = asyncio.new_event_loop(); TG = {"c": None, "adminler": set()}
def tg_calistir(coro, zaman=40): return asyncio.run_coroutine_threadsafe(coro, LOOP).result(zaman)

async def tg_basla():
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    api_id, api_hash = os.getenv("TG_API_ID"), os.getenv("TG_API_HASH")
    if not (api_id and api_hash): D["tg"] = "🔑 TG_API_ID / TG_API_HASH yok (Railway Variables)"; return
    oturum = os.getenv("TG_SESSION") or (open(OTURUM).read().strip() if os.path.exists(OTURUM) else "")
    c = TelegramClient(StringSession(oturum), int(api_id), api_hash); TG["c"] = c
    await c.connect()
    if not await c.is_user_authorized(): D["tg"] = "🔐 Giriş gerekli — aşağıdan telefon numaranla gir"; D["adim"] = "telefon"; return
    await tg_dinle()

async def tg_dinle():
    from telethon import events
    from telethon.tl.types import ChannelParticipantsAdmins
    c = TG["c"]; ara = (os.getenv("TG_KANAL") or "").strip(); hedef = None                       # v1.4: Bitcoin Bullets kapatıldı (sinyalleri ~1 gün geç paylaşıyor); yeni kanal bekleniyor
    if not ara:                                                                        # v1.8: HATA DÜZELTİLDİ — kanal yokken artık hiçbir şey sıfırlanmaz
        D["tg"] = "📭 Telegram bağlı · kanal seçilmedi (lider takibi çalışıyor)"; D["adim"] = None; return
    try:
        if ara.startswith("@") or "t.me/" in ara: hedef = await c.get_entity(ara)
        else:
            async for dl in c.iter_dialogs():
                if ara.lower() in (dl.name or "").lower(): hedef = dl.entity; break
    except Exception as e: D["hata"] = "kanal: " + str(e)[:120]
    if not hedef: D["tg"] = f"❓ Kanal bulunamadı: '{ara}' — gruba/kanala katıl ya da TG_KANAL'ı düzelt"; return
    D["kanal"] = getattr(hedef, "title", ara)
    with KIL:                                                                              # v1.2: kanal değiştiyse eski sonuçları arşivle, sıfırdan başla
        if S.get("kanal", "Signals - Bitcoin and Ethereum") != D["kanal"] and (S["gecmis"] or S["acik"] or S["mesaj"]):
            S.setdefault("arsiv", []).append({"kanal": S.get("kanal", "Signals - Bitcoin and Ethereum"), "oz": round(ozsermaye(), 2), "gecmis": S["gecmis"], "acik": S["acik"], "bitis": int(time.time())})
            S.update({"nakit": KASA, "acik": [], "gecmis": [], "mesaj": [], "egri": [], "kur": int(time.time()), "islenen": []})
        S["kanal"] = D["kanal"]
    try: TG["adminler"] = {u.id async for u in c.iter_participants(hedef, filter=ChannelParticipantsAdmins)}
    except Exception: TG["adminler"] = set()

    def isle(m, gecmis=False):
        metin = m.raw_text or ""
        if m.id in S.setdefault("islenen", []): return
        S["islenen"].append(m.id); del S["islenen"][:-300]
        if TG["adminler"] and m.sender_id not in TG["adminler"] and not m.post: return          # sadece yönetici / kanal mesajı
        if not re.search(r"entry|enter|stop|target|\bTP\b|\bSL\b|open\s+(long|short)", metin, re.I) or re.search(r"Report\s+on\s+#", metin, re.I): return
        sg = coz(metin)
        if not sg: sonuc = "çözülemedi (giriş/hedef/stop eksik)"
        elif "hata" in sg: sonuc = "atlandı: " + sg["hata"]
        elif gecmis: sonuc = gecmis_oynat(sg, metin, m.date.timestamp())
        else: sonuc = ac(sg, metin)
        with KIL: log_mesaj(metin, sonuc)
        if gecmis: S["mesaj"][-1]["t"] = int(m.date.timestamp())
        kaydet()

    try:                                                                                     # v1.1: son 24 sa'te kaçırılan sinyaller
        eski = [m async for m in c.iter_messages(hedef, limit=60) if time.time() - m.date.timestamp() < 86400]
        for m in reversed(eski):
            await asyncio.get_event_loop().run_in_executor(None, isle, m, True)
        with KIL: S["mesaj"].sort(key=lambda x: x["t"])
    except Exception as e: D["hata"] = "geçmiş tarama: " + str(e)[:120]

    @c.on(events.NewMessage(chats=hedef))
    async def yeni(ev):
        try: await asyncio.get_event_loop().run_in_executor(None, isle, ev.message, False)
        except Exception as e: D["hata"] = "mesaj: " + str(e)[:120]
    D["tg"] = f"✅ Bağlı · dinleniyor: {D['kanal']}" + (f" · {len(TG['adminler'])} yönetici" if TG["adminler"] else ""); D["adim"] = None

def tg_dongu():
    asyncio.set_event_loop(LOOP); LOOP.create_task(tg_basla_guvenli()); LOOP.run_forever()

async def tg_basla_guvenli():
    for deneme in range(1000):                                                   # bağlanamazsa 60 sn'de bir tekrar dene
        try:
            await tg_basla()
            if not D["tg"].startswith("⚠️"): return
        except Exception as e: D["tg"] = "⚠️ Telegram hatası (tekrar denenecek): " + str(e)[:150]
        try:
            if TG["c"]: await TG["c"].disconnect()
        except Exception: pass
        await asyncio.sleep(60)

async def giris_telefon(tel):
    r = await TG["c"].send_code_request(tel); D["telefon"], D["hash"], D["adim"] = tel, r.phone_code_hash, "kod"

async def giris_kod(kod, sifre):
    from telethon.errors import SessionPasswordNeededError
    c = TG["c"]
    try: await c.sign_in(D["telefon"], kod, phone_code_hash=D["hash"])
    except SessionPasswordNeededError:
        if not sifre: D["adim"] = "sifre"; return "iki adımlı doğrulama şifresi gerekli"
        await c.sign_in(password=sifre)
    oturum = c.session.save()
    try: open(OTURUM, "w").write(oturum)
    except Exception: pass
    D["oturum_goster"] = oturum; D["adim"] = None
    await tg_dinle(); return "ok"

# ───────────── panel ─────────────
def veri():
    with KIL:
        G = S["gecmis"]; oz = ozsermaye(); acik = []
        for p in S["acik"]:
            c = D["fiyat"].get(p["sym"]) or p["giris"]
            acik.append({"coin": p["coin"], "yon": p["yon"], "giris": p["giris"], "sinyal_giris": p["sinyal_giris"], "t": p["t"], "c": c, "ayar": p["ayar"],
                         "stop": p["iz"]["stop"], "aktif": p["iz"]["aktif"], "kaynak": p.get("kaynak", ""),
                         "adim": len(p["iz"].get("adim", [])), "izb": p["giris"] * (1 + (1 if p["yon"] == "long" else -1) * p["ayar"][1] / 100),
                         "konum": (lambda sl, hb: max(0, min(100, (c - sl) / (hb - sl) * 100 if hb != sl else 0)))(p["iz"]["stop"], p["giris"] * (1 + (1 if p["yon"] == "long" else -1) * p["ayar"][1] / 100)), "adim_t": (p["iz"].get("adim") or [0])[-1], "kilit": round(MJ * LEV * yuzde(p["yon"], p["giris"], p["iz"]["stop"]) / 100, 3), "pnl": round(MJ * LEV * yuzde(p["yon"], p["giris"], c) / 100, 3)})
        return {"v": VERSIYON, "klasor": KLASOR, "tg": D["tg"], "lider": L["durum"], "liderler": L["liste"], "lider_tarama": int(time.time() - L["tarama_t"]) if L["tarama_t"] else -1, "lider_sonuc": lider_sonuc(), "kanal": D["kanal"], "hata": D["hata"], "adim": D["adim"], "oz": round(oz, 2), "baslangic": S["baslangic"],
                "nakit": round(S["nakit"], 2), "acik": acik, "gecmis": G[::-1], "mesaj": S["mesaj"][-25:][::-1], "kur": S["kur"], "yaris": yaris_veri(),
                "ozet": {"n": len(G), "kaz": sum(1 for g in G if g["pnl"] > 0), "toplam": round(sum(g["pnl"] for g in G), 2),
                         "stop": sum(1 for g in G if g["neden"] == "stop"), "iz": sum(1 for g in G if g["neden"] == "iz süren stop")}}

SAYFA = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sinyal Testi</title>
<style>:root{--bg:#0b1020;--kart:#141b31;--cizgi:#26304f;--yazi:#e8ecf8;--soluk:#8b95b5;--yesil:#22d39b;--kirmizi:#ff5c7a;--sari:#ffc857;--mavi:#5b8cff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 500px at 0 -10%,#16304a 0,transparent 60%),var(--bg);color:var(--yazi);font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.sar{max-width:760px;margin:0 auto;padding:16px}.logo{font-weight:800;font-size:22px;background:linear-gradient(90deg,#5b8cff,#22d39b);-webkit-background-clip:text;color:transparent}
.alt{color:var(--soluk);font-size:12px}.pan{background:var(--kart);border:1px solid var(--cizgi);border-radius:16px;padding:14px;margin:12px 0}h2{font-size:15px;margin:0 0 10px}
.kartlar{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.k{background:#121a30;border:1px solid var(--cizgi);border-radius:14px;padding:12px}.e{color:var(--soluk);font-size:11px;text-transform:uppercase;letter-spacing:.5px}.d{font-size:22px;font-weight:800;margin-top:4px}
.art{color:var(--yesil)}.eks{color:var(--kirmizi)}.chip{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700}.c-l{background:rgba(34,211,155,.15);color:var(--yesil)}.c-s{background:rgba(255,92,122,.15);color:var(--kirmizi)}
.pz{border:1px solid var(--cizgi);border-radius:12px;padding:10px;margin-bottom:8px;background:#121a30}.ust{display:flex;justify-content:space-between;gap:8px}
.tp{display:flex;gap:4px;margin-top:6px;flex-wrap:wrap}.tp span{font-size:11px;padding:2px 6px;border-radius:6px;background:#1c2542;color:var(--soluk)}.tp span.v{background:rgba(34,211,155,.2);color:var(--yesil)}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:7px 4px;border-bottom:1px solid var(--cizgi);text-align:right}td:first-child,th:first-child{text-align:left}th{color:var(--soluk);font-size:11px}
.msg{font-size:12px;border-bottom:1px solid var(--cizgi);padding:6px 0;white-space:pre-wrap}.msg b{display:block;margin-top:2px}input,button{font:inherit;padding:10px;border-radius:10px;border:1px solid var(--cizgi);background:#0d1326;color:var(--yazi);width:100%;margin-top:6px}button{background:linear-gradient(135deg,#5b8cff,#22d39b);border:0;font-weight:800;cursor:pointer}
.sek{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.sek a{display:block;text-align:center;padding:10px;border-radius:12px;background:var(--kart);border:1px solid var(--cizgi);color:var(--soluk);text-decoration:none;font-weight:700;font-size:14px}.sek a.on{background:linear-gradient(135deg,#5b8cff,#22d39b);color:#fff;border:0}
.yol{position:relative;height:10px;border-radius:99px;background:linear-gradient(90deg,rgba(255,92,122,.5),rgba(139,149,181,.25) 33%,rgba(34,211,155,.5));margin:14px 0 4px}.yol i{position:absolute;top:-4px;width:4px;height:18px;border-radius:3px;background:#fff;box-shadow:0 0 8px #fff}
.ucl{display:flex;justify-content:space-between;font-size:11px;color:var(--soluk)}.iz{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px;flex-wrap:wrap}.tik{color:var(--yesil);letter-spacing:1px;font-size:12px}
.uy{background:rgba(255,200,87,.1);border:1px solid rgba(255,200,87,.4);border-radius:12px;padding:10px;font-size:13px;word-break:break-all}</style></head><body><div class="sar">
<div class="logo">📡 SİNYAL TESTİ · 👥 LİDER TAKİBİ</div><div class="alt" id="alt">yükleniyor…</div>
<div class="sek" style="grid-template-columns:1fr 1fr 1fr"><a href="https://worker-production-a529.up.railway.app/canli/">🟢 Canlı</a><a class="on" href="./">👥 Lider takibi</a><a href="ayna/">🪞 Ayna</a></div>
<div class="kartlar" id="kart"></div>
<div class="pan"><h2>💼 Açık işlemler</h2><div id="acik"></div></div>
<div class="pan"><h2>📒 Kapanan</h2><div id="gec"></div></div>
<div class="pan"><h2>🏆 Gruplara göre sıralama</h2><style>.gs{table-layout:fixed;width:100%}.gs th,.gs td{white-space:nowrap}.gs td:nth-child(2),.gs th:nth-child(2){text-align:left;white-space:normal;word-break:break-word}.gs th:nth-child(1){width:22px}.gs th:nth-child(3){width:44px}.gs th:nth-child(4){width:46px}.gs th:nth-child(5){width:78px}</style><div id="lsn"></div></div>
<div class="pan"><b id="ld">…</b><div class="alt" id="ldx"></div><div style="margin-top:8px"><span class="alt" id="tg">…</span></div><div class="alt" id="hata"></div><div id="giris"></div></div>
<div class="pan"><div class="alt"><b>Kaynak:</b> Binance Copy Trading lider trader'ları (son 30 gün ROI sırası, ama <b>takipçileri de kâr etmiş</b>, en büyük düşüş &lt;%40, kazanma ≥%55) + <b>OKX</b> lider trader'ları (resmi açık API; en az 30 gün liderlik, kazanma ≥%55, kârda). Bir lider <b>yeni pozisyon açtığı an</b> aynı coin + yönde açılır (liderin kapanışı izlenmez). Telegram kanalı da bağlanırsa aynı kurallar. Kanal mesajı gelir gelmez <b>o anki gerçek fiyattan</b> sanal işlem açar (sonradan düzenlenen/silinen mesajlar sonucu değiştirmez). 100 $ kasa · işlem başı <b>10 $ × 10x</b> · kanaldan <b>sadece coin + yön</b> alınır; kanalın TP/stop/DCA'sı kullanılmaz · <b>stop ve iz süren stopu bot kendisi seçer</b> (çıkış yarışı: her sinyal 27 ayarla gölgede takip edilir, 10 sinyalden sonra en iyisi kullanılır) · stop borsa stopu gibi (+%0,05 kayma) · ücret %0,06 · en çok 24 saat. <b>Gerçek emir yok.</b></div></div>
<div class="pan"><h2>🏁 Çıkış yarışı</h2><div id="yr"></div></div>
<div class="pan"><h2>💬 Son sinyaller (lider + kanal)</h2><div id="msg"></div></div>
</div><script>
const CNU='https://worker-production-a529.up.railway.app/canli/';window.CA=new Set();
async function cac(c){if(!confirm(c+' Canlı\'da GERÇEK parayla şimdiki fiyattan açılsın mı? (stop: bu işlemin kağıttaki stopu)'))return;try{await fetch(CNU+'ac?s='+encodeURIComponent(c),{method:'POST'});alert('Gönderildi — birkaç saniye içinde Canlı\'da açılır (stopa çok yakınsa açılmaz).')}catch(e){alert('Gönderilemedi')}}
const $=i=>document.getElementById(i),f=(x,d=2)=>Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}),sg=(x,d=2)=>(x>0?'+':'')+f(x,d),rk=x=>x>0?'art':x<0?'eks':'';
const fy=x=>x>=100?f(x,2):x>=1?f(x,4):Number(x).toLocaleString('tr-TR',{maximumSignificantDigits:4});
const ts=t=>new Date(t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const es=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function gonder(yol,veri){const r=await fetch(yol,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(veri)});const j=await r.json();if(j.oturum)$('giris').innerHTML=`<div class="uy">✅ Giriş tamam. Railway'de bu projeye <b>TG_SESSION</b> değişkeni olarak ekle (yeniden kurulumda tekrar giriş istemesin). Kimseyle paylaşma:<br><br>${es(j.oturum)}</div>`;else if(j.mesaj)alert(j.mesaj);yenile()}
let girisCizildi='';
function girisCiz(adim){if(adim===girisCizildi)return;girisCizildi=adim;const g=$('giris');
 if(adim==='telefon')g.innerHTML='<input id="tel" placeholder="+46… telefon numaran"><button onclick="gonder(\'giris/telefon\',{tel:$(\'tel\').value})">Kod gönder</button>';
 else if(adim==='kod')g.innerHTML='<input id="kod" placeholder="Telegram\'dan gelen kod"><input id="sif" type="password" placeholder="iki adımlı şifre (varsa)"><button onclick="gonder(\'giris/kod\',{kod:$(\'kod\').value,sifre:$(\'sif\').value})">Giriş</button>';
 else if(adim==='sifre')g.innerHTML='<input id="kod" placeholder="kod (tekrar)"><input id="sif" type="password" placeholder="iki adımlı doğrulama şifren"><button onclick="gonder(\'giris/kod\',{kod:$(\'kod\').value,sifre:$(\'sif\').value})">Giriş</button>';
 else if(!g.querySelector('.uy'))g.innerHTML='';}
let GEC=[],SAY=0;const SB=10;
function gecSayfa(n){SAY=Math.max(0,Math.min(n,Math.ceil(GEC.length/SB)-1));gecCiz()}
function gecCiz(){const t=Math.max(1,Math.ceil(GEC.length/SB));if(SAY>=t)SAY=t-1;const L=GEC.slice(SAY*SB,SAY*SB+SB);
 $('gec').innerHTML=GEC.length?'<table><tr><th>Coin</th><th>Sonuç</th><th>Kâr</th></tr>'+L.map(g=>`<tr><td><b>${g.coin}</b> <span class="chip ${g.yon=='long'?'c-l':'c-s'}">${g.yon.toUpperCase()}</span><div class="alt">${ts(g.t)}${g.kaynak?' · '+es(g.kaynak):''}</div></td><td>${g.neden}<div class="alt">fiyat %${sg(g.yuzde||0)}${g.ayar?' · ayar %'+g.ayar.join('/%'):''}</div></td><td class="${rk(g.pnl)}"><b>${sg(g.pnl,3)} $</b></td></tr>`).join('')+'</table>'+`<div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px"><button style="width:auto;padding:6px 14px" onclick="gecSayfa(SAY-1)" ${SAY==0?'disabled':''}>◀</button><span class="alt">sayfa ${SAY+1} / ${t} · ${GEC.length} işlem</span><button style="width:auto;padding:6px 14px" onclick="gecSayfa(SAY+1)" ${SAY>=t-1?'disabled':''}>▶</button></div>`:'<div class="alt">Henüz yok.</div>'}
async function yenile(){try{const d=await (await fetch('api',{cache:'no-store'})).json(),o=d.ozet;
 $('alt').textContent=`kağıt · ${d.v} · ${ts(d.kur)}'den beri · kayıt: ${d.klasor}`;$('tg').textContent='Telegram: '+d.tg;$('ld').textContent=d.lider+(d.lider_tarama>=0?` · son tarama ${d.lider_tarama} sn önce`:'');$('ldx').innerHTML=(d.liderler||[]).map(x=>`${x.grup||''}<b>${x.borsa}</b> ${es(x.ad)} <span class="art">%${f(x.roi,0)}</span> <span class="alt">(${x.mdd!=null?'düşüş %'+f(x.mdd,0)+', ':''}kaz %${f(x.kaz,0)})</span>`).join(' · ');
 window.AG=window.AG||{};const ls=d.lider_sonuc||[],SN={};ls.forEach(t=>SN[t.kaynak]=t);
 const GR=[['👥','👥 Normal liderler'],['💰','💰 Takipçisine kazandıranlar'],['🚀','🚀 Yüksek ROI']];
 $('lsn').innerHTML=GR.map(([g,bas])=>{const ks=new Set();(d.liderler||[]).filter(x=>(x.grup||'👥')==g).forEach(x=>ks.add(`${g} ${x.borsa} · ${x.ad}`));ls.filter(t=>t.kaynak.startsWith(g)).forEach(t=>ks.add(t.kaynak));
  const R=[...ks].map(k=>SN[k]||{kaynak:k,n:0,kaz:0,top:0}).sort((a,b)=>(b.n>0)-(a.n>0)||b.top-a.top);const T=R.reduce((s,t)=>s+t.top,0),N=R.reduce((s,t)=>s+t.n,0),K=R.reduce((s,t)=>s+t.kaz,0);
  const RI=R.filter(t=>t.n),bek=R.length-RI.length,ac=AG[g]?' open':'';
  return `<details data-g="${g}"${ac} style="border-top:1px solid #ffffff14;padding:10px 0"><summary style="display:flex;justify-content:space-between;align-items:baseline;cursor:pointer;list-style:none"><b>${bas}</b><span><span class="alt">${N} işlem · </span><b class="${rk(T)}">${sg(T,2)} $</b> ▾</span></summary>`+
  (RI.length?'<table class="gs" style="margin-top:6px"><tr><th>#</th><th>Lider</th><th>İşlem</th><th>Kârlı</th><th>Toplam</th></tr>'+RI.map((t,i)=>`<tr><td>${i+1}</td><td>${es(t.kaynak.slice(g.length+1))}</td><td>${t.n}</td><td>%${f(t.kaz/t.n*100,0)}</td><td class="${rk(t.top)}"><b>${sg(t.top,2)} $</b></td></tr>`).join('')+'</table>':'')+
  (bek?`<div class="alt" style="margin-top:6px">⏳ ${bek} lider henüz işlem açmadı</div>`:'')+'</details>'}).join('');
 document.querySelectorAll('#lsn details').forEach(e=>e.addEventListener('toggle',()=>{AG[e.dataset.g]=e.open}));$('hata').textContent=d.hata||'';girisCiz(d.adim||'');
 $('kart').innerHTML=`<div class="k"><div class="e">Bakiye</div><div class="d">${f(d.oz)} $</div><div class="alt">başlangıç ${f(d.baslangic,0)} $ · boşta ${f(d.nakit)} $</div></div>
 <div class="k"><div class="e">Kâr / zarar</div><div class="d ${rk(d.oz-d.baslangic)}">${sg(d.oz-d.baslangic)} $</div><div class="alt">kapanan ${sg(o.toplam)} $</div></div>
 <div class="k"><div class="e">İşlem</div><div class="d">${o.n}</div><div class="alt">kârlı ${o.n?'%'+f(o.kaz/o.n*100,0):'–'} · açık ${d.acik.length}</div></div>
 <div class="k"><div class="e">Bizim ayar</div><div class="d" style="font-size:16px">stop %${f(d.yaris.secili[0],0)} · iz %${f(d.yaris.secili[1],0)}/%${f(d.yaris.secili[2],1)}</div><div class="alt">${d.yaris.n<d.yaris.min?`yarış öğreniyor ${d.yaris.n}/${d.yaris.min}`:'yarışın seçtiği'} · stop ${o.stop} · iz ${o.iz}</div></div>`;
 const y=d.yaris;$('yr').innerHTML=`<div class="alt" style="margin-bottom:6px">${y.n} biten sinyal · ${y.takipte} takipte · birim: fiyat % (ücret dahil)</div><table><tr><th>Stop / iz başlar / geriden</th><th>Kârlı</th><th>Toplam</th></tr>`+y.liste.map(x=>`<tr><td>${x.secili?'👉 ':''}%${x.k[0]} / %${x.k[1]} / %${x.k[2]}</td><td>${x.kaz}/${y.n}</td><td class="${rk(x.top)}"><b>${sg(x.top)}%</b></td></tr>`).join('')+'</table>';
 try{const cj=await (await fetch(CNU+'api',{cache:'no-store'})).json();window.CA=new Set(((cj.botlar||[])[0]||{acik:[]}).acik.map(x=>x.s))}catch(e){window.CA=window.CA||new Set()}
 $('acik').innerHTML=d.acik.map(p=>{const tm=p.adim_t?new Date(p.adim_t*1000).toLocaleTimeString('tr-TR',{timeZone:'Europe/Stockholm',hour:'2-digit',minute:'2-digit'}):'';
  return `<div class="pz"><div class="ust"><div><b>${p.coin}</b> <span class="chip ${p.yon=='long'?'c-l':'c-s'}">${p.yon.toUpperCase()} 10x</span>${p.kaynak?` <span class="alt">${es(p.kaynak)}</span>`:''}<div class="alt">${ts(p.t)} · giriş ${fy(p.giris)} (sinyal ${fy(p.sinyal_giris)}) → şimdi ${fy(p.c)}</div><div class="alt">ayar: stop %${p.ayar[0]} · %${p.ayar[1]} kârda iz · %${p.ayar[2]} geriden</div></div><div style="text-align:right"><b class="${rk(p.pnl)}">${sg(p.pnl,3)} $</b>${CA.has(p.coin)?'<div class="alt" style="margin-top:6px">🟢 Canlı\'da</div>':`<div><button onclick="cac('${p.coin}')" style="margin-top:6px;border:0;border-radius:8px;padding:5px 9px;font-weight:800;font-size:12px;white-space:nowrap;color:#fff;background:#14a57a">🟢 Canlı'da aç</button></div>`}</div></div>
  ${p.aktif?`<div class="iz"><span>🔒</span><span class="tik">${'▲'.repeat(Math.max(0,Math.min(p.adim,12)-1))}${p.adim?'<b>▲</b>':''}${p.adim>12?'…':''}</span><span class="alt">${p.adim?`kilit <b class="art">${p.adim}×</b> ilerledi · son ${tm} → stop <span class="art">${fy(p.stop)}</span>`:'iz başladı'}</span></div><div class="ucl" style="margin-top:4px"><span>giriş ${fy(p.giris)} → ${fy(p.c)}</span><span class="${rk(p.kilit)}">kilitli kâr ${sg(p.kilit,3)} $</span></div>`
  :`<div class="yol"><i style="left:calc(${p.konum}% - 2px)"></i></div><div class="ucl"><span class="eks">⛔ stop ${fy(p.stop)}</span><span>giriş ${fy(p.giris)}</span><span class="art">🔓 iz başlar ${fy(p.izb)}</span></div><div class="alt" style="text-align:center;margin-top:6px">🔓 İz <b class="art">${fy(p.izb)}</b> fiyatında başlayacak · <b>%${f(Math.abs(p.izb/p.c-1)*100,2)}</b> kaldı</div>`}</div>`}).join('')||'<div class="alt">Açık işlem yok. Kanalda yeni sinyal bekleniyor.</div>';
 GEC=d.gecmis;gecCiz();
 $('msg').innerHTML=d.mesaj.map(m=>`<div class="msg"><span class="alt">${ts(m.t)}</span> ${es(m.m.slice(0,160))}<b>${es(m.s)}</b></div>`).join('')||'<div class="alt">Henüz sinyal mesajı gelmedi.</div>';
}catch(e){$('tg').textContent='⚠️ bağlantı yok'}}
yenile();setInterval(yenile,8000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _yaz(self, kod, govde, tip="application/json; charset=utf-8"):
        b = govde.encode() if isinstance(govde, str) else govde
        self.send_response(kod); self.send_header("Content-Type", tip); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        yol = self.path.split("?")[0].rstrip("/")
        if yol in ("", "/"): return self._yaz(200, SAYFA, "text/html; charset=utf-8")
        if yol == "/api": return self._yaz(200, json.dumps(veri(), ensure_ascii=False))
        if yol == "/grid" and not self.path.split("?")[0].endswith("/"):
            self.send_response(301); self.send_header("Location", "/grid/"); self.end_headers(); return
        if yol == "/grid": return self._yaz(200, GRID_SAYFA, "text/html; charset=utf-8")         # v1.14
        if yol == "/grid/api": return self._yaz(200, json.dumps(grid_veri(), ensure_ascii=False))
        if yol == "/akilli" and not self.path.split("?")[0].endswith("/"):
            self.send_response(301); self.send_header("Location", "/akilli/"); self.end_headers(); return
        if yol == "/akilli": return self._yaz(200, AKILLI_SAYFA, "text/html; charset=utf-8")    # v1.16
        if yol == "/akilli/api": return self._yaz(200, json.dumps(akilli_veri(), ensure_ascii=False))
        if yol == "/ayna" and not self.path.split("?")[0].endswith("/"):
            self.send_response(301); self.send_header("Location", "/ayna/"); self.end_headers(); return
        if yol == "/ayna": return self._yaz(200, AYNA_SAYFA, "text/html; charset=utf-8")          # v1.25
        if yol == "/ayna/api": return self._yaz(200, json.dumps(ayna_veri(), ensure_ascii=False))
        if yol == "/deneme_bybit":                                                         # v1.6.3: Bybit kopya trading erişim testi (salt okunur)
            q = "pageNo=1&pageSize=5&dataDuration=DATA_DURATION_THIRTY_DAY&sortField=LEADER_SORT_FIELD_SORT_ROI"; out = {}
            ua = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "Accept": "application/json"}
            for u in ("https://api2.bybit.com/fapi/beehive/public/v1/common/dynamic-leader-list?" + q, "https://www.bybit.com/x-api/fapi/beehive/public/v1/common/dynamic-leader-list?" + q,
                      "https://api2.bybitglobal.com/fapi/beehive/public/v1/common/dynamic-leader-list?" + q, "https://www.bybitglobal.com/x-api/fapi/beehive/public/v1/common/dynamic-leader-list?" + q):
                try: r = requests.get(u, headers=ua, timeout=15); out[u.split("/fapi")[0]] = [r.status_code, r.text[:500]]
                except Exception as e: out[u.split("/fapi")[0]] = ["hata", str(e)[:200]]
            return self._yaz(200, json.dumps(out, ensure_ascii=False))
        self._yaz(404, "{}")
    def do_POST(self):
        yol = self.path.split("?")[0].rstrip("/")
        try:
            n = int(self.headers.get("Content-Length", "0")); d = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            if yol == "/giris/telefon" and D["adim"] == "telefon":
                tg_calistir(giris_telefon(str(d.get("tel", "")).strip())); return self._yaz(200, json.dumps({"ok": True}))
            if yol == "/giris/kod" and D["adim"] in ("kod", "sifre"):
                r = tg_calistir(giris_kod(str(d.get("kod", "")).strip(), str(d.get("sifre", ""))))
                if r == "ok":
                    o = D["oturum_goster"]; D["oturum_goster"] = ""; return self._yaz(200, json.dumps({"ok": True, "oturum": o}))
                return self._yaz(200, json.dumps({"ok": False, "mesaj": r}, ensure_ascii=False))
            self._yaz(403, json.dumps({"ok": False, "mesaj": "şu an izin yok"}, ensure_ascii=False))
        except Exception as e: self._yaz(200, json.dumps({"ok": False, "mesaj": "hata: " + str(e)[:150]}, ensure_ascii=False))

# ───────────── 👥 Binance lider takibi (v1.5) ─────────────
# Binance Copy Trading'in herkese açık lider trader'ları: anlık açık pozisyonlar. Bir lider YENİ pozisyon açınca aynı coin + yönde kağıt işlem açılır;
# çıkışı (stop / iz) bizim çıkış yarışı yönetir. Lider seçimi: son 30 günde ROI'ye göre, ama takipçileri de kâr etmiş (copierPnl > 0),
# en büyük düşüş < %40, kazanma oranı ≥ %55 ve pozisyonlarını gösteren ilk 15 lider. Liste saatte bir yenilenir.
BN = "https://www.binance.com/bapi/futures/v1/friendly/future/copy-trade/"
L = {"liste": [], "onceki": {}, "liste_t": 0, "tarama_t": 0, "durum": "başlamadı"}
OKX = "https://www.okx.com/api/v5/copytrading/"
def lider_liste():
    sec = []
    # Binance: takipçileri de kâr etmiş, düşüş < %40, kazanma ≥ %55, pozisyonlarını gösteren ilk 15
    aday = []
    for sayfa in range(1, 11):
        r = requests.post(BN + "home-page/query-list", json={"pageNumber": sayfa, "pageSize": 20, "timeRange": "30D", "dataType": "ROI", "favoriteOnly": False,
                          "hideFull": False, "nickname": "", "order": "DESC", "userAsset": 0, "portfolioType": "PUBLIC"}, timeout=15).json()
        aday += (r.get("data") or {}).get("list") or []; time.sleep(0.5)
    n = 0
    for x in aday:
        if float(x.get("copierPnl") or 0) < 50 or float(x.get("mdd") or 100) >= 40 or float(x.get("winRate") or 0) < 55: continue
        r = requests.get(BN + "lead-data/positions", params={"portfolioId": x["leadPortfolioId"]}, timeout=15).json(); time.sleep(0.4)
        if not r.get("data"): continue
        sec.append({"borsa": "Binance", "id": x["leadPortfolioId"], "ad": x["nickname"], "roi": round(float(x["roi"]), 0), "mdd": round(float(x["mdd"]), 1),
                    "kaz": round(float(x["winRate"]), 0)}); n += 1
        if n >= 15: break
    # v1.19 (Sadık): 💰 Takipçilerine en çok kazandıran Binance liderleri (90 ve 30 günde takipçi kârda, takipçi getirisi en yüksek,
    # düşüş < %40, en az 90 gün). Pozisyonlarını gizleyenler de dahil: açık işlemleri "pozisyon geçmişi"nden (kapanmamış olanlar) okunur.
    try:
        cp = {}
        for tr in ("90D", "30D"):
            for sayfa in range(1, 6):
                r = requests.post(BN + "home-page/query-list", json={"pageNumber": sayfa, "pageSize": 20, "timeRange": tr, "dataType": "COPIER_PNL", "favoriteOnly": False,
                                  "hideFull": False, "nickname": "", "order": "DESC", "userAsset": 0, "portfolioType": "PUBLIC"}, timeout=15).json()
                for x in (r.get("data") or {}).get("list") or []: cp.setdefault(x["leadPortfolioId"], {})[tr] = x
                time.sleep(0.4)
        ad_l = []
        for pid, v in cp.items():
            a9, a3 = v.get("90D"), v.get("30D")
            if not a9 or not a3 or float(a9.get("copyAum") or 0) < 20000: continue
            if float(a9["copierPnl"]) <= 0 or float(a3["copierPnl"]) <= 0 or float(a9.get("mdd") or 100) >= 40: continue
            if time.time() * 1000 - float(a9.get("startTime") or 0) < 90 * 86400000: continue
            ad_l.append((float(a9["copierPnl"]) / float(a9["copyAum"]), a9))
        secili = {x["id"] for x in sec}; n = 0
        for oran, x in sorted(ad_l, key=lambda t: -t[0]):
            if n >= 8: break
            if x["leadPortfolioId"] in secili: continue
            r = requests.get(BN + "lead-data/positions", params={"portfolioId": x["leadPortfolioId"]}, timeout=15).json(); time.sleep(0.4)
            if r.get("code") != "000000" or not r.get("data"): continue              # v1.22: gizli lider atlanır (geçmişte açık işlem ancak kapanınca görünüyor → takip edilemez)
            sec.append({"borsa": "Binance", "grup": "💰", "id": x["leadPortfolioId"], "ad": x["nickname"], "roi": round(float(x["roi"]), 0),
                        "mdd": round(float(x.get("mdd") or 0), 1), "kaz": round(float(x.get("winRate") or 0), 0), "takipci": round(oran * 100, 0),
                        "gizli": False}); n += 1
    except Exception as e: L["durum"] = "⚠️ 💰 listesi alınamadı: " + str(e)[:80]
    # v1.13 (Sadık): 🚀 Yüksek ROI grubu — filtresiz en yüksek ROI'li 10 lider (pozisyonları görünen); bizim stop/iz korur
    secili = {x["id"] for x in sec}; n = 0
    for x in sorted(aday, key=lambda x: -float(x.get("roi") or 0)):
        if x["leadPortfolioId"] in secili: continue
        r = requests.get(BN + "lead-data/positions", params={"portfolioId": x["leadPortfolioId"]}, timeout=15).json(); time.sleep(0.4)
        if not r.get("data"): continue
        sec.append({"borsa": "Binance", "grup": "🚀", "id": x["leadPortfolioId"], "ad": x["nickname"], "roi": round(float(x["roi"]), 0),
                    "mdd": round(float(x.get("mdd") or 0), 1), "kaz": round(float(x.get("winRate") or 0), 0)}); n += 1
        if n >= 10: break
    # v1.6 OKX: resmi açık API — en az 30 gün liderlik, kazanma ≥ %55, kârda, pozisyonlarını gösteren ilk 10
    try:
        aday = []
        for sayfa in (1, 2, 3):
            r = requests.get(OKX + "public-lead-traders", params={"instType": "SWAP", "sortType": "pnl_ratio", "limit": "20", "page": str(sayfa)}, timeout=15).json()
            aday += (r.get("data") or [{}])[0].get("ranks") or []; time.sleep(0.5)
        n = 0
        for x in aday:
            if int(x.get("leadDays") or 0) < 30 or float(x.get("winRatio") or 0) < 0.55 or float(x.get("pnlRatio") or 0) <= 0: continue
            r = requests.get(OKX + "public-current-subpositions", params={"instType": "SWAP", "uniqueCode": x["uniqueCode"], "limit": "50"}, timeout=15).json(); time.sleep(0.4)
            if r.get("code") != "0" or any(not q.get("instId") for q in r.get("data") or []): continue       # gizli
            sec.append({"borsa": "OKX", "id": x["uniqueCode"], "ad": x["nickName"], "roi": round(float(x["pnlRatio"]) * 100, 0), "mdd": None,
                        "kaz": round(float(x["winRatio"]) * 100, 0)}); n += 1
            if n >= 10: break
        for uid, ad_ in (("b0b246728fb43a53a396", "Armandino"), ("bcbd487f89b53b55ad93", "Hedge-Trader"), ("b1b648748fb23d57a292", "woshiguaizi"),
                         ("bfb44a7788b73d57a793", "盗野"), ("bbb34f7f89b73d50ac91", "狙盘手安迪"), ("b0bd497f8eb3395ead90", "小z必定暴富")):   # v1.20 💰 Bitget
            if not any(x["id"] == uid for x in sec): sec.append({"borsa": "Bitget", "grup": "💰", "id": uid, "ad": ad_, "roi": 0, "mdd": None, "kaz": None})
        for uc, ad_ in (("F2BCA22ABBB69F57", "Mine13"), ("35F888C7BB441B2B", "Shallow-Pair-Frog"), ("94FC2CF4A047C10E", "Xiaoyao Lee")):   # v1.19 💰 OKX
            if not any(x["id"] == uc for x in sec):
                y = next((x for x in aday if x["uniqueCode"] == uc), {})
                sec.append({"borsa": "OKX", "grup": "💰", "id": uc, "ad": ad_, "roi": round(float(y.get("pnlRatio") or 0) * 100, 0), "mdd": None,
                            "kaz": round(float(y.get("winRatio") or 0) * 100, 0)})
        secili = {x["id"] for x in sec}; n = 0                                                  # v1.13: 🚀 OKX en yüksek 5 (filtresiz)
        for x in sorted(aday, key=lambda x: -float(x.get("pnlRatio") or 0)):
            if x["uniqueCode"] in secili: continue
            r = requests.get(OKX + "public-current-subpositions", params={"instType": "SWAP", "uniqueCode": x["uniqueCode"], "limit": "50"}, timeout=15).json(); time.sleep(0.4)
            if r.get("code") != "0" or any(not q.get("instId") for q in r.get("data") or []): continue
            sec.append({"borsa": "OKX", "grup": "🚀", "id": x["uniqueCode"], "ad": x["nickName"], "roi": round(float(x["pnlRatio"]) * 100, 0), "mdd": None,
                        "kaz": round(float(x.get("winRatio") or 0) * 100, 0)}); n += 1
            if n >= 5: break
    except Exception as e: L["durum"] = "⚠️ OKX listesi alınamadı: " + str(e)[:80]
    # v1.28: kağıtta kendini kanıtlamış lider (≥10 işlem, toplam artı) ROI listesinden düşse de takipte kalır (Canlı onları kopyalıyor)
    with KIL:
        K = S.setdefault("lider_kayit", {})
        K.setdefault("👥 Binance · 天辰资本", {"borsa": "Binance", "id": "5263968339740503553", "ad": "天辰资本", "roi": 176, "mdd": 9.6, "kaz": 93})   # listeden düşmüştü
        for x in sec: K[f"{x.get('grup', '👥')} {x['borsa']} · {x['ad']}"] = x
        for x in ({"borsa": "Binance", "id": "5263968339740503553", "ad": "天辰资本"}, {"borsa": "Binance", "id": "4882735096799123968", "ad": "京吉"},   # v1.29 ⭐ seçkin (Canlı bunları kopyalar)
                  {"borsa": "Binance", "id": "4751341070898456065", "ad": "SatoshiW"}, {"borsa": "Binance", "grup": "💰", "id": "5076854789130646529", "ad": "Leo-Hamsters"},
                  {"borsa": "OKX", "id": "460047947CE774E1", "ad": "leaf-ye"}):
            if not any(y["id"] == x["id"] for y in sec): sec.append(dict(x, roi=0, mdd=None, kaz=None, seckin=True))
        for t in lider_sonuc():
            x = K.get(t["kaynak"])
            if x and t["n"] >= 10 and t["top"] > 0 and not any(y["id"] == x["id"] for y in sec): sec.append(dict(x, kanit=True))
    return sec

def lider_pozlar(x):
    """Döner: {(BTCUSDT, long/short): giriş} ya da None (hata)."""
    simdi = {}
    if x.get("borsa") == "Bitget":                                                          # v1.20: Bitget lider (herkese açık pozisyonlar)
        r = requests.post("https://www.bitget.com/v1/trigger/trace/public/currentPositionList", json={"traderId": x["id"], "pageNo": 1, "pageSize": 50},
                          headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Origin": "https://www.bitget.com", "Referer": "https://www.bitget.com/",
                                   "language": "en_US", "locale": "en_US"}, timeout=15).json()
        if r.get("code") != "00000": return None
        for p in r.get("data") or []:
            sid = p.get("symbolId", "")
            if sid.endswith("USDT_UMCBL") and p.get("holdSide") in (1, 2):
                ky = (sid.replace("_UMCBL", ""), "long" if p["holdSide"] == 1 else "short"); simdi[ky] = float(p.get("averageOpenPrice") or 0)
                LDET[(x["id"],) + ky] = (int(p.get("leverage") or 0), float(p.get("margin") or 0), float(p.get("positionSize") or 0) * simdi[ky])
        return simdi
    if x.get("borsa", "Binance") == "Binance":
        r = requests.get(BN + "lead-data/positions", params={"portfolioId": x["id"]}, timeout=15).json()
        if r.get("code") != "000000": return None
        for p in r.get("data") or []:
            a = float(p.get("positionAmount") or 0)
            if a:
                ky = (p["symbol"], "long" if a > 0 else "short"); simdi[ky] = float(p.get("entryPrice") or 0); lv = int(p.get("leverage") or 0)
                nv = abs(float(p.get("notionalValue") or 0)) or abs(a) * simdi[ky]; LDET[(x["id"],) + ky] = (lv, nv / lv if lv else 0, nv)
        if x.get("gizli") and not simdi:                                                    # v1.19: gizli lider → geçmişte kapanmamış pozisyonlar
            h = requests.post(BN + "lead-portfolio/position-history", json={"pageNumber": 1, "pageSize": 30, "portfolioId": x["id"]}, timeout=15).json()
            if h.get("code") != "000000": return None
            for p in (h.get("data") or {}).get("list") or []:
                if p.get("closed") is None and p.get("status") != "All Closed" and p.get("side") in ("Long", "Short") \
                        and time.time() * 1000 - float(p.get("opened") or 0) < 15 * 60000:          # sadece son 15 dk'da açılanlar (eski/kayan kayıtlar yeni sanılmasın)
                    simdi[(p["symbol"], p["side"].lower())] = float(p.get("avgCost") or 0)
    else:
        r = requests.get(OKX + "public-current-subpositions", params={"instType": "SWAP", "uniqueCode": x["id"], "limit": "50"}, timeout=15).json()
        if r.get("code") != "0": return None
        for p in r.get("data") or []:
            if not p.get("instId", "").endswith("-USDT-SWAP"): continue
            ps = p.get("posSide"); a = float(p.get("subPos") or 0)
            yon = ps if ps in ("long", "short") else ("long" if a > 0 else "short")
            ky = (p["instId"].replace("-USDT-SWAP", "") + "USDT", yon); simdi[ky] = float(p.get("openAvgPx") or 0)
            lv = int(float(p.get("lever") or 0)); mg = float(p.get("margin") or 0); LDET[(x["id"],) + ky] = (lv, mg, mg * lv)
    return simdi

def lider_dongu():
    time.sleep(20)
    while True:
        try:
            if time.time() - L["liste_t"] > 3600 or not L["liste"]:
                L["liste"] = lider_liste(); L["liste_t"] = time.time()
                L["onceki"] = {k: v for k, v in L["onceki"].items() if k in {x["id"] for x in L["liste"]}}
            for x in L["liste"]:
                simdi = lider_pozlar(x); time.sleep(0.8)
                if simdi is None: continue
                with KIL: ay_lider(x, simdi, x["id"] not in L["onceki"])                      # v1.25: 🪞 Ayna
                if x["id"] not in L["onceki"]: L["onceki"][x["id"]] = simdi; continue          # ilk görüş: eski pozisyonlara girilmez
                for (sym, yon), gir in simdi.items():
                    if (sym, yon) in L["onceki"][x["id"]] or not sym.endswith("USDT"): continue
                    coin = sym[:-4]; gr = x.get("grup", "👥"); metin = f"{gr} {x['borsa']} · {x['ad']} (30g ROI %{x['roi']:g}) yeni {yon.upper()} açtı: {coin} @ {gir:g}"
                    if sym not in D["semboller"]: sonuc = "atlandı: Bitget'te yok"
                    else: sonuc = ac({"coin": coin, "yon": yon, "giris": gir, "kaynak": f"{gr} {x['borsa']} · {x['ad']}"}, metin)
                    with KIL: log_mesaj(metin, sonuc)
                    kaydet()
                L["onceki"][x["id"]] = simdi
            L["tarama_t"] = time.time()
            nr = sum(1 for x in L["liste"] if x.get("grup") == "🚀"); nm = sum(1 for x in L["liste"] if x.get("grup") == "💰")
            nb = sum(1 for x in L["liste"] if x["borsa"] == "Binance" and not x.get("grup")) + sum(1 for x in L["liste"] if x["borsa"] == "Bitget" and not x.get("grup"))
            L["durum"] = f"✅ Lider takibi · 👥 Binance {nb} + OKX {len(L['liste']) - nb - nr - nm} · 💰 takipçisine kazandıran {nm} · 🚀 yüksek ROI {nr} lider izleniyor"
        except Exception as e: L["durum"] = "⚠️ Lider takibi hatası (tekrar denenecek): " + str(e)[:120]
        time.sleep(10)

# ───────────── 🪞 AYNA (v1.25, kağıt) — liderlerin işlemlerinin BİREBİR aynısı ─────────────
# Sadık: "onların kaldıracıyla, marjıyla, tamamen aynısı; açtı mı açar, kapattı mı kapatır". Bizim stop / iz / filtre YOK.
# Giriş = liderin giriş fiyatı, marj ve kaldıraç = liderinki (açıldığı andaki). Lider pozisyonu listeden kalkınca o anki fiyattan kapanır.
# Ücret: giriş + çıkış %0,05 (taker). Sonradan ekleme / kısmi kapatma izlenmez (ilk boyut kalır).
LDET = {}
AY_UCRET = 0.0005

def ay_pnl(q, c): return ((c / q["giris"] - 1) if q["yon"] == "long" else (1 - c / q["giris"])) * q["not"]

def ay_ac(x, sym, yon, gir):
    A = S.setdefault("ayna", {"acik": {}, "gecmis": [], "t0": int(time.time())}); k = f"{x['id']}|{sym}|{yon}"
    if k in A["acik"] or not gir or sym not in D["semboller"]: return                    # fiyatını bilmediğimiz coin (Bitget'te yok) alınmaz
    lev, marj, not_ = LDET.get((x["id"], sym, yon), (None, None, None))
    if not lev or not marj: return
    A["acik"][k] = {"lider": x["ad"], "borsa": x["borsa"], "grup": x.get("grup", "👥"), "sym": sym, "coin": sym[:-4], "yon": yon, "giris": gir, "lev": lev,
                    "marj": round(marj, 2), "not": round(not_ or marj * lev, 2), "t": int(time.time()), "fiyatli": sym in D["fiyat"]}

def ay_kapat(k, neden="lider kapattı"):
    A = S["ayna"]; q = A["acik"].pop(k, None)
    if not q: return
    c = D["fiyat"].get(q["sym"]) or q.get("son_c") or q["giris"]
    kz = ay_pnl(q, c) - q["not"] * AY_UCRET * 2
    A["gecmis"].append({**{a: q[a] for a in ("lider", "borsa", "grup", "coin", "yon", "giris", "lev", "marj", "t")}, "cikis": c, "tk": int(time.time()),
                        "pnl": round(kz, 2), "roi": round(kz / q["marj"] * 100, 1) if q["marj"] else 0, "neden": neden})
    del A["gecmis"][:-600]

def ay_lider(x, simdi, ilk):
    """lider_dongu'dan her taramada çağrılır."""
    A = S.setdefault("ayna", {"acik": {}, "gecmis": [], "t0": int(time.time())})
    for k in [k for k, q in A["acik"].items() if k.split("|")[0] == x["id"]]:
        _, sym, yon = k.split("|")
        if (sym, yon) not in simdi: ay_kapat(k)
    if not ilk:
        for (sym, yon), gir in simdi.items():
            if sym.endswith("USDT") and f"{x['id']}|{sym}|{yon}" not in A["acik"] and (sym, yon) not in L["onceki"].get(x["id"], {}): ay_ac(x, sym, yon, gir)

def ayna_veri():
    with KIL:
        A = S.get("ayna") or {"acik": {}, "gecmis": [], "t0": None}
        P = []
        for q in A["acik"].values():
            c = D["fiyat"].get(q["sym"])
            if c: q["son_c"] = c
            c = c or q.get("son_c") or q["giris"]; kz = ay_pnl(q, c) - q["not"] * AY_UCRET
            P.append({**{a: q[a] for a in ("lider", "borsa", "grup", "coin", "yon", "giris", "lev", "marj", "t")}, "c": c, "pnl": round(kz, 2),
                      "roi": round(kz / q["marj"] * 100, 1) if q["marj"] else 0, "fiyat_yok": q["sym"] not in D["fiyat"]})
        G = A["gecmis"]; T = {}
        for g in G:
            t = T.setdefault(g["grup"] + " " + g["borsa"] + " · " + g["lider"], {"k": g["grup"] + " " + g["borsa"] + " · " + g["lider"], "g": g["grup"], "n": 0, "kaz": 0, "top": 0.0, "marj": 0.0})
            t["n"] += 1; t["kaz"] += g["pnl"] > 0; t["top"] = round(t["top"] + g["pnl"], 2); t["marj"] += g["marj"]
        return {"v": VERSIYON, "t0": A.get("t0"), "P": sorted(P, key=lambda p: -p["t"]), "son": G[::-1][:60], "lid": sorted(T.values(), key=lambda t: -t["top"]),
                "r": round(sum(g["pnl"] for g in G), 2), "acik": round(sum(p["pnl"] for p in P), 2), "n": len(G), "kaz": sum(1 for g in G if g["pnl"] > 0),
                "marj_acik": round(sum(p["marj"] for p in P), 0)}

AYNA_SAYFA = SAYFA.split("<body>")[0].replace("<title>Sinyal Testi</title>", "<title>Ayna</title>") + r"""<body><div class="sar">
<div class="logo">🪞 AYNA · liderlerin birebir aynısı (kağıt)</div><div class="alt" id="alt">yükleniyor…</div>
<div class="sek" style="grid-template-columns:1fr 1fr 1fr"><a href="https://worker-production-a529.up.railway.app/canli/">🟢 Canlı</a><a href="../">👥 Lider takibi</a><a class="on" href="./">🪞 Ayna</a></div>
<div class="pan"><div class="alt">Takip edilen <b>tüm liderlerin</b> (👥 · 💰 · 🚀) işlemleri <b>birebir</b>: onların <b>marjı ve kaldıracıyla</b>, onların giriş fiyatından açılır; <b>lider kapatınca kapanır</b>. Bizim stop / iz süren / filtre yok. Ücret giriş+çıkış %0,05. Sonradan ekleme/kısmi kapatma izlenmez. Gerçek emir yok.</div></div>
<div class="kartlar" id="kart"></div>
<div class="pan"><h2>💼 Açık işlemler</h2><div id="acik"></div></div>
<div class="pan"><h2>📒 Kapanan işlemler</h2><div id="son"></div></div>
<div class="pan"><h2>🏆 Liderler (birebir sonuç)</h2><div id="lid"></div></div>
</div><script>
const $=i=>document.getElementById(i),f=(x,d=2)=>Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}),sg=(x,d=2)=>(x>0?'+':'')+f(x,d),rk=x=>x>0?'art':x<0?'eks':'';
const fy=x=>{x=Number(x);return f(x,x>=1000?1:x>=1?3:6)},es=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ts=t=>new Date(t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const sure=s=>{s=Math.max(0,s);const g=Math.floor(s/86400),sa=Math.floor(s%86400/3600),d=Math.floor(s%3600/60);return g?`${g}g ${sa}sa`:sa?`${sa}sa ${d}dk`:`${d}dk`};
const GR=[['👥','👥 Normal'],['💰','💰 Takipçisine kazandıran'],['🚀','🚀 Yüksek ROI']];
async function yenile(){try{const d=await (await fetch('api',{cache:'no-store'})).json();const now=Date.now()/1000;
 $('alt').textContent=`kağıt · ${d.v}${d.t0?' · '+ts(d.t0)+"'den beri":''}`;
 $('kart').innerHTML=`<div class="k"><div class="e">Gerçekleşen</div><div class="d ${rk(d.r)}">${sg(d.r)} $</div><div class="alt">${d.n} işlem · ${d.n?'%'+f(d.kaz/d.n*100,0)+' kârlı':'–'}</div></div>
 <div class="k"><div class="e">Açık işlemler</div><div class="d ${rk(d.acik)}">${sg(d.acik)} $</div><div class="alt">${d.P.length} açık · marj ${f(d.marj_acik,0)} $</div></div>`;
 $('acik').innerHTML=d.P.map(p=>`<div class="pz"><div class="ust"><div><b>${p.coin}</b> <span class="chip ${p.yon=='long'?'c-l':'c-s'}">${p.yon.toUpperCase()} ${p.lev}x</span> <span class="alt">${p.grup} ${p.borsa} · ${es(p.lider)}</span>
  <div class="alt">${ts(p.t)} · ${sure(now-p.t)} · marj <b>${f(p.marj,0)} $</b> · giriş ${fy(p.giris)} → şimdi ${p.fiyat_yok?'<i>fiyat yok</i>':fy(p.c)}</div></div>
  <div style="text-align:right"><b class="${rk(p.pnl)}">${sg(p.pnl)} $</b><div class="alt ${rk(p.roi)}">marja %${sg(p.roi,1)}</div></div></div></div>`).join('')||'<div class="alt">Açık işlem yok — liderler yeni işlem açınca burada görünür.</div>';
 $('son').innerHTML=d.son.length?'<table><tr><th>İşlem</th><th>Süre</th><th>Sonuç</th></tr>'+d.son.slice(0,30).map(g=>`<tr><td><b>${g.coin}</b> <span class="chip ${g.yon=='long'?'c-l':'c-s'}">${g.yon.toUpperCase()} ${g.lev}x</span><div class="alt">${g.grup} ${es(g.lider)} · marj ${f(g.marj,0)} $</div><div class="alt">${fy(g.giris)} → ${fy(g.cikis)} · ${ts(g.tk)}</div></td><td>${sure(g.tk-g.t)}</td><td class="${rk(g.pnl)}"><b>${sg(g.pnl)} $</b><div class="alt">%${sg(g.roi,1)}</div></td></tr>`).join('')+'</table>':'<div class="alt">Henüz kapanan yok.</div>';
 $('lid').innerHTML=GR.map(([g,b])=>{const R=d.lid.filter(t=>t.g==g);if(!R.length)return '';const T=R.reduce((s,t)=>s+t.top,0);
  return `<div style="margin:10px 0 4px;display:flex;justify-content:space-between"><b>${b}</b><b class="${rk(T)}">${sg(T)} $</b></div><table><tr><th>Lider</th><th>İşlem</th><th>Kârlı</th><th>Toplam</th></tr>`+R.map(t=>`<tr><td>${es(t.k.slice(g.length+1))}</td><td>${t.n}</td><td>%${f(t.kaz/t.n*100,0)}</td><td class="${rk(t.top)}"><b>${sg(t.top)} $</b></td></tr>`).join('')+'</table>'}).join('')||'<div class="alt">Henüz kapanan yok.</div>';
}catch(e){$('alt').textContent='⚠️ bağlantı yok'}}
yenile();setInterval(yenile,8000);
</script></body></html>"""

def lider_sonuc():
    T = {}
    for g in S["gecmis"]:
        k = g.get("kaynak") or "Telegram"; t = T.setdefault(k, {"kaynak": k, "n": 0, "kaz": 0, "top": 0.0})
        t["n"] += 1; t["kaz"] += 1 if g["pnl"] > 0 else 0; t["top"] = round(t["top"] + g["pnl"], 3)
    return sorted(T.values(), key=lambda t: -t["top"])

# ───────────── 🔲 GRID (v1.14, kağıt) — Elirox demo'daki gibi BTC nötr grid, Bitget fiyatları ─────────────
# Sadık: "10 USDT marj, kaldıraç en yüksek, aynı Elirox gibi". Aralık: fiyatın %2,99 üstü / %2,47 altı, 40 seviye, nötr (ters çevirme):
# fiyatın altındaki her aralık LONG modda (Li'de al → Li+1'de sat), üstündekiler SHORT modda (Li+1'de sat → Li'de al). Limit emir = maker %0,02.
# Koruma: fiyat aralık dışına çıkarsa ya da tur zararı %30'a ulaşırsa her şey market (%0,06) kapanır, yeni fiyatla yeni tur başlar.
GR_SYM, GR_MJ, GR_LEV, GR_SEV, GR_UST, GR_ALT, GR_MAKER, GR_TAKER, GR_STOP = "BTCUSDT", 10.0, 125, 40, 0.0299, 0.0247, 0.0002, 0.0006, 0.30

def gr_kur(p0):
    hi, lo = p0 * (1 + GR_UST), p0 * (1 - GR_ALT); L = [lo + (hi - lo) * i / GR_SEV for i in range(GR_SEV + 1)]
    q = max(0.0001, math.floor(GR_MJ * GR_LEV / (GR_SEV / 2) / p0 / 0.0001) * 0.0001)
    return {"t0": int(time.time()), "p0": p0, "L": L, "q": round(q, 4), "gerc": 0.0, "n": 0, "ucret": 0.0,
            "g": [{"mod": "long" if L[i + 1] <= p0 else "short", "tut": False} for i in range(GR_SEV)], "son": []}

def gr_acik_kz(T, c):
    t = 0.0
    for i, g in enumerate(T["g"]):
        if g["tut"]: t += ((c - T["L"][i]) if g["mod"] == "long" else (T["L"][i + 1] - c)) * T["q"]
    return t

def gr_bitir(G, T, c, neden):
    kz = gr_acik_kz(T, c); acik_q = sum(1 for g in T["g"] if g["tut"]) * T["q"]; uc = acik_q * c * GR_TAKER
    sonuc = T["gerc"] + kz - uc
    G["turlar"].append({"t0": T["t0"], "t": int(time.time()), "p0": T["p0"], "cikis": c, "n": T["n"], "sonuc": round(sonuc, 3), "neden": neden}); del G["turlar"][:-100]
    G["toplam"] = round(G.get("toplam", 0) + sonuc, 3)

def gr_adim(c):
    G = S.setdefault("grid", {"turlar": [], "toplam": 0.0, "tur": None})
    if not G.get("tur"): G["tur"] = gr_kur(c); return
    T = G["tur"]; L = T["L"]; q = T["q"]
    for i, g in enumerate(T["g"]):
        a, b = L[i], L[i + 1]
        if g["mod"] == "long":
            if not g["tut"] and c <= a: g["tut"] = True; T["ucret"] += q * a * GR_MAKER; T["gerc"] -= q * a * GR_MAKER
            elif g["tut"] and c >= b:
                g["tut"] = False; kz = (b - a) * q - q * b * GR_MAKER; T["gerc"] += kz; T["ucret"] += q * b * GR_MAKER; T["n"] += 1
                T["son"].append([int(time.time()), "long", round(a, 1), round(b, 1), round(kz + q * a * GR_MAKER, 4)]); del T["son"][:-30]
        else:
            if not g["tut"] and c >= b: g["tut"] = True; T["ucret"] += q * b * GR_MAKER; T["gerc"] -= q * b * GR_MAKER
            elif g["tut"] and c <= a:
                g["tut"] = False; kz = (b - a) * q - q * a * GR_MAKER; T["gerc"] += kz; T["ucret"] += q * a * GR_MAKER; T["n"] += 1
                T["son"].append([int(time.time()), "short", round(b, 1), round(a, 1), round(kz + q * b * GR_MAKER, 4)]); del T["son"][:-30]
    oz = GR_MJ + T["gerc"] + gr_acik_kz(T, c)
    neden = "fiyat aralığın üstüne çıktı" if c > L[-1] else "fiyat aralığın altına indi" if c < L[0] else "zarar %30 (koruma)" if oz <= GR_MJ * (1 - GR_STOP) else None
    if neden: gr_bitir(G, T, c, neden); G["tur"] = gr_kur(c)

def grid_dongu():
    time.sleep(15); son = 0
    while True:
        try:
            c = D["fiyat"].get(GR_SYM)
            if c:
                with KIL:
                    G = S.get("grid") or {}
                    if G.get("tur"): gr_bitir(G, G["tur"], c, "Sadık kapattı"); G["tur"] = None     # v1.26: grid kapatıldı (veriler duruyor)
                    G["kapali"] = True
            if time.time() - son > 120: son = time.time(); kaydet()
        except Exception as e: D["hata"] = "grid: " + str(e)[:120]
        time.sleep(2)

def grid_veri():
    with KIL:
        G = S.get("grid") or {"turlar": [], "toplam": 0}; T = G.get("tur"); c = D["fiyat"].get(GR_SYM) or (T or {}).get("p0", 0)
        out = {"v": VERSIYON + " · ⏹ KAPATILDI", "c": c, "toplam": G.get("toplam", 0), "turlar": G["turlar"][::-1], "mj": GR_MJ, "lev": GR_LEV}
        if T:
            ak = gr_acik_kz(T, c); tut = [i for i, g in enumerate(T["g"]) if g["tut"]]
            out["tur"] = {"t0": T["t0"], "p0": T["p0"], "hi": T["L"][-1], "lo": T["L"][0], "adim": T["L"][1] - T["L"][0], "q": T["q"], "n": T["n"], "gerc": round(T["gerc"], 3),
                          "acik": round(ak, 3), "oz": round(GR_MJ + T["gerc"] + ak, 3), "ucret": round(T["ucret"], 3), "tut": len(tut),
                          "net_poz": round(sum(T["q"] * (1 if T["g"][i]["mod"] == "long" else -1) for i in tut), 4), "son": T["son"][::-1],
                          "acik_l": [dict(yon=T["g"][i]["mod"], giris=(T["L"][i] if T["g"][i]["mod"] == "long" else T["L"][i + 1]),          # v1.15: açık grid işlemleri
                                          hedef=(T["L"][i + 1] if T["g"][i]["mod"] == "long" else T["L"][i]), sinir=(T["L"][0] if T["g"][i]["mod"] == "long" else T["L"][-1]),
                                          pnl=round(((c - T["L"][i]) if T["g"][i]["mod"] == "long" else (T["L"][i + 1] - c)) * T["q"], 4)) for i in tut],
                          "adim_kar": round((T["L"][1] - T["L"][0]) * T["q"] - 2 * T["q"] * T["p0"] * GR_MAKER, 4), "konum": max(0, min(100, (c - T["L"][0]) / (T["L"][-1] - T["L"][0]) * 100))}
        return out

GRID_SAYFA = SAYFA.split("<body>")[0].replace("<title>Sinyal Testi</title>", "<title>Grid</title>") + r"""<body><div class="sar">
<div class="logo">🔲 GRID · BTC (kağıt)</div><div class="alt" id="alt">yükleniyor…</div>
<div class="sek" style="grid-template-columns:1fr 1fr 1fr"><a href="https://worker-production-a529.up.railway.app/canli/">🟢 Canlı</a><a href="../">👥 Lider takibi</a><a href="../ayna/">🪞 Ayna</a></div>
<div class="pan"><div class="alt">Elirox demo'daki gibi <b>BTC nötr grid</b>, Bitget fiyatlarıyla: aralık fiyatın <b>%3,0 üstü – %2,5 altı</b>, <b>40 seviye</b>; fiyat düşerken alır (bir üst seviyede satar), yükselirken satar (bir alt seviyede geri alır). Marj <b>10 $ × 125x</b> (Bitget BTC en yüksek), limit emir ücreti %0,02. <b>Koruma:</b> fiyat aralık dışına çıkarsa ya da tur zararı %30'a ulaşırsa hepsi market kapanır ve yeni fiyatla yeni tur başlar. Gerçek emir yok.</div></div>
<div class="kartlar" id="kart"></div>
<div class="pan"><h2>📍 Fiyat aralıkta nerede</h2><div id="yer"></div></div>
<div class="pan"><h2>💼 Açık grid işlemleri</h2><div id="acik"></div></div>
<div class="pan"><h2>📒 Son kapanan grid işlemleri</h2><div id="son"></div></div>
<div class="pan"><h2>🔁 Biten turlar</h2><div id="tur"></div></div>
</div><script>
const $=i=>document.getElementById(i),f=(x,d=2)=>Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}),sg=(x,d=2)=>(x>0?'+':'')+f(x,d),rk=x=>x>0?'art':x<0?'eks':'';
const ts=t=>new Date(t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
async function yenile(){try{const d=await (await fetch('api',{cache:'no-store'})).json(),T=d.tur;
 $('alt').textContent=`kağıt · ${d.v} · BTC ${f(d.c,1)}`;
 if(!T){$('kart').innerHTML='<div class="alt">Grid kuruluyor…</div>';return}
 $('kart').innerHTML=`<div class="k"><div class="e">Bu tur bakiye</div><div class="d ${rk(T.oz-d.mj)}">${f(T.oz)} $</div><div class="alt">marj ${f(d.mj,0)} $ × ${d.lev}x · ${ts(T.t0)}'den beri</div></div>
 <div class="k"><div class="e">Gerçekleşen kâr</div><div class="d ${rk(T.gerc)}">${sg(T.gerc,3)} $</div><div class="alt">${T.n} kapanış · adım başı ~${f(T.adim_kar,3)} $ · ücret ${f(T.ucret,3)} $</div></div>
 <div class="k"><div class="e">Açık pozisyon</div><div class="d ${rk(T.acik)}">${sg(T.acik,3)} $</div><div class="alt">${T.tut} seviye dolu · net ${sg(T.net_poz,4)} BTC</div></div>
 <div class="k"><div class="e">Tüm turlar toplam</div><div class="d ${rk(d.toplam)}">${sg(d.toplam,3)} $</div><div class="alt">${d.turlar.length} tur bitti</div></div>`;
 $('yer').innerHTML=`<div class="yol"><i style="left:calc(${T.konum}% - 2px)"></i></div><div class="ucl"><span class="eks">⬇ ${f(T.lo,0)}</span><span>başlangıç ${f(T.p0,0)} · şimdi ${f(d.c,0)}</span><span class="eks">⬆ ${f(T.hi,0)}</span></div><div class="alt" style="margin-top:6px;text-align:center">40 seviye · adım ${f(T.adim,1)} $ · seviye başı ${T.q} BTC · aralık dışına çıkarsa tur kapanır</div>`;
 $('acik').innerHTML=(T.acik_l||[]).map(p=>{const u=p.yon=='long'?1:-1,k=Math.max(0,Math.min(100,(d.c-p.sinir)/(p.hedef-p.sinir)*100));
  return `<div class="pz"><div class="ust"><div><b>BTC</b> <span class="chip ${p.yon=='long'?'c-l':'c-s'}">${p.yon.toUpperCase()} ${d.lev}x</span><div class="alt">giriş ${f(p.giris,1)} → şimdi ${f(d.c,1)} · ${T.q} BTC</div></div><b class="${rk(p.pnl)}">${sg(p.pnl,3)} $</b></div>
  <div class="yol"><i style="left:calc(${k}% - 2px)"></i></div><div class="ucl"><span class="eks">⛔ aralık ${p.yon=='long'?'altı':'üstü'} ${f(p.sinir,0)}</span><span>giriş ${f(p.giris,1)}</span><span class="art">🎯 hedef ${f(p.hedef,1)}</span></div>
  <div class="alt" style="text-align:center;margin-top:6px">🎯 Hedef <b class="art">${f(p.hedef,1)}</b> · <b>%${f(Math.abs(p.hedef/d.c-1)*100,2)}</b> kaldı · kâr ~${f((Math.abs(p.hedef-p.giris))*T.q,3)} $</div></div>`}).join('')||'<div class="alt">Açık grid işlemi yok.</div>';
 $('son').innerHTML=T.son.length?'<table><tr><th>Zaman</th><th>İşlem</th><th>Kâr (ücret öncesi)</th></tr>'+T.son.slice(0,15).map(x=>`<tr><td>${ts(x[0])}</td><td><span class="chip ${x[1]=='long'?'c-l':'c-s'}">${x[1].toUpperCase()}</span> ${f(x[2],1)} → ${f(x[3],1)}</td><td class="art"><b>${sg(x[4],3)} $</b></td></tr>`).join('')+'</table>':'<div class="alt">Henüz kapanış yok; fiyat bir seviye gidip dönünce ilk kâr gelir.</div>';
 $('tur').innerHTML=d.turlar.length?'<table><tr><th>Tur</th><th>Neden</th><th>Sonuç</th></tr>'+d.turlar.map(x=>`<tr><td>${ts(x.t0)} → ${ts(x.t)}<div class="alt">${x.n} kapanış</div></td><td>${x.neden}</td><td class="${rk(x.sonuc)}"><b>${sg(x.sonuc,3)} $</b></td></tr>`).join('')+'</table>':'<div class="alt">Henüz biten tur yok.</div>';
}catch(e){$('alt').textContent='⚠️ bağlantı yok'}}
yenile();setInterval(yenile,6000);
</script></body></html>"""

# ───────────── 🧠 AKILLI GRID (v1.16, kağıt) ─────────────
# Sadık: "kendini ayarlasın, fiyat dışarı çıkmasın, peşinden gitsin, iz süren SL gibi". Testte (BTC 1dk 14 gün) iki haftada da kârlı olan ayar:
# adım %0,3 (sabit kafes, merkez fiyatı izler: fiyat merkezden %3 uzaklaşınca merkez fiyata kayar) · merkezin altında LONG, üstünde SHORT ·
# her işlem hedefi 1 adım (limit, %0,02), stopu 5 adım (market %0,06 + kayma) · TREND FİLTRESİ: fiyat 12 saatlik EMA'dan %0,3'ten fazla
# uzaksa yeni işlem açılmaz · en çok 20 açık · 20 $ × 50x · bakiye %30 düşerse hepsi kapanır, sıfırdan başlar.
AG_S, AG_K, AG_T, AG_M, AG_MJ, AG_LEV, AG_EMA, AG_ESIK, AG_KAY = 0.003, 5, 0.03, 20, 20.0, 50, 720, 0.003, 0.0003
AGD = {"ema": None, "ema_dk": 0, "hata": ""}

def ag_ema_kur():
    m = []; t = int(time.time() // 60 * 60) * 1000 - 1000 * 60000
    while t < time.time() * 1000 - 60000:
        d = requests.get(API + "history-candles", params={"symbol": "BTCUSDT", "productType": "USDT-FUTURES", "granularity": "1m", "startTime": str(t),
                                                          "endTime": str(t + 200 * 60000), "limit": "200"}, timeout=15).json().get("data") or []
        if not d: t += 200 * 60000; continue
        m += [float(x[4]) for x in sorted(d, key=lambda x: int(x[0]))]; t = int(sorted(d, key=lambda x: int(x[0]))[-1][0]) + 60000; time.sleep(0.2)
    a = 2 / (AG_EMA + 1); e = None
    for c in m: e = c if e is None else e + a * (c - e)
    AGD["ema"] = e; AGD["ema_dk"] = int(time.time() // 60)

def ag_not(): return AG_MJ * AG_LEV / AG_M
def ag_kz(q, p): return ((p / q["g"] - 1) if q["y"] == 1 else (1 - p / q["g"])) * ag_not()

def ag_kapat(A, q, f, neden, ucret):
    A["P"].remove(q); kz = ag_kz(q, f) - ag_not() * (ucret + AG_MAK)
    A["r"] += kz; A["n" if neden == "hedef" else "ns"] += 1
    A["son"].append([int(time.time()), "long" if q["y"] == 1 else "short", round(q["g"], 1), round(f, 1), round(kz, 4), neden]); del A["son"][:-40]

AG_MAK, AG_TAK = 0.0002, 0.0006
def ag_adim(p):
    A = S.setdefault("akilli", None)
    if not A: A = S["akilli"] = {"cen": p, "prev": p, "P": [], "r": 0.0, "n": 0, "ns": 0, "son": [], "t0": int(time.time()), "turlar": []}; return
    s = AG_S; cen = A["cen"]
    for q in A["P"][:]:                                                                     # çıkışlar
        if q["y"] == 1:
            if p <= q["st"]: ag_kapat(A, q, q["st"] * (1 - AG_KAY), "stop", AG_TAK)
            elif p >= q["h"]: ag_kapat(A, q, q["h"], "hedef", AG_MAK)
        else:
            if p >= q["st"]: ag_kapat(A, q, q["st"] * (1 + AG_KAY), "stop", AG_TAK)
            elif p <= q["h"]: ag_kapat(A, q, q["h"], "hedef", AG_MAK)
    e = AGD["ema"]; izin = e is not None and abs(p / e - 1) < AG_ESIK
    ix = lambda v: math.floor((v - cen) / (s * cen)); a, b = ix(A["prev"]), ix(p)
    if izin and b != a:                                                                     # girişler (geçilen seviyeler)
        rng = range(a, b, -1) if b < a else range(a + 1, b + 1)
        for j in rng:
            L = cen + j * s * cen; y = 1 if b < a else -1
            if ((y == 1 and L < cen) or (y == -1 and L > cen)) and len(A["P"]) < AG_M and not any(abs(q["g"] - L) < s * cen * 0.5 for q in A["P"]):
                A["P"].append({"y": y, "g": L, "h": L * (1 + y * s), "st": L * (1 - y * AG_K * s), "t": int(time.time())})
    if p > cen * (1 + AG_T) or p < cen * (1 - AG_T): A["cen"] = p                            # merkez fiyatın peşinden kayar
    A["prev"] = p
    oz = AG_MJ + A["r"] + sum(ag_kz(q, p) for q in A["P"])
    if oz <= AG_MJ * 0.7:                                                                   # koruma: %30
        for q in A["P"][:]: ag_kapat(A, q, p, "koruma %30", AG_TAK)
        A["turlar"].append({"t0": A["t0"], "t": int(time.time()), "sonuc": round(A["r"], 3)}); A.update({"r": 0.0, "cen": p, "t0": int(time.time())})

def akilli_dongu():
    time.sleep(20)
    while AGD["ema"] is None:
        try: ag_ema_kur()
        except Exception as e: AGD["hata"] = "EMA: " + str(e)[:100]; time.sleep(30)
    while True:
        try:
            c = D["fiyat"].get("BTCUSDT")
            if c:
                dk = int(time.time() // 60)
                if dk > AGD["ema_dk"]: AGD["ema"] += (2 / (AG_EMA + 1)) * (c - AGD["ema"]); AGD["ema_dk"] = dk
                with KIL:                                                                      # v1.26: akıllı grid kapatıldı
                    A = S.get("akilli") or {}
                    for q in list(A.get("P", [])): ag_kapat(A, q, c, "Sadık kapattı", AG_TAK)
                    A["kapali"] = True
        except Exception as e: AGD["hata"] = "akıllı grid: " + str(e)[:120]
        time.sleep(2)

def akilli_veri():
    with KIL:
        A = S.get("akilli") or {}; c = D["fiyat"].get("BTCUSDT") or 0; e = AGD["ema"]
        P = [{"yon": "long" if q["y"] == 1 else "short", "giris": q["g"], "hedef": q["h"], "stop": q["st"], "pnl": round(ag_kz(q, c), 4), "t": q.get("t", 0)} for q in A.get("P", [])]
        acik = sum(x["pnl"] for x in P); sap = (c / e - 1) * 100 if e and c else None
        return {"v": VERSIYON + " · ⏹ KAPATILDI", "c": c, "ema": e, "sapma": sap, "izin": sap is not None and abs(sap) < AG_ESIK * 100, "esik": AG_ESIK * 100, "cen": A.get("cen"),
                "r": round(A.get("r", 0), 3), "acik": round(acik, 3), "oz": round(AG_MJ + A.get("r", 0) + acik, 3), "n": A.get("n", 0), "ns": A.get("ns", 0), "t0": A.get("t0"),
                "P": P, "son": (A.get("son") or [])[::-1], "turlar": (A.get("turlar") or [])[::-1], "mj": AG_MJ, "lev": AG_LEV, "s": AG_S * 100, "k": AG_K, "hata": AGD["hata"]}

AKILLI_SAYFA = SAYFA.split("<body>")[0].replace("<title>Sinyal Testi</title>", "<title>Akıllı Grid</title>") + r"""<body><div class="sar">
<div class="logo">🧠 AKILLI GRID · BTC (kağıt)</div><div class="alt" id="alt">yükleniyor…</div>
<div class="sek" style="grid-template-columns:1fr 1fr 1fr"><a href="https://worker-production-a529.up.railway.app/canli/">🟢 Canlı</a><a href="../">👥 Lider takibi</a><a href="../ayna/">🪞 Ayna</a></div>
<div class="pan"><div class="alt"><b>Kendini ayarlayan grid:</b> her <b>%0,3</b>'te bir seviye; merkezin altında LONG, üstünde SHORT açar, hedef <b>1 adım</b> (limit). Her işlemin kendi <b>stopu 5 adım</b>. Fiyat merkezden %3 uzaklaşınca <b>grid fiyatın peşinden kayar</b>. <b>Trend filtresi:</b> fiyat 12 saatlik ortalamadan %0,3'ten fazla uzaksa (trend var) yeni işlem açmaz, sadece açıkları yönetir. 20 $ × 50x, en çok 20 açık, bakiye %30 düşerse hepsi kapanır. Gerçek emir yok.</div></div>
<div class="pan"><b id="filtre">…</b></div>
<div class="kartlar" id="kart"></div>
<div class="pan"><h2>💼 Açık grid işlemleri</h2><div id="acik"></div></div>
<div class="pan"><h2>📒 Son kapananlar</h2><div id="son"></div></div>
</div><script>
const $=i=>document.getElementById(i),f=(x,d=2)=>Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}),sg=(x,d=2)=>(x>0?'+':'')+f(x,d),rk=x=>x>0?'art':x<0?'eks':'';
const ts=t=>new Date(t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
async function yenile(){try{const d=await (await fetch('api',{cache:'no-store'})).json();
 $('alt').textContent=`kağıt · ${d.v} · BTC ${f(d.c,1)}${d.t0?' · '+ts(d.t0)+"'den beri":''}`;
 $('filtre').innerHTML=d.sapma==null?'⏳ 12 saatlik ortalama hesaplanıyor…':(d.izin?`✅ Yatay piyasa — grid işlem açıyor <span class="alt">(ortalamadan %${sg(d.sapma,2)}, sınır ±%${f(d.esik,1)})</span>`:`⏸ Trend var — yeni işlem açılmıyor <span class="alt">(ortalamadan %${sg(d.sapma,2)}, sınır ±%${f(d.esik,1)})</span>`);
 $('kart').innerHTML=`<div class="k"><div class="e">Bakiye</div><div class="d ${rk(d.oz-d.mj)}">${f(d.oz)} $</div><div class="alt">marj ${f(d.mj,0)} $ × ${d.lev}x</div></div>
 <div class="k"><div class="e">Gerçekleşen</div><div class="d ${rk(d.r)}">${sg(d.r,3)} $</div><div class="alt">🎯 hedef ${d.n} · ⛔ stop ${d.ns}</div></div>
 <div class="k"><div class="e">Açık işlemler</div><div class="d ${rk(d.acik)}">${sg(d.acik,3)} $</div><div class="alt">${d.P.length} açık · merkez ${d.cen?f(d.cen,0):'–'}</div></div>
 <div class="k"><div class="e">Ayar</div><div class="d" style="font-size:16px">adım %${f(d.s,1)} · stop ${d.k} adım</div><div class="alt">kayma %3 · trend filtresi</div></div>`;
 $('acik').innerHTML=d.P.map(p=>{const k=Math.max(0,Math.min(100,(d.c-p.stop)/(p.hedef-p.stop)*100));
  return `<div class="pz"><div class="ust"><div><b>BTC</b> <span class="chip ${p.yon=='long'?'c-l':'c-s'}">${p.yon.toUpperCase()} ${d.lev}x</span><div class="alt">${ts(p.t)} · giriş ${f(p.giris,1)} → şimdi ${f(d.c,1)}</div></div><b class="${rk(p.pnl)}">${sg(p.pnl,3)} $</b></div>
  <div class="yol"><i style="left:calc(${k}% - 2px)"></i></div><div class="ucl"><span class="eks">⛔ stop ${f(p.stop,1)}</span><span>giriş ${f(p.giris,1)}</span><span class="art">🎯 hedef ${f(p.hedef,1)}</span></div>
  <div class="alt" style="text-align:center;margin-top:6px">🎯 Hedef <b class="art">${f(p.hedef,1)}</b> · <b>%${f(Math.abs(p.hedef/d.c-1)*100,2)}</b> kaldı</div></div>`}).join('')||'<div class="alt">Açık işlem yok.</div>';
 $('son').innerHTML=d.son.length?'<table><tr><th>Zaman</th><th>İşlem</th><th>Sonuç</th></tr>'+d.son.slice(0,20).map(x=>`<tr><td>${ts(x[0])}</td><td><span class="chip ${x[1]=='long'?'c-l':'c-s'}">${x[1].toUpperCase()}</span> ${f(x[2],1)} → ${f(x[3],1)}<div class="alt">${x[5]=='hedef'?'🎯 hedef':'⛔ '+x[5]}</div></td><td class="${rk(x[4])}"><b>${sg(x[4],3)} $</b></td></tr>`).join('')+'</table>':'<div class="alt">Henüz kapanış yok.</div>';
}catch(e){$('alt').textContent='⚠️ bağlantı yok'}}
yenile();setInterval(yenile,6000);
</script></body></html>"""

def kayit_dongu():
    while True:
        time.sleep(60); kaydet()

if __name__ == "__main__":
    print("📡 Sinyal kağıt botu", VERSIYON, "— GERÇEK EMİR YOK", flush=True)
    threading.Thread(target=fiyat_dongu, daemon=True).start()
    threading.Thread(target=tg_dongu, daemon=True).start()
    threading.Thread(target=kayit_dongu, daemon=True).start()
    threading.Thread(target=lider_dongu, daemon=True).start()
    threading.Thread(target=grid_dongu, daemon=True).start()                      # v1.14: 🔲 Grid
    threading.Thread(target=akilli_dongu, daemon=True).start()                    # v1.16: 🧠 Akıllı grid
    class S6(ThreadingHTTPServer):                                               # v1.17: IPv4+IPv6 (Railway özel ağı için; Canlı 429 almasın)
        address_family = socket.AF_INET6
        def server_bind(self):
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0); super().server_bind()
    try: S6(("::", int(os.getenv("PORT", "8080"))), H).serve_forever()
    except OSError: ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()
