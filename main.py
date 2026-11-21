# ══════════════════════════════════════════════════════════════════════════════
#  📈 TREND KAĞIT BOTU — sadece KAĞIT (sanal para). Borsaya EMİR KODU YOK, API anahtarı GEREKMEZ.
#  Sürüm: K1.1 (21.11.2026) — eski/yavaş coinler (BTC, ETH, XRP, DOGE…) taranmaz
#
#  Neden bu tasarım (kod denetimi raporundaki dersler):
#   • Gerçek emir yolu yok → "stopsuz pozisyon", "şifresiz emir", "çift pozisyon" hataları imkânsız.
#   • Panelde hiçbir POST/değiştirme ucu yok; sadece okuma. PANEL_SIFRE tanımlıysa her sayfa şifreli.
#   • Risk HESABIN YÜZDESİ: işlem başı %1, açık toplam risk en çok %3, kaldıraç en çok 5x
#     ve stop her zaman likidasyondan çok önce (stop ≤ likidasyon mesafesinin %70'i).
#   • Maliyetler gerçekçi: giriş+çıkış komisyonu %0,06+%0,06, kayma %0,05+%0,05,
#     FUNDING her ödeme saatinde coinin o anki gerçek oranıyla düşülür/eklenir.
#   • Ölçüm: işlem sayısı, kazanma oranı, ortalama R, profit factor, en büyük düşüş — hepsi panelde.
#
#  Strateji (tek strateji): 4 saatlik mum kapanışında
#   LONG : kapanış son 55 mumun en yükseğini kırdı VE fiyat EMA200 üstünde
#   SHORT: kapanış son 55 mumun en düşüğünü kırdı VE fiyat EMA200 altında
#   Filtre: kırılım mumu (yüksek−düşük) ≥ 1,5 ATR ise girme (pompa/çöküş) · stop %15'ten uzaksa girme
#   Stop: 2 ATR · İz: son 20 mumun dibi/tepesi, sadece lehe ilerler · Hedef YOK (trend takibi)
#
#  Ortam değişkenleri (hepsi isteğe bağlı): PANEL_SIFRE, PORT, DATA_DIR (/data)
# ══════════════════════════════════════════════════════════════════════════════
import base64, json, os, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests

V = "K1.1 (21.11 01:20)"
BG = "https://api.bitget.com/api/v2/mix/market/"
KLASOR = os.getenv("DATA_DIR") or ("/data" if os.path.isdir("/data") else ".")
DOSYA = os.path.join(KLASOR, "trend_kagit.json")
SIFRE = os.getenv("PANEL_SIFRE", "")

# ── ayarlar ──
BASLANGIC = 100.0          # sanal kasa $
RISK = 0.01                # işlem başı risk: kasanın %1'i (stop olursa kaybedilecek)
TOPLAM_RISK = 0.03         # açık işlemlerin toplam riski en çok %3
MAX_LEV = 5                # kaldıraç tavanı
N_GIRIS, N_IZ, K_ATR, MUM_MAX, STOP_MAX = 55, 20, 2.0, 1.5, 0.15
EVREN = 40                 # en hacimli 40 kripto (hisse/emtia hariç)
ESKI = {"BTC", "ETH", "XRP", "ADA", "DOGE", "TRX", "LTC", "BCH", "BNB", "XLM", "ETC", "DOT", "LINK", "SHIB", "AVAX", "XMR", "UNI", "ATOM", "FIL", "NEAR"}   # K1.1 (Sadık): eski/yavaş coinler taranmaz
TAKER, KAYMA = 0.0006, 0.0005
GUN_ZARAR = 0.03           # gün içinde kasanın %3'ü kaybedilirse o gün yeni işlem yok

KIL = threading.RLock()
S = {"v": 1, "kasa": BASLANGIC, "acik": {}, "gecmis": [], "log": [], "t0": int(time.time()), "blok": 0, "tepe": BASLANGIC, "dd": 0.0, "fon_t": {}}
D = {"fiyat": {}, "fon": {}, "hata": "", "tarama_t": 0, "yakin": [], "kripto": set()}

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
    with KIL: S["log"].append([int(time.time()), m]); del S["log"][:-200]
    print(time.strftime("%d.%m %H:%M"), m, flush=True)

def ad(s): return s.replace("USDT", "")

def get(yol, **q):
    for i in range(3):
        try:
            r = requests.get(BG + yol, params={"productType": "USDT-FUTURES", **q}, timeout=15).json()
            if r.get("code") == "00000": return r["data"]
            D["hata"] = f"{yol}: {r.get('msg')}"
        except Exception as e: D["hata"] = f"{yol}: {str(e)[:80]}"
        time.sleep(1 + i)
    return None

# ── göstergeler ──
def ema(c, n):
    a = 2 / (n + 1); e = c[0]
    for x in c[1:]: e += a * (x - e)
    return e
def atr(m, n=14):
    a = m[1][1] - m[1][2]
    for i in range(1, len(m)):
        tr = max(m[i][1] - m[i][2], abs(m[i][1] - m[i - 1][3]), abs(m[i][2] - m[i - 1][3]))
        a = (a * (n - 1) + tr) / n
    return a

def mumlar(s):   # kapanmış 4H mumlar: [açılış, yüksek, düşük, kapanış]
    d = get("candles", symbol=s, granularity="4H", limit="400")
    if not d: return None
    d = sorted(d, key=lambda x: int(x[0]))
    if int(d[-1][0]) + 4 * 3600 * 1000 > time.time() * 1000: d = d[:-1]
    return [[float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in d]

def evren():
    if not D["kripto"]:
        c = get("contracts") or []
        D["kripto"] = {x["symbol"] for x in c if x.get("isRwa") != "YES" and x.get("symbolStatus") == "normal"}
    tk = get("tickers") or []
    return [x["symbol"] for x in sorted(tk, key=lambda x: -float(x.get("usdtVolume") or 0))
            if x["symbol"] in D["kripto"] and x["symbol"] != "USDCUSDT" and x["symbol"][:-4] not in ESKI][:EVREN]

def ozkaynak():
    a = 0.0
    for s, q in S["acik"].items():
        c = D["fiyat"].get(s) or q["giris"]; a += q["adet"] * q["u"] * (c - q["giris"])
    return S["kasa"] + a

def acik_risk():
    return sum(q["adet"] * max(0.0, q["u"] * (q["giris"] - q["stop"])) for q in S["acik"].values())

def bugun_zarar():
    g0 = time.time() - time.time() % 86400
    return -sum(g["pnl"] for g in S["gecmis"] if g["tk"] >= g0)

# ── strateji ──
def tara():
    ev = list(dict.fromkeys(list(S["acik"]) + evren())); yakin = []; aday = []   # açık işlemler (eski coin olsa da) izlenmeye devam eder
    for s in ev:
        m = mumlar(s); time.sleep(0.05)
        if not m or len(m) < 260: continue
        c = [x[3] for x in m]; A = atr(m); e = ema(c, 200); son = c[-1]
        ust = max(x[1] for x in m[-N_GIRIS - 1:-1]); alt = min(x[2] for x in m[-N_GIRIS - 1:-1])
        if s in S["acik"]:                                      # iz: son 20 mumun dibi/tepesi, sadece lehe
            q = S["acik"][s]
            yeni = min(x[2] for x in m[-N_IZ:]) if q["u"] == 1 else max(x[1] for x in m[-N_IZ:])
            if q["u"] * (yeni - q["stop"]) > 0:
                q["stop"] = yeni; q["tik"] = q.get("tik", 0) + 1
                log(f"▲ {ad(s)} iz {q['tik']}. kez ilerledi → stop {yeni:g} · kilitli {q['adet'] * q['u'] * (yeni - q['giris']):+.2f} $")
            continue
        u = 1 if son > ust and son > e else -1 if son < alt and son < e else 0
        yakin.append({"s": ad(s), "yon": "long" if son > e else "short", "uz": round(((ust / son - 1) if son > e else (1 - alt / son)) * 100, 2)})
        if not u: continue
        mum = (m[-1][1] - m[-1][2]) / A
        if mum >= MUM_MAX: log(f"🚫 {ad(s)} kırılımı atlandı: mum {mum:.1f} ATR (pompa/çöküş)"); continue
        stop_m = K_ATR * A / son
        if stop_m > STOP_MAX: log(f"🚫 {ad(s)} atlandı: stop %{stop_m * 100:.0f} uzakta (çok oynak)"); continue
        aday.append((abs(son / (ust if u == 1 else alt) - 1), s, u, A, stop_m))
    taze = time.time() % 14400 < 900                             # mum kapanışından en çok 15 dk sonra gir (eski kırılıma girme)
    for _, s, u, A, stop_m in sorted(aday, reverse=True):
        if taze: ac(s, u, A, stop_m)
        else: log(f"⏭ {ad(s)} kırılımı eski (mum kapanışından >15 dk), girilmedi")
    with KIL: D["yakin"] = sorted(yakin, key=lambda x: x["uz"])[:10]; D["tarama_t"] = int(time.time())

def ac(s, u, A, stop_m):
    with KIL:
        oz = ozkaynak()
        if bugun_zarar() >= oz * GUN_ZARAR: log(f"⏸ {ad(s)} atlandı: günlük zarar sınırı (%{GUN_ZARAR * 100:.0f})"); return
        risk_d = oz * RISK
        if acik_risk() + risk_d > oz * TOPLAM_RISK: log(f"⏸ {ad(s)} atlandı: açık toplam risk %{TOPLAM_RISK * 100:.0f} dolu"); return
        p = D["fiyat"].get(s)
        if not p: return
        g = p * (1 + u * KAYMA); st = g - u * K_ATR * A
        adet = risk_d / abs(g - st); notional = adet * g
        lev = max(1, min(MAX_LEV, int(0.7 / stop_m)))           # stop, likidasyon mesafesinin (≈1/lev) en çok %70'i
        marj = notional / lev
        if marj > oz - sum(q["marj"] for q in S["acik"].values()): log(f"⏸ {ad(s)} atlandı: marj yetmiyor"); return
        ucret = notional * TAKER; S["kasa"] -= ucret
        S["acik"][s] = {"u": u, "giris": g, "stop": st, "stop0": st, "adet": adet, "marj": marj, "lev": lev, "t": int(time.time()),
                        "ucret": ucret, "fon": 0.0, "risk_d": risk_d}
        log(f"{'🔺 LONG' if u == 1 else '🔻 SHORT'} {ad(s)} @ {g:g} · stop {st:g} (%{stop_m * 100:.1f}) · risk {risk_d:.2f} $ · {notional:.1f} $ poz. · {lev}x · marj {marj:.2f} $")
    kaydet()

def kapat(s, cikis, neden):
    with KIL:
        q = S["acik"].pop(s); u = q["u"]
        brut = q["adet"] * u * (cikis - q["giris"]); ucret = q["adet"] * cikis * TAKER
        pnl = brut - ucret - q["ucret"] + q["fon"]
        S["kasa"] += brut - ucret
        R = pnl / q["risk_d"] if q["risk_d"] else 0
        S["gecmis"].append({"s": ad(s), "yon": "long" if u == 1 else "short", "giris": q["giris"], "cikis": cikis, "t": q["t"], "tk": int(time.time()),
                            "pnl": round(pnl, 3), "R": round(R, 2), "fon": round(q["fon"], 3), "ucret": round(q["ucret"] + ucret, 3), "neden": neden, "tik": q.get("tik", 0)})
        oz = ozkaynak(); S["tepe"] = max(S["tepe"], oz); S["dd"] = max(S["dd"], (S["tepe"] - oz) / S["tepe"])
        log(f"{'✅' if pnl > 0 else '❌'} {ad(s)} kapandı · {neden} · {pnl:+.2f} $ ({R:+.2f}R) · funding {q['fon']:+.3f} $")
    kaydet()

def fonlama():   # her coinin ödeme saatinde gerçek oranla funding uygula
    d = get("current-fund-rate")
    if not d: return
    D["fon"] = {x["symbol"]: (float(x["fundingRate"]), int(x["nextUpdate"]) / 1000) for x in d if x.get("nextUpdate")}
    with KIL:
        for s, q in S["acik"].items():
            r, nt = D["fon"].get(s, (0, 0))
            son = S["fon_t"].get(s, 0)
            if nt and nt != son and nt - time.time() < 30:      # ödeme anı
                c = D["fiyat"].get(s) or q["giris"]; f = -q["u"] * r * q["adet"] * c   # long + oranda öder
                q["fon"] += f; S["kasa"] += f; S["fon_t"][s] = nt

def dongu():
    yukle(); log(f"🚀 Trend KAĞIT {V} başladı · kasa {S['kasa']:.2f} $ · işlem başı risk %{RISK * 100:.0f} · emir kodu yok")
    son_fon = 0
    while True:
        try:
            tk = get("tickers") or []
            D["fiyat"] = {x["symbol"]: float(x["lastPr"]) for x in tk if x.get("lastPr")}
            for s in list(S["acik"]):                            # stop kontrolü (fiyat stopa değdi mi)
                q = S["acik"][s]; c = D["fiyat"].get(s)
                if c and q["u"] * (c - q["stop"]) <= 0:
                    kapat(s, min(c, q["stop"]) * (1 - KAYMA) if q["u"] == 1 else max(c, q["stop"]) * (1 + KAYMA), "stop" if q.get("tik") == 0 or not q.get("tik") else "🔒 iz stopu")
            if time.time() - son_fon > 20: son_fon = time.time(); fonlama()
            blok = int((time.time() - 60) // 14400)              # 4H mum kapanışından 1 dk sonra
            if blok != S["blok"]: S["blok"] = blok; tara(); kaydet()
            D["hata"] = ""
        except Exception as e:
            D["hata"] = str(e)[:140]; traceback.print_exc()
        time.sleep(5)

# ── metrikler ──
def veri():
    with KIL:
        G = S["gecmis"]; n = len(G); kaz = [g for g in G if g["pnl"] > 0]; kay = [g for g in G if g["pnl"] <= 0]
        bk = sum(g["pnl"] for g in kaz); bz = -sum(g["pnl"] for g in kay)
        P = []
        for s, q in S["acik"].items():
            c = D["fiyat"].get(s) or q["giris"]
            P.append({"s": ad(s), "yon": "long" if q["u"] == 1 else "short", "giris": q["giris"], "c": c, "stop": q["stop"], "stop0": q["stop0"],
                      "t": q["t"], "lev": q["lev"], "marj": round(q["marj"], 2), "pnl": round(q["adet"] * q["u"] * (c - q["giris"]) - q["ucret"] + q["fon"], 3),
                      "kilit": round(q["adet"] * q["u"] * (q["stop"] - q["giris"]), 3), "tik": q.get("tik", 0), "fon": round(q["fon"], 3)})
        oz = ozkaynak()
        return {"v": V, "t0": S["t0"], "kasa0": BASLANGIC, "oz": round(oz, 2), "n": n, "kaz": len(kaz), "r": round(sum(g["pnl"] for g in G), 2),
                "ortR": round(sum(g["R"] for g in G) / n, 2) if n else 0, "pf": round(bk / bz, 2) if bz else None,
                "dd": round(max(S["dd"], (S["tepe"] - oz) / S["tepe"] if S["tepe"] else 0) * 100, 1),
                "fon": round(sum(g["fon"] for g in G) + sum(q["fon"] for q in S["acik"].values()), 3), "ucret": round(sum(g["ucret"] for g in G), 3),
                "acik_risk": round(acik_risk(), 2), "P": P, "son": G[::-1][:50], "log": S["log"][::-1][:40], "yakin": D["yakin"],
                "tarama_t": D["tarama_t"], "hata": D["hata"]}

SAYFA = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trend Kağıt</title>
<style>:root{--bg:#0d1220;--k:#161d30;--c:#26304a;--y:#e8ecf5;--s:#8b95ad;--g:#22d39b;--r:#ff5c7a}body{margin:0;background:var(--bg);color:var(--y);font:15px/1.45 -apple-system,system-ui,sans-serif}
.w{max-width:640px;margin:auto;padding:16px}h1{font-size:20px;margin:4px 0}h2{font-size:16px;margin:0 0 10px}.s{color:var(--s);font-size:13px}.p{background:var(--k);border:1px solid var(--c);border-radius:14px;padding:14px;margin:12px 0}
.g{display:grid;grid-template-columns:1fr 1fr;gap:10px}.n{font-size:22px;font-weight:800}.art{color:var(--g)}.eks{color:var(--r)}.r{display:flex;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid #ffffff10}
.ch{font-size:11px;font-weight:800;padding:2px 7px;border-radius:7px;background:#ffffff12}.u{background:#ff5c7a22;color:var(--r);padding:8px;border-radius:10px;display:none}</style></head><body><div class="w">
<h1>📈 Trend · KAĞIT</h1><div class="s" id="alt"></div><div class="u" id="u"></div>
<div class="p g" id="kart"></div>
<div class="p"><h2>💼 Açık işlemler</h2><div id="acik"></div></div>
<div class="p"><h2>👀 Kırılıma en yakın</h2><div class="s" id="tar"></div><div id="yak"></div></div>
<div class="p"><h2>📒 Kapanan</h2><div id="son"></div></div>
<div class="p s"><b>Kurallar.</b> Sadece kağıt, borsaya emir yok. 4 saatlik mum kapanışında son 55 mumun zirvesini (EMA200 üstünde) kırana LONG, dibini (EMA200 altında) kırana SHORT. Kırılım mumu ≥1,5 ATR ya da stop %15'ten uzaksa girmez. Stop 2 ATR, iz son 20 mumun dibi/tepesi, hedef yok.
<b>Risk:</b> işlem başı kasanın %1'i, açık toplam en çok %3, kaldıraç en çok 5x ve stop likidasyondan çok önce, günde %3 zararda yeni işlem yok. <b>Maliyet:</b> komisyon %0,06+%0,06, kayma %0,05+%0,05, funding gerçek oranla.</div>
<div class="p"><h2>🧾 Kayıt</h2><div class="s" id="log"></div></div></div><script>
const $=i=>document.getElementById(i),f=(x,d=2)=>Number(x).toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}),sg=(x,d=2)=>(x>0?'+':'')+f(x,d),rk=x=>x>0?'art':x<0?'eks':'';
const fy=x=>{x=Number(x);return f(x,x>=1000?1:x>=1?4:6)},ts=t=>new Date(t*1000).toLocaleString('tr-TR',{timeZone:'Europe/Stockholm',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
async function y(){try{const d=await(await fetch('api',{cache:'no-store'})).json();
$('alt').textContent=`${d.v} · ${ts(d.t0)}'den beri`;$('u').textContent=d.hata;$('u').style.display=d.hata?'block':'none';
$('kart').innerHTML=`<div><div class="s">Kasa (kağıt)</div><div class="n ${rk(d.oz-d.kasa0)}">${f(d.oz)} $</div><div class="s">başlangıç ${f(d.kasa0,0)} $ · açık risk ${f(d.acik_risk)} $</div></div>
<div><div class="s">Kapanan</div><div class="n ${rk(d.r)}">${sg(d.r)} $</div><div class="s">${d.n} işlem · ${d.n?'%'+f(d.kaz/d.n*100,0)+' kârlı':'–'}</div></div>
<div><div class="s">Ortalama R · Profit factor</div><div class="n">${sg(d.ortR)}R · ${d.pf==null?'–':f(d.pf)}</div></div>
<div><div class="s">En büyük düşüş · funding · komisyon</div><div class="n eks">%${f(d.dd,1)}</div><div class="s">funding ${sg(d.fon,3)} $ · komisyon ${f(d.ucret,3)} $</div></div>`;
$('acik').innerHTML=d.P.map(p=>`<div class="r"><div><b>${p.s}</b> <span class="ch ${p.yon=='long'?'art':'eks'}">${p.yon.toUpperCase()} ${p.lev}x</span><div class="s">${ts(p.t)} · giriş ${fy(p.giris)} → ${fy(p.c)} · stop ${fy(p.stop)}${p.tik?' · ▲ iz '+p.tik+'× · kilitli '+sg(p.kilit)+' $':''} · funding ${sg(p.fon,3)} $</div></div><b class="${rk(p.pnl)}">${sg(p.pnl)} $</b></div>`).join('')||'<div class="s">Açık işlem yok — kırılım bekleniyor (haftada birkaç işlem).</div>';
$('tar').textContent=d.tarama_t?'son tarama '+ts(d.tarama_t)+' · her 4 saatte':'ilk tarama bekleniyor…';
$('yak').innerHTML=d.yakin.map(x=>`<div class="r"><b>${x.s}</b><span class="s">${x.yon=='long'?'zirveye':'dibe'} %${f(x.uz)}</span></div>`).join('');
$('son').innerHTML=d.son.map(g=>`<div class="r"><div><b>${g.s}</b> <span class="ch">${g.yon.toUpperCase()}</span><div class="s">${ts(g.tk)} · ${g.neden} · funding ${sg(g.fon,3)} $</div></div><div style="text-align:right"><b class="${rk(g.pnl)}">${sg(g.pnl)} $</b><div class="s">${sg(g.R)}R</div></div></div>`).join('')||'<div class="s">Henüz yok.</div>';
$('log').innerHTML=d.log.slice(0,20).map(l=>ts(l[0])+' · '+l[1]).join('<br>');}catch(e){$('alt').textContent='⚠️ bağlantı yok'}}
y();setInterval(y,10000);</script></body></html>"""

class Panel(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _izin(self):
        if not SIFRE: return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                if base64.b64decode(h[6:]).decode().split(":", 1)[-1] == SIFRE: return True
            except Exception: pass
        self.send_response(401); self.send_header("WWW-Authenticate", 'Basic realm="Trend"'); self.end_headers(); return False
    def do_GET(self):
        if not self._izin(): return
        yol = self.path.split("?")[0].rstrip("/")
        if yol in ("", "/"): b, t = SAYFA.encode(), "text/html; charset=utf-8"
        elif yol == "/api": b, t = json.dumps(veri(), ensure_ascii=False).encode(), "application/json; charset=utf-8"
        else: self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", t); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

if __name__ == "__main__":
    threading.Thread(target=dongu, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Panel).serve_forever()
