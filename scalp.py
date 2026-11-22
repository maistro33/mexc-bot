# ⚡ 5 DK TREND SCALP — KAĞIT (Sadık'ın isteği, 22.11.2026). Borsaya emir kodu YOK.
# Sürüm S1.0
# Evren: Bitget'te son 24 saatte EN ÇOK YÜKSELEN ilk 30 kripto (hisse/ETF hariç, hacim ≥0,5 M$), saatte bir yenilenir.
# Strateji (testlerde 5 dk'da en az kaybettiren): 4 saatlikte güçlü trend + 5 dk'da EMA20'ye geri çekilip dönüş
#   LONG : 4H kapanış > EMA20 > EMA50 ve son 2 günün dibinden ≥%10 yukarıda · 5 dk: önceki mum EMA20'ye değdi, bu mum yeşil ve EMA20 üstünde kapandı
#   SHORT: tam tersi
#   Stop: son 4 mumun dibi/tepesi · Hedef: 1,5R · En çok 2 saat · aynı coine kapanıştan sonra 15 dk girilmez
# Para: 100 $ kağıt kasa · işlem başı 3 $ marj × 5x = 15 $ · en çok 10 açık
# Maliyet: giriş/çıkış %0,06 taker + %0,03 kayma (hedef limit: %0,02)
# Dürüst not: 1 aylık 5 dk testinde bu kural işlem başı ≈ −0,12…−0,19R çıktı. Burada CANLI ölçülüyor.
import json, os, threading, time, traceback
import requests

V = "S1.1 (22.11 22:25)"
BG = "https://api.bitget.com/api/v2/mix/market/"
KLASOR = os.getenv("DATA_DIR") or ("/data" if os.path.isdir("/data") else ".")
DOSYA = os.path.join(KLASOR, "scalp5.json")
KASA0, MJ, LEV, MAXA, EVREN = 100.0, 3.0, 5, 10, 30
TAKER, MAKER, KAYMA = 0.0006, 0.0002, 0.0003
GUC, RR, MAXDK, BEKLE = 0.10, 1.5, 120, 15 * 60

KIL = threading.RLock()
S = {"v": 1, "kasa": KASA0, "acik": {}, "gecmis": [], "log": [], "t0": int(time.time()), "son_kapanis": {}}
D = {"fiyat": {}, "trend": {}, "trend_t": 0, "evren": [], "kripto": set(), "hata": "", "tarama_t": 0, "izle": []}

def kaydet():
    with KIL:
        try:
            tmp = DOSYA + ".tmp"
            with open(tmp, "w") as f: json.dump(S, f); f.flush(); os.fsync(f.fileno())
            os.replace(tmp, DOSYA)
        except Exception as e: D["hata"] = "kayıt: " + str(e)[:80]

def yukle():
    try:
        with open(DOSYA) as f: d = json.load(f)
        if d.get("v") == 1: S.update(d)
    except Exception: pass

def log(m):
    with KIL: S["log"].append([int(time.time()), m]); del S["log"][:-300]

def ad(s): return s.replace("USDT", "")

def get(yol, **q):
    for i in range(3):
        try:
            r = requests.get(BG + yol, params={"productType": "USDT-FUTURES", **q}, timeout=12).json()
            if r.get("code") == "00000": return r["data"]
        except Exception: pass
        time.sleep(0.5 + i)
    return None

def ema(c, n):
    a = 2 / (n + 1); e = c[0]; o = []
    for x in c: e += a * (x - e); o.append(e)
    return o

def mum(s, g, n):
    d = get("candles", symbol=s, granularity=g, limit=str(n))
    if not d: return None
    d = sorted(d, key=lambda x: int(x[0]))
    adim = {"5m": 300, "4H": 14400}[g] * 1000
    if int(d[-1][0]) + adim > time.time() * 1000: d = d[:-1]          # sadece kapanmış mumlar
    return [[float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in d]

def evren():
    if not D["kripto"]:
        c = get("contracts") or []
        D["kripto"] = {x["symbol"] for x in c if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"}
    tk = get("tickers") or []
    # S1.1 (Sadık): Bitget "Change" sıralaması — son 24 saatte EN ÇOK YÜKSELEN ilk 30 kripto (hisse/ETF hariç, hacim ≥ 0,5 M$ — yoksa kağıt sonuç gerçekçi olmaz)
    return [x["symbol"] for x in sorted(tk, key=lambda x: -float(x.get("change24h") or 0))
            if x["symbol"] in D["kripto"] and x["symbol"] != "USDCUSDT" and float(x.get("usdtVolume") or 0) >= 500_000][:EVREN]

def trend_guncelle():                                   # saatte bir: 4H trend yönü
    D["evren"] = evren(); tr = {}
    for s in D["evren"]:
        m = mum(s, "4H", 100); time.sleep(0.04)
        if not m or len(m) < 60: continue
        c = [x[3] for x in m]; e20 = ema(c, 20)[-1]; e50 = ema(c, 50)[-1]; son = c[-1]
        dip = min(x[2] for x in m[-13:]); tepe = max(x[1] for x in m[-13:])
        if son > e20 > e50 and son / dip - 1 >= GUC: tr[s] = (1, round((son / dip - 1) * 100, 1))
        elif son < e20 < e50 and 1 - son / tepe >= GUC: tr[s] = (-1, round((1 - son / tepe) * 100, 1))
    with KIL: D["trend"] = tr; D["trend_t"] = int(time.time())
    log(f"🧭 4H trend: {len(tr)} coin güçlü trendde " + ", ".join(f"{ad(s)}{'↑' if u == 1 else '↓'}" for s, (u, _) in tr.items()))

def tara():                                             # her 5 dk mum kapanışında
    izle = []
    for s, (u, guc) in list(D["trend"].items()):
        if s in S["acik"] or time.time() - S["son_kapanis"].get(s, 0) < BEKLE: continue
        m = mum(s, "5m", 60); time.sleep(0.04)
        if not m or len(m) < 30: continue
        c = [x[3] for x in m]; e = ema(c, 20)
        izle.append({"s": ad(s), "yon": "long" if u == 1 else "short", "guc": guc, "uz": round((c[-1] / e[-1] - 1) * 100, 2)})
        dok = m[-2][2] <= e[-2] if u == 1 else m[-2][1] >= e[-2]
        don = (c[-1] > e[-1] and c[-1] > m[-1][0]) if u == 1 else (c[-1] < e[-1] and c[-1] < m[-1][0])
        if not (dok and don): continue
        st = min(x[2] for x in m[-4:]) * 0.998 if u == 1 else max(x[1] for x in m[-4:]) * 1.002
        p = D["fiyat"].get(s) or c[-1]; g = p * (1 + u * KAYMA); risk = abs(g - st) / g
        if not (0.004 <= risk <= 0.05) or u * (g - st) <= 0: continue
        with KIL:
            if len(S["acik"]) >= MAXA: log(f"⏸ {ad(s)} sinyal ama 10 işlem dolu"); continue
            hd = g + u * RR * abs(g - st); adet = MJ * LEV / g
            S["acik"][s] = {"u": u, "giris": g, "stop": st, "hedef": hd, "adet": adet, "t": int(time.time()), "risk": risk}
        log(f"{'🔺 LONG' if u == 1 else '🔻 SHORT'} {ad(s)} @ {g:g} · stop {st:g} (%{risk * 100:.2f}) · hedef {hd:g} · 4H trend %{guc}")
    with KIL: D["izle"] = sorted(izle, key=lambda x: abs(x["uz"]))[:10]; D["tarama_t"] = int(time.time())
    kaydet()

def kapat(s, cik, neden, ucret):
    with KIL:
        q = S["acik"].pop(s); u = q["u"]; n = q["adet"] * q["giris"]
        pnl = q["adet"] * u * (cik - q["giris"]) - n * TAKER - q["adet"] * cik * ucret
        S["kasa"] += pnl; S["son_kapanis"][s] = time.time()
        R = pnl / (n * q["risk"]) if q["risk"] else 0
        S["gecmis"].append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "cikis": cik, "t": q["t"], "tk": int(time.time()),
                            "pnl": round(pnl, 3), "R": round(R, 2), "neden": neden})
        del S["gecmis"][:-3000]
    log(f"{'✅' if pnl > 0 else '❌'} {ad(s)} kapandı · {neden} · {pnl:+.3f} $ ({R:+.2f}R)"); kaydet()

def dongu():
    yukle(); log(f"🚀 5dk Trend Scalp KAĞIT {V} başladı · kasa {S['kasa']:.2f} $")
    son5 = 0
    while True:
        try:
            tk = get("tickers") or []
            D["fiyat"] = {x["symbol"]: float(x["lastPr"]) for x in tk if x.get("lastPr")}
            for s in list(S["acik"]):
                q = S["acik"][s]; c = D["fiyat"].get(s); u = q["u"]
                if not c: continue
                if u * (c - q["stop"]) <= 0: kapat(s, c * (1 - u * KAYMA), "stop", TAKER)
                elif u * (c - q["hedef"]) > 0: kapat(s, q["hedef"], "🎯 hedef", MAKER)
                elif time.time() - q["t"] > MAXDK * 60: kapat(s, c * (1 - u * KAYMA), "süre (2 sa)", TAKER)
            if time.time() - D["trend_t"] > 1800: trend_guncelle()
            b = int((time.time() - 8) // 300)
            if b != son5: son5 = b; tara()
            D["hata"] = ""
        except Exception as e:
            D["hata"] = str(e)[:140]; traceback.print_exc()
        time.sleep(3)

def basla(): threading.Thread(target=dongu, daemon=True).start()

def veri():
    with KIL:
        G = S["gecmis"]; n = len(G); kz = [g for g in G if g["pnl"] > 0]; bk = sum(g["pnl"] for g in kz); bz = -sum(g["pnl"] for g in G if g["pnl"] <= 0)
        P = []; ac = 0
        for s, q in S["acik"].items():
            c = D["fiyat"].get(s) or q["giris"]; p = q["adet"] * q["u"] * (c - q["giris"]); ac += p
            P.append({"s": ad(s), "yon": "long" if q["u"] == 1 else "short", "giris": q["giris"], "c": c, "stop": q["stop"], "hedef": q["hedef"], "t": q["t"], "pnl": round(p, 3)})
        g0 = time.time() - time.time() % 86400; bugun = [g for g in G if g["tk"] >= g0]
        return {"v": V, "t0": S["t0"], "kasa0": KASA0, "oz": round(S["kasa"] + ac, 2), "acik": round(ac, 3), "n": n, "kaz": len(kz), "r": round(sum(g["pnl"] for g in G), 2),
                "ortR": round(sum(g["R"] for g in G) / n, 3) if n else 0, "pf": round(bk / bz, 2) if bz else None,
                "bugun_n": len(bugun), "bugun_r": round(sum(g["pnl"] for g in bugun), 2),
                "P": P, "son": G[::-1][:60], "log": S["log"][::-1][:40], "trend": [{"s": ad(s), "u": u, "guc": g} for s, (u, g) in D["trend"].items()],
                "izle": D["izle"], "tarama_t": D["tarama_t"], "hata": D["hata"], "evren": len(D["evren"])}

SAYFA = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>5dk Scalp</title>
<style>:root{--bg:#0d1220;--k:#161d30;--c:#26304a;--y:#e8ecf5;--s:#8b95ad;--g:#22d39b;--r:#ff5c7a}body{margin:0;background:var(--bg);color:var(--y);font:15px/1.45 -apple-system,system-ui,sans-serif}
.w{max-width:640px;margin:auto;padding:16px}h1{font-size:20px;margin:4px 0}h2{font-size:16px;margin:0 0 10px}.s{color:var(--s);font-size:13px}.p{background:var(--k);border:1px solid var(--c);border-radius:14px;padding:14px;margin:12px 0}
.g{display:grid;grid-template-columns:1fr 1fr;gap:10px}.n{font-size:22px;font-weight:800}.art{color:var(--g)}.eks{color:var(--r)}.r{display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid #ffffff10}
.ch{font-size:11px;font-weight:800;padding:2px 7px;border-radius:7px;background:#ffffff12}a{color:#7aa7ff}</style></head><body><div class="w">
<h1>⚡ 5 dk Trend Scalp · KAĞIT</h1><div class="s" id="alt"></div><div class="s"><a href="../">← 📈 Trend sayfası</a></div>
<div class="p g" id="kart"></div>
<div class="p"><h2>💼 Açık işlemler</h2><div id="acik"></div></div>
<div class="p"><h2>🧭 4 saatlikte güçlü trenddeki coinler</h2><div class="s" id="tr"></div><div class="s" style="margin-top:6px" id="tar"></div><div id="izle"></div></div>
<div class="p"><h2>📒 Kapanan</h2><div id="son"></div></div>
<div class="p s"><b>Kural.</b> Son 24 saatte en çok yükselen 30 coin (hacim ≥0,5 M$, saatte bir yenilenir). 4 saatlikte güçlü trend (EMA20>EMA50, 2 günde ≥%10) olan coinde, 5 dk mum EMA20'ye geri çekilip trend yönünde dönünce girer. Stop son 4 mumun dibi/tepesi, hedef 1,5R, en çok 2 saat. 3 $ × 5x, en çok 10 açık, komisyon+kayma dahil. <b>Test: 5 dk'da işlem başı ≈ −0,12…−0,19R — burada canlı ölçülüyor.</b></div>
<div class="p"><h2>🧾 Kayıt</h2><div class="s" id="log"></div></div></div><script>
const $=i=>document.getElementById(i),f=(x,d=2)=>Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}),sg=(x,d=2)=>(x>0?'+':'')+f(x,d),rk=x=>x>0?'art':x<0?'eks':'';
const fy=x=>{x=Number(x);return f(x,x>=1000?1:x>=1?4:6)},ts=t=>new Date(t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
async function y(){try{const d=await(await fetch('api',{cache:'no-store'})).json();
$('alt').textContent=`${d.v} · ${ts(d.t0)}'den beri · ${d.evren} coin`+(d.hata?' · ⚠️ '+d.hata:'');
$('kart').innerHTML=`<div><div class="s">Kasa (kağıt)</div><div class="n ${rk(d.oz-d.kasa0)}">${f(d.oz)} $</div><div class="s">açık ${sg(d.acik,3)} $ · ${d.P.length} işlem</div></div>
<div><div class="s">Kapanan</div><div class="n ${rk(d.r)}">${sg(d.r)} $</div><div class="s">${d.n} işlem · ${d.n?'%'+f(d.kaz/d.n*100,0)+' kârlı':'–'}</div></div>
<div><div class="s">Ortalama R · Profit factor</div><div class="n">${sg(d.ortR,2)}R · ${d.pf==null?'–':f(d.pf)}</div></div>
<div><div class="s">Bugün</div><div class="n ${rk(d.bugun_r)}">${sg(d.bugun_r)} $</div><div class="s">${d.bugun_n} işlem</div></div>`;
$('acik').innerHTML=d.P.map(p=>`<div class="r"><div><b>${p.s}</b> <span class="ch ${p.yon=='long'?'art':'eks'}">${p.yon.toUpperCase()} 5x</span><div class="s">${ts(p.t)} · ${fy(p.giris)} → ${fy(p.c)} · ⛔ ${fy(p.stop)} · 🎯 ${fy(p.hedef)}</div></div><b class="${rk(p.pnl)}">${sg(p.pnl,3)} $</b></div>`).join('')||'<div class="s">Açık işlem yok.</div>';
$('tr').innerHTML=d.trend.map(t=>`${t.s} ${t.u==1?'↑':'↓'}%${t.guc}`).join(' · ')||'–';
$('tar').textContent=d.tarama_t?'son 5 dk tarama '+ts(d.tarama_t)+' · EMA20\'ye en yakınlar:':'ilk tarama bekleniyor…';
$('izle').innerHTML=d.izle.map(x=>`<div class="r"><b>${x.s}</b><span class="s">${x.yon=='long'?'LONG arar':'SHORT arar'} · EMA20'ye %${f(x.uz)}</span></div>`).join('');
$('son').innerHTML=d.son.map(g=>`<div class="r"><div><b>${g.s}</b> <span class="ch">${g.yon.toUpperCase()}</span><div class="s">${ts(g.tk)} · ${Math.round((g.tk-g.t)/60)} dk · ${g.neden}</div></div><div style="text-align:right"><b class="${rk(g.pnl)}">${sg(g.pnl,3)} $</b><div class="s">${sg(g.R)}R</div></div></div>`).join('')||'<div class="s">Henüz yok.</div>';
$('log').innerHTML=d.log.slice(0,25).map(l=>ts(l[0])+' · '+l[1]).join('<br>');}catch(e){$('alt').textContent='⚠️ bağlantı yok'}}
y();setInterval(y,8000);</script></body></html>"""
