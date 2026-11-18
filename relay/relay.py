from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "messages.jsonl")
TOKEN_FILE = os.path.join(HERE, "token.txt")
PORT = int(os.environ.get("PET_PORT", "8787"))
BIND = os.environ.get("PET_BIND", "0.0.0.0")
KEEP_DAYS = 7

_lock = threading.Condition()
_messages: list[dict] = []
_seq = 0


def load_token() -> str:
    tok = os.environ.get("PET_TOKEN")
    if tok:
        return tok
    if os.path.exists(TOKEN_FILE):
        got = open(TOKEN_FILE, encoding="utf-8").read().strip()
        if got:
            return got
    tok = secrets.token_urlsafe(18)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok + "\n")
    return tok


def load_messages():
    global _seq
    if not os.path.exists(DATA):
        return
    cutoff = time.time() - KEEP_DAYS * 86400
    alive = []
    with open(DATA, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except Exception:
                continue
            if m.get("ts", 0) >= cutoff:
                alive.append(m)
    _messages.extend(alive)
    if alive:
        _seq = max(int(m.get("id", 0)) for m in alive)


def append(msg: dict):
    with open(DATA, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")


PHONE_HTML = """<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>发给她的桌宠</title>
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0;padding:18px;font:16px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
     background:#f6f2ec;color:#3a2a1a}
h1{font-size:19px;margin:0 0 4px}
.sub{font-size:12px;color:#8d7a66;margin-bottom:16px}
.card{background:#fff;border:2px solid #331208;border-radius:14px;padding:14px;margin-bottom:14px;
      box-shadow:0 2px 0 #33120822}
label{display:block;font-size:12px;color:#8d7a66;margin:8px 0 4px}
input,select,textarea{width:100%;padding:11px;border:1.5px solid #d9cfc2;border-radius:10px;
      font-size:16px;background:#fdfbf8;color:#3a2a1a}
textarea{min-height:74px;resize:vertical}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.chip{border:1.5px solid #d9cfc2;background:#fdfbf8;border-radius:999px;padding:8px 13px;
      font-size:14px;color:#5d4b3a}
.chip.on{background:#ffe9c9;border-color:#e0972e;color:#8a5a12;font-weight:600}
button.go{width:100%;margin-top:14px;padding:14px;border:none;border-radius:12px;
      background:#ce7e05;color:#fff;font-size:17px;font-weight:700}
button.go:disabled{opacity:.5}
#log{margin-top:10px;font-size:12px;color:#8d7a66;min-height:18px}
</style></head><body>
<h1>发给她的桌宠</h1>
<div class="sub">消息会出现在她电脑上那只熊的头顶，按她电脑的本地时间提醒。</div>

<div class="card">
  <label>说点什么</label>
  <textarea id="text" placeholder="记得喝水，别又忘了吃饭"></textarea>

  <label>什么时候</label>
  <select id="when">
    <option value="">现在就说</option>
    <option value="in:10m">10 分钟后</option>
    <option value="in:30m">30 分钟后</option>
    <option value="in:2h">2 小时后</option>
    <option value="20:00">今天 20:00（过点顺延到明天）</option>
    <option value="08:00">早上 08:00</option>
    <option value="22:30">晚上 22:30</option>
  </select>

  <label>重复</label>
  <select id="repeat">
    <option value="">不重复</option>
    <option value="daily">每天</option>
    <option value="weekday">工作日</option>
  </select>

  <div class="chips">
    <button class="chip" data-t="记得喝水">记得喝水</button>
    <button class="chip" data-t="起来走走，别坐太久">起来走走</button>
    <button class="chip" data-t="吃饭了吗">吃饭了吗</button>
    <button class="chip" data-t="早点睡，别熬夜">早点睡</button>
    <button class="chip" data-t="你很好看，今天也是">夸她一句</button>
  </div>

  <button class="go" id="send">发过去</button>
  <div id="log"></div>
</div>

<div class="card">
  <label>配对令牌（第一次填一次就行）</label>
  <input id="token" placeholder="服务器 relay/token.txt 里的那串">
  <div class="sub" style="margin:8px 0 0">令牌只存在这台手机的浏览器里，别发给别人。</div>
</div>

<script>
const $=s=>document.querySelector(s);
const KEY="petdex_token";
$("#token").value = localStorage.getItem(KEY) || new URLSearchParams(location.search).get("t") || "";
$("#token").oninput = e => localStorage.setItem(KEY, e.target.value.trim());
document.querySelectorAll(".chip").forEach(b=>b.onclick=()=>{$("#text").value=b.dataset.t;});
$("#send").onclick = async () => {
  const text=$("#text").value.trim(), token=$("#token").value.trim();
  if(!text){$("#log").textContent="先写点什么";return;}
  if(!token){$("#log").textContent="先填配对令牌";return;}
  $("#send").disabled=true; $("#log").textContent="发送中…";
  try{
    const r = await fetch("/api/send",{method:"POST",
      headers:{"Content-Type":"application/json","X-Pet-Token":token},
      body:JSON.stringify({text, at:$("#when").value, repeat:$("#repeat").value})});
    const j = await r.json();
    if(!r.ok) throw new Error(j.error||r.status);
    $("#log").textContent = "已发过去（#"+j.id+"）";
    $("#text").value="";
    if(navigator.vibrate) navigator.vibrate(30);
  }catch(e){ $("#log").textContent = "失败："+e.message; }
  finally{ $("#send").disabled=false; }
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "PetRelay/1.0"
    token = ""

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Pet-Token")
        self.end_headers()
        self.wfile.write(body)

    def _auth(self, q: dict) -> bool:
        tok = self.headers.get("X-Pet-Token") or (q.get("token", [""])[0])
        return bool(tok) and secrets.compare_digest(tok, self.token)

    def log_message(self, fmt, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Pet-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            body = PHONE_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if u.path == "/api/health":
            self._send_json({"ok": True, "server_time": time.time(),
                             "count": len(_messages), "seq": _seq})
            return
        if not self._auth(q):
            self._send_json({"error": "bad token"}, 401)
            return
        if u.path in ("/api/poll", "/api/recent"):
            since = int((q.get("since", ["0"])[0]) or 0)
            timeout = 0 if u.path == "/api/recent" else min(25, int(q.get("timeout", ["25"])[0]))
            deadline = time.time() + timeout
            with _lock:
                while True:
                    got = [m for m in _messages if int(m["id"]) > since]
                    if got or time.time() >= deadline:
                        break
                    _lock.wait(max(0.2, deadline - time.time()))
            self._send_json({"messages": got, "server_time": time.time()})
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path != "/api/send":
            self._send_json({"error": "not found"}, 404)
            return
        if not self._auth(q):
            self._send_json({"error": "bad token"}, 401)
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send_json({"error": "bad json"}, 400)
            return
        text = str(payload.get("text", "")).strip()
        if not text:
            self._send_json({"error": "empty text"}, 400)
            return
        global _seq
        with _lock:
            _seq += 1
            msg = {
                "id": _seq,
                "text": text[:160],
                "at": str(payload.get("at", "") or ""),
                "repeat": str(payload.get("repeat", "") or ""),
                "urgent": bool(payload.get("urgent")),
                "ts": time.time(),
            }
            _messages.append(msg)
            append(msg)
            _lock.notify_all()
        self._send_json({"ok": True, "id": msg["id"], "server_time": msg["ts"]})


def main():
    Handler.token = load_token()
    load_messages()
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    srv.daemon_threads = True
    lan = os.environ.get("PET_PUBLIC_URL", f"http://<这台机器的IP>:{PORT}")
    print(f"桌宠中继已启动： http://{BIND}:{PORT}")
    print(f"手机打开： {lan}/   令牌：{Handler.token}")
    print(f"已加载历史消息 {len(_messages)} 条")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("bye")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
