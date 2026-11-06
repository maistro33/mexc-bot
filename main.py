# 📡 SİNYAL KAĞIT BOTU — v1.0 (06.11.2026)
# Sadık: Telegram sinyal kanalını kağıtta test et. GERÇEK EMİR YOK: Bitget anahtarları hiç okunmaz, sadece herkese açık fiyat kullanılır.
# Kanal mesajı gelir gelmez o anki gerçek fiyattan (alış/satış fiyatı) sanal işlem açar; sonradan düzenlenen/silinen mesajlar sonucu değiştirmez.
# Kural: 100 $ kasa · işlem başı 10 $ marj × 10x · hedeflere eşit parçalarla kapatır · TP1 sonrası stop girişe · 7 gün en uzun.
import os, json, time, re, threading, asyncio, html
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import requests

VERSIYON = "v1.0 (06.11 02:30)"
KLASOR = (os.getenv("DATA_DIR") or ".").rstrip("/") + "/"
DOSYA = KLASOR + "sinyal.json"; OTURUM = KLASOR + "tg_oturum.txt"
API = "https://api.bitget.com/api/v2/mix/market/"
MJ, LEV, KASA, MAXA, UCRET, KAYMA, SURE = 10.0, 10, 100.0, 10, 0.0006, 0.0005, 7 * 86400
KIL = threading.RLock()
S = {"v": 1, "nakit": KASA, "baslangic": KASA, "acik": [], "gecmis": [], "mesaj": [], "egri": [], "kur": int(time.time())}
try:
    _d = json.load(open(DOSYA))
    if _d.get("v") == 1: S.update(_d)
except Exception: pass
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

def coz(metin):
    """Döner: dict(coin, yon, giris, hedefler, stop) ya da None."""
    m_g = re.search(r"entry(?:\s*price)?\s*[:\-–]?\s*([\d][\d.,\s]*)", metin, re.I)
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

# ───────────── kağıt işlem ─────────────
def ac(sg, metin):
    sym = sg["coin"] + "USDT"; yon = sg["yon"]
    with KIL:
        if any(p["sym"] == sym and p["yon"] == yon for p in S["acik"]): return "bu coinde aynı yönde açık işlem var"
        if len(S["acik"]) >= MAXA: return f"en çok {MAXA} açık"
        if S["nakit"] < MJ: return "nakit yetmiyor"
        c = D["ask"].get(sym) if yon == "long" else D["bid"].get(sym)
        if not c: return "fiyat yok"
        h1 = sg["hedefler"][0]
        if (yon == "long" and (c >= h1 or c <= sg["stop"])) or (yon == "short" and (c <= h1 or c >= sg["stop"])): return f"geç kalındı: fiyat {c:g} zaten TP1/stop ötesinde"
        adet = MJ * LEV / c; uc = adet * c * UCRET
        S["nakit"] -= MJ + uc
        S["acik"].append({"sym": sym, "coin": sg["coin"], "yon": yon, "giris": c, "sinyal_giris": sg["giris"], "hedefler": sg["hedefler"], "stop": sg["stop"],
                          "ilk_stop": sg["stop"], "adet": adet, "kalan": adet, "parca": adet / len(sg["hedefler"]), "vurulan": 0, "t": int(time.time()),
                          "gerceklesen": -uc, "ucret": uc, "metin": metin[:200]})
    return f"✅ AÇILDI {sg['coin']} {yon.upper()} @ {c:g} (sinyal {sg['giris']:g}, fark %{(c / sg['giris'] - 1) * 100:+.2f})"

def parca_kapat(p, adet, fiyat, neden):
    yon = 1 if p["yon"] == "long" else -1
    kz = (fiyat - p["giris"]) * adet * yon - adet * fiyat * UCRET
    p["gerceklesen"] += kz; p["ucret"] += adet * fiyat * UCRET; p["kalan"] -= adet
    S["nakit"] += MJ * adet / p["adet"] + (fiyat - p["giris"]) * adet * yon - adet * fiyat * UCRET
    if p["kalan"] <= p["adet"] * 1e-6:
        S["acik"].remove(p)
        S["gecmis"].append({"coin": p["coin"], "yon": p["yon"], "giris": p["giris"], "sinyal_giris": p["sinyal_giris"], "cikis": fiyat, "t0": p["t"], "t": int(time.time()),
                            "pnl": round(p["gerceklesen"], 3), "neden": neden, "vurulan": p["vurulan"], "hedef_n": len(p["hedefler"]), "ilk_stop": p["ilk_stop"]})
        del S["gecmis"][:-500]
        S["egri"].append([int(time.time()), round(ozsermaye(), 2)]); del S["egri"][:-800]

def yonet():
    with KIL:
        for p in list(S["acik"]):
            sym = p["sym"]; uzun = p["yon"] == "long"
            c = D["fiyat"].get(sym)
            if not c: continue
            if (uzun and c <= p["stop"]) or (not uzun and c >= p["stop"]):              # stop (borsa stopu gibi: stop fiyatı + kayma)
                f = p["stop"] * (1 - KAYMA if uzun else 1 + KAYMA)
                parca_kapat(p, p["kalan"], f, "başa baş stop" if p["vurulan"] else "stop"); continue
            while p["vurulan"] < len(p["hedefler"]):                                       # hedefler (limit emir gibi: hedef fiyatından)
                h = p["hedefler"][p["vurulan"]]
                if not ((uzun and c >= h) or (not uzun and c <= h)): break
                p["vurulan"] += 1; son = p["vurulan"] == len(p["hedefler"])
                parca_kapat(p, p["kalan"] if son else p["parca"], h, f"TP{p['vurulan']} (son hedef)" if son else f"TP{p['vurulan']}")
                if son: break
                if p["vurulan"] == 1: p["stop"] = p["giris"]                                 # TP1 → stop girişe
            if p in S["acik"] and time.time() - p["t"] > SURE:
                parca_kapat(p, p["kalan"], D["bid"].get(sym, c) if uzun else D["ask"].get(sym, c), "süre doldu (7 gün)")
        if not S["egri"] or time.time() - S["egri"][-1][0] >= 3600: S["egri"].append([int(time.time()), round(ozsermaye(), 2)])

def ozsermaye():
    t = S["nakit"]
    for p in S["acik"]:
        c = D["fiyat"].get(p["sym"]) or p["giris"]; yon = 1 if p["yon"] == "long" else -1
        t += MJ * p["kalan"] / p["adet"] + (c - p["giris"]) * p["kalan"] * yon
    return t

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
    c = TG["c"]; ara = (os.getenv("TG_KANAL") or "Signals - Bitcoin").strip(); hedef = None
    try:
        if ara.startswith("@") or "t.me/" in ara: hedef = await c.get_entity(ara)
        else:
            async for dl in c.iter_dialogs():
                if ara.lower() in (dl.name or "").lower(): hedef = dl.entity; break
    except Exception as e: D["hata"] = "kanal: " + str(e)[:120]
    if not hedef: D["tg"] = f"❓ Kanal bulunamadı: '{ara}' — gruba/kanala katıl ya da TG_KANAL'ı düzelt"; return
    D["kanal"] = getattr(hedef, "title", ara)
    try: TG["adminler"] = {u.id async for u in c.iter_participants(hedef, filter=ChannelParticipantsAdmins)}
    except Exception: TG["adminler"] = set()

    @c.on(events.NewMessage(chats=hedef))
    async def yeni(ev):
        try:
            metin = ev.raw_text or ""
            if TG["adminler"] and ev.sender_id not in TG["adminler"] and not ev.post: return          # sadece yönetici / kanal mesajı
            if not re.search(r"entry|stop|target|\bTP\b|\bSL\b", metin, re.I): return
            sg = coz(metin)
            if not sg: sonuc = "çözülemedi (giriş/hedef/stop eksik)"
            elif "hata" in sg: sonuc = "atlandı: " + sg["hata"]
            else: sonuc = ac(sg, metin)
            with KIL: log_mesaj(metin, sonuc)
            kaydet()
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
            c = D["fiyat"].get(p["sym"]) or p["giris"]; yon = 1 if p["yon"] == "long" else -1
            acik.append({**{k: p[k] for k in ("coin", "yon", "giris", "sinyal_giris", "hedefler", "stop", "vurulan", "t")}, "c": c,
                         "pnl": round(p["gerceklesen"] + (c - p["giris"]) * p["kalan"] * yon, 3)})
        return {"v": VERSIYON, "tg": D["tg"], "kanal": D["kanal"], "hata": D["hata"], "adim": D["adim"], "oz": round(oz, 2), "baslangic": S["baslangic"],
                "nakit": round(S["nakit"], 2), "acik": acik, "gecmis": G[-50:][::-1], "mesaj": S["mesaj"][-25:][::-1], "kur": S["kur"],
                "ozet": {"n": len(G), "kaz": sum(1 for g in G if g["pnl"] > 0), "toplam": round(sum(g["pnl"] for g in G), 2),
                         "stop": sum(1 for g in G if g["neden"] == "stop"), "tp1": sum(1 for g in G if g["vurulan"] >= 1), "hepsi": sum(1 for g in G if g["vurulan"] == g["hedef_n"])}}

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
<div class="logo">📡 SİNYAL TESTİ</div><div class="alt" id="alt">yükleniyor…</div>
<div class="pan"><b id="tg">…</b><div class="alt" id="hata"></div><div id="giris"></div></div>
<div class="pan"><div class="alt">Kanal mesajı gelir gelmez <b>o anki gerçek fiyattan</b> sanal işlem açar (sonradan düzenlenen/silinen mesajlar sonucu değiştirmez). 100 $ kasa · işlem başı <b>10 $ × 10x</b> · hedeflere eşit parçalarla kapatır · <b>TP1 sonrası stop girişe</b> · stop borsa stopu gibi (+%0,05 kayma) · ücret %0,06 · en çok 7 gün. <b>Gerçek emir yok.</b></div></div>
<div class="kartlar" id="kart"></div>
<div class="pan"><h2>💼 Açık işlemler</h2><div id="acik"></div></div>
<div class="pan"><h2>📒 Kapanan</h2><div id="gec"></div></div>
<div class="pan"><h2>💬 Son sinyal mesajları</h2><div id="msg"></div></div>
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
 $('alt').textContent=`kağıt · ${d.v} · ${ts(d.kur)}'den beri`;$('tg').textContent=d.tg;$('hata').textContent=d.hata||'';girisCiz(d.adim||'');
 $('kart').innerHTML=`<div class="k"><div class="e">Bakiye</div><div class="d">${f(d.oz)} $</div><div class="alt">başlangıç ${f(d.baslangic,0)} $ · boşta ${f(d.nakit)} $</div></div>
 <div class="k"><div class="e">Kâr / zarar</div><div class="d ${rk(d.oz-d.baslangic)}">${sg(d.oz-d.baslangic)} $</div><div class="alt">kapanan ${sg(o.toplam)} $</div></div>
 <div class="k"><div class="e">İşlem</div><div class="d">${o.n}</div><div class="alt">kârlı ${o.n?'%'+f(o.kaz/o.n*100,0):'–'} · açık ${d.acik.length}</div></div>
 <div class="k"><div class="e">Hedefler</div><div class="d" style="font-size:16px">TP1 ${o.tp1} · hepsi ${o.hepsi}</div><div class="alt">direkt stop ${o.stop}</div></div>`;
 $('acik').innerHTML=d.acik.map(p=>`<div class="pz"><div class="ust"><div><b>${p.coin}</b> <span class="chip ${p.yon=='long'?'c-l':'c-s'}">${p.yon.toUpperCase()} 10x</span><div class="alt">${ts(p.t)} · giriş ${fy(p.giris)} (sinyal ${fy(p.sinyal_giris)}) → şimdi ${fy(p.c)}</div><div class="alt">stop ${fy(p.stop)}${p.vurulan?' (girişte)':''}</div></div><b class="${rk(p.pnl)}">${sg(p.pnl,3)} $</b></div><div class="tp">${p.hedefler.map((h,i)=>`<span class="${i<p.vurulan?'v':''}">TP${i+1} ${fy(h)}</span>`).join('')}</div></div>`).join('')||'<div class="alt">Açık işlem yok. Kanalda yeni sinyal bekleniyor.</div>';
 $('gec').innerHTML=d.gecmis.length?'<table><tr><th>Coin</th><th>Sonuç</th><th>Kâr</th></tr>'+d.gecmis.map(g=>`<tr><td><b>${g.coin}</b> <span class="chip ${g.yon=='long'?'c-l':'c-s'}">${g.yon.toUpperCase()}</span><div class="alt">${ts(g.t)}</div></td><td>${g.neden}<div class="alt">${g.vurulan}/${g.hedef_n} hedef</div></td><td class="${rk(g.pnl)}"><b>${sg(g.pnl,3)} $</b></td></tr>`).join('')+'</table>':'<div class="alt">Henüz yok.</div>';
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

def kayit_dongu():
    while True:
        time.sleep(60); kaydet()

if __name__ == "__main__":
    print("📡 Sinyal kağıt botu", VERSIYON, "— GERÇEK EMİR YOK", flush=True)
    threading.Thread(target=fiyat_dongu, daemon=True).start()
    threading.Thread(target=tg_dongu, daemon=True).start()
    threading.Thread(target=kayit_dongu, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()
