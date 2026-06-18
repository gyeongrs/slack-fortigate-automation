#!/bin/bash
# 簡易 HTTP サーバー（演習用）
PORT="${LAB_WEB_PORT:-8088}"
exec python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'lab-web OK')
    def log_message(self, *a): pass
HTTPServer(('0.0.0.0', $PORT), H).serve_forever()
"
