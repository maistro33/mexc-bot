# 📡 SİNYAL KAĞIT BOTU — v1.0 (06.11.2026)
# Sadık: Telegram sinyal kanalını kağıtta test et. GERÇEK EMİR YOK: Bitget anahtarları hiç okunmaz, sadece herkese açık fiyat kullanılır.
# Kanal mesajı gelir gelmez o anki gerçek fiyattan (alış/satış fiyatı) sanal işlem açar; sonradan düzenlenen/silinen mesajlar sonucu değiştirmez.
# Kural (v1.3): 100 $ kasa · işlem başı 10 $ marj × 10x · kanaldan SADECE coin + yön · stop / iz süren stopu bot seçer (çıkış yarışı) · 24 sa en uzun.
import os, json, time, re, threading, asyncio, html
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import requests

VERSIYON = "v1.7 (09.11 17:10)"
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
    if not ara:
        with KIL:
            if S["gecmis"] or S["acik"] or S["mesaj"]:
                S.setdefault("arsiv", []).append({"kanal": S.get("kanal", "?"), "oz": round(ozsermaye(), 2), "gecmis": S["gecmis"], "acik": S["acik"], "bitis": int(time.time())})
                S.update({"nakit": KASA, "acik": [], "gecmis": [], "mesaj": [], "egri": [], "kur": int(time.time()), "golge": [], "yaris": []})
            S["kanal"] = ""
        kaydet(); D["tg"] = "📭 Telegram bağlı · kanal seçilmedi (yeni kanal bekleniyor)"; D["adim"] = None; return
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
                         "adim": len(p["iz"].get("adim", [])), "adim_t": (p["iz"].get("adim") or [0])[-1], "kilit": round(MJ * LEV * yuzde(p["yon"], p["giris"], p["iz"]["stop"]) / 100, 3), "pnl": round(MJ * LEV * yuzde(p["yon"], p["giris"], c) / 100, 3)})
        return {"v": VERSIYON, "klasor": KLASOR, "tg": D["tg"], "lider": L["durum"], "liderler": L["liste"], "lider_tarama": int(time.time() - L["tarama_t"]) if L["tarama_t"] else -1, "lider_sonuc": lider_sonuc(), "kanal": D["kanal"], "hata": D["hata"], "adim": D["adim"], "oz": round(oz, 2), "baslangic": S["baslangic"],
                "nakit": round(S["nakit"], 2), "acik": acik, "gecmis": G[-50:][::-1], "mesaj": S["mesaj"][-25:][::-1], "kur": S["kur"], "yaris": yaris_veri(),
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
.uy{background:rgba(255,200,87,.1);border:1px solid rgba(255,200,87,.4);border-radius:12px;padding:10px;font-size:13px;word-break:break-all}</style></head><body><div class="sar">
<div class="logo">📡 SİNYAL TESTİ · 👥 LİDER TAKİBİ</div><div class="alt" id="alt">yükleniyor…</div>
<div class="pan"><b id="ld">…</b><div class="alt" id="ldx"></div><div style="margin-top:8px"><span class="alt" id="tg">…</span></div><div class="alt" id="hata"></div><div id="giris"></div></div>
<div class="pan"><div class="alt"><b>Kaynak:</b> Binance Copy Trading lider trader'ları (son 30 gün ROI sırası, ama <b>takipçileri de kâr etmiş</b>, en büyük düşüş &lt;%40, kazanma ≥%55) + <b>OKX</b> lider trader'ları (resmi açık API; en az 30 gün liderlik, kazanma ≥%55, kârda). Bir lider <b>yeni pozisyon açtığı an</b> aynı coin + yönde açılır (liderin kapanışı izlenmez). Telegram kanalı da bağlanırsa aynı kurallar. Kanal mesajı gelir gelmez <b>o anki gerçek fiyattan</b> sanal işlem açar (sonradan düzenlenen/silinen mesajlar sonucu değiştirmez). 100 $ kasa · işlem başı <b>10 $ × 10x</b> · kanaldan <b>sadece coin + yön</b> alınır; kanalın TP/stop/DCA'sı kullanılmaz · <b>stop ve iz süren stopu bot kendisi seçer</b> (çıkış yarışı: her sinyal 27 ayarla gölgede takip edilir, 10 sinyalden sonra en iyisi kullanılır) · stop borsa stopu gibi (+%0,05 kayma) · ücret %0,06 · en çok 24 saat. <b>Gerçek emir yok.</b></div></div>
<div class="kartlar" id="kart"></div>
<div class="pan"><h2>💼 Açık işlemler</h2><div id="acik"></div></div>
<div class="pan"><h2>📒 Kapanan</h2><div id="gec"></div></div>
<div class="pan"><h2>🏆 Lider bazında sonuç</h2><div id="lsn"></div></div>
<div class="pan"><h2>🏁 Çıkış yarışı</h2><div id="yr"></div></div>
<div class="pan"><h2>💬 Son sinyaller (lider + kanal)</h2><div id="msg"></div></div>
</div><script>
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
async function yenile(){try{const d=await (await fetch('api',{cache:'no-store'})).json(),o=d.ozet;
 $('alt').textContent=`kağıt · ${d.v} · ${ts(d.kur)}'den beri · kayıt: ${d.klasor}`;$('tg').textContent='Telegram: '+d.tg;$('ld').textContent=d.lider+(d.lider_tarama>=0?` · son tarama ${d.lider_tarama} sn önce`:'');$('ldx').innerHTML=(d.liderler||[]).map(x=>`<b>${x.borsa}</b> ${es(x.ad)} <span class="art">%${f(x.roi,0)}</span> <span class="alt">(${x.mdd!=null?'düşüş %'+f(x.mdd,0)+', ':''}kaz %${f(x.kaz,0)})</span>`).join(' · ');
 const ls=d.lider_sonuc||[];$('lsn').innerHTML=ls.length?'<table><tr><th>Kaynak</th><th>İşlem</th><th>Kârlı</th><th>Toplam</th></tr>'+ls.map(t=>`<tr><td>${es(t.kaynak)}</td><td>${t.n}</td><td>%${f(t.kaz/t.n*100,0)}</td><td class="${rk(t.top)}"><b>${sg(t.top,2)} $</b></td></tr>`).join('')+'</table>':'<div class="alt">Henüz kapanan işlem yok.</div>';$('hata').textContent=d.hata||'';girisCiz(d.adim||'');
 $('kart').innerHTML=`<div class="k"><div class="e">Bakiye</div><div class="d">${f(d.oz)} $</div><div class="alt">başlangıç ${f(d.baslangic,0)} $ · boşta ${f(d.nakit)} $</div></div>
 <div class="k"><div class="e">Kâr / zarar</div><div class="d ${rk(d.oz-d.baslangic)}">${sg(d.oz-d.baslangic)} $</div><div class="alt">kapanan ${sg(o.toplam)} $</div></div>
 <div class="k"><div class="e">İşlem</div><div class="d">${o.n}</div><div class="alt">kârlı ${o.n?'%'+f(o.kaz/o.n*100,0):'–'} · açık ${d.acik.length}</div></div>
 <div class="k"><div class="e">Bizim ayar</div><div class="d" style="font-size:16px">stop %${f(d.yaris.secili[0],0)} · iz %${f(d.yaris.secili[1],0)}/%${f(d.yaris.secili[2],1)}</div><div class="alt">${d.yaris.n<d.yaris.min?`yarış öğreniyor ${d.yaris.n}/${d.yaris.min}`:'yarışın seçtiği'} · stop ${o.stop} · iz ${o.iz}</div></div>`;
 const y=d.yaris;$('yr').innerHTML=`<div class="alt" style="margin-bottom:6px">${y.n} biten sinyal · ${y.takipte} takipte · birim: fiyat % (ücret dahil)</div><table><tr><th>Stop / iz başlar / geriden</th><th>Kârlı</th><th>Toplam</th></tr>`+y.liste.map(x=>`<tr><td>${x.secili?'👉 ':''}%${x.k[0]} / %${x.k[1]} / %${x.k[2]}</td><td>${x.kaz}/${y.n}</td><td class="${rk(x.top)}"><b>${sg(x.top)}%</b></td></tr>`).join('')+'</table>';
 $('acik').innerHTML=d.acik.map(p=>`<div class="pz"><div class="ust"><div><b>${p.coin}</b> <span class="chip ${p.yon=='long'?'c-l':'c-s'}">${p.yon.toUpperCase()} 10x</span>${p.kaynak?`<div class="alt"><b>${es(p.kaynak)}</b></div>`:''}<div class="alt">${ts(p.t)} · giriş ${fy(p.giris)} (sinyal ${fy(p.sinyal_giris)}) → şimdi ${fy(p.c)}</div><div class="alt">${p.aktif?'🔒 iz süren stop':'⛔ stop'} ${fy(p.stop)} · ayar %${p.ayar[0]}/%${p.ayar[1]}/%${p.ayar[2]}</div>${p.aktif?`<div class="alt" style="margin-top:4px">🔒 <span class="art">${'▲'.repeat(Math.min(p.adim,12))}${p.adim>12?'…':''}</span> kilit <b class="art">${p.adim}×</b> ilerledi${p.adim?' · son '+new Date(p.adim_t*1000).toLocaleTimeString('tr-TR',{timeZone:'Europe/Stockholm',hour:'2-digit',minute:'2-digit'}):''} · kilitli kâr <b class="${rk(p.kilit)}">${sg(p.kilit,3)} $</b></div>`:''}</div><b class="${rk(p.pnl)}">${sg(p.pnl,3)} $</b></div></div></div>`).join('')||'<div class="alt">Açık işlem yok. Kanalda yeni sinyal bekleniyor.</div>';
 $('gec').innerHTML=d.gecmis.length?'<table><tr><th>Coin</th><th>Sonuç</th><th>Kâr</th></tr>'+d.gecmis.map(g=>`<tr><td><b>${g.coin}</b> <span class="chip ${g.yon=='long'?'c-l':'c-s'}">${g.yon.toUpperCase()}</span><div class="alt">${ts(g.t)}${g.kaynak?' · '+es(g.kaynak):''}</div></td><td>${g.neden}<div class="alt">fiyat %${sg(g.yuzde||0)}${g.ayar?' · ayar %'+g.ayar.join('/%'):''}</div></td><td class="${rk(g.pnl)}"><b>${sg(g.pnl,3)} $</b></td></tr>`).join('')+'</table>':'<div class="alt">Henüz yok.</div>';
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
    except Exception as e: L["durum"] = "⚠️ OKX listesi alınamadı: " + str(e)[:80]
    return sec

def lider_pozlar(x):
    """Döner: {(BTCUSDT, long/short): giriş} ya da None (hata)."""
    simdi = {}
    if x.get("borsa", "Binance") == "Binance":
        r = requests.get(BN + "lead-data/positions", params={"portfolioId": x["id"]}, timeout=15).json()
        if r.get("code") != "000000": return None
        for p in r.get("data") or []:
            a = float(p.get("positionAmount") or 0)
            if a: simdi[(p["symbol"], "long" if a > 0 else "short")] = float(p.get("entryPrice") or 0)
    else:
        r = requests.get(OKX + "public-current-subpositions", params={"instType": "SWAP", "uniqueCode": x["id"], "limit": "50"}, timeout=15).json()
        if r.get("code") != "0": return None
        for p in r.get("data") or []:
            if not p.get("instId", "").endswith("-USDT-SWAP"): continue
            ps = p.get("posSide"); a = float(p.get("subPos") or 0)
            yon = ps if ps in ("long", "short") else ("long" if a > 0 else "short")
            simdi[(p["instId"].replace("-USDT-SWAP", "") + "USDT", yon)] = float(p.get("openAvgPx") or 0)
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
                if x["id"] not in L["onceki"]: L["onceki"][x["id"]] = simdi; continue          # ilk görüş: eski pozisyonlara girilmez
                for (sym, yon), gir in simdi.items():
                    if (sym, yon) in L["onceki"][x["id"]] or not sym.endswith("USDT"): continue
                    coin = sym[:-4]; metin = f"👥 {x['borsa']} · {x['ad']} (30g ROI %{x['roi']:g}) yeni {yon.upper()} açtı: {coin} @ {gir:g}"
                    if sym not in D["semboller"]: sonuc = "atlandı: Bitget'te yok"
                    else: sonuc = ac({"coin": coin, "yon": yon, "giris": gir, "kaynak": f"👥 {x['borsa']} · {x['ad']}"}, metin)
                    with KIL: log_mesaj(metin, sonuc)
                    kaydet()
                L["onceki"][x["id"]] = simdi
            L["tarama_t"] = time.time()
            nb = sum(1 for x in L["liste"] if x["borsa"] == "Binance"); L["durum"] = f"✅ Lider takibi · Binance {nb} + OKX {len(L['liste']) - nb} lider izleniyor"
        except Exception as e: L["durum"] = "⚠️ Lider takibi hatası (tekrar denenecek): " + str(e)[:120]
        time.sleep(10)

def lider_sonuc():
    T = {}
    for g in S["gecmis"]:
        k = g.get("kaynak") or "Telegram"; t = T.setdefault(k, {"kaynak": k, "n": 0, "kaz": 0, "top": 0.0})
        t["n"] += 1; t["kaz"] += 1 if g["pnl"] > 0 else 0; t["top"] = round(t["top"] + g["pnl"], 3)
    return sorted(T.values(), key=lambda t: -t["top"])

def kayit_dongu():
    while True:
        time.sleep(60); kaydet()

if __name__ == "__main__":
    print("📡 Sinyal kağıt botu", VERSIYON, "— GERÇEK EMİR YOK", flush=True)
    threading.Thread(target=fiyat_dongu, daemon=True).start()
    threading.Thread(target=tg_dongu, daemon=True).start()
    threading.Thread(target=kayit_dongu, daemon=True).start()
    threading.Thread(target=lider_dongu, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()
