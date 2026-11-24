# KAPALI — 24.11.2026 22:30 (Sadık: "sonuçlar iyi değil, silecez")
# Bütün botlar durduruldu: 📈 Trend, 🔻 Dip Alım, ⚡ Scalp (kağıt) ve 🔍 Dip Bulucu / 🟢 gerçek işlem.
# Borsaya bağlanan HİÇBİR kod çalışmaz. Eski kodlar arsiv/ klasöründe (çalıştırılmaz).
# Sürüm X1.0
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SAYFA = """<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Botlar kapalı</title>
<style>body{margin:0;background:#0b1020;color:#e8ecf5;font:16px/1.5 system-ui;display:grid;place-items:center;min-height:100vh}div{max-width:420px;padding:24px;text-align:center}</style></head>
<body><div><h1>⏹️ Bütün botlar kapalı</h1><p>24.11.2026 · X1.0<br>Borsaya bağlanan kod çalışmıyor. Eski kodlar arşivde.</p></div></body></html>"""

class Panel(BaseHTTPRequestHandler):
    def do_GET(self):
        b = SAYFA.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), Panel).serve_forever()
