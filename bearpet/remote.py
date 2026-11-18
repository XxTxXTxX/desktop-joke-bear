"""远端客户端：长轮询中继服务器，把手机发来的消息拉进来。

设计取舍：
  * 用长轮询而不是 WebSocket —— 断线重连、公司网络代理、手机热点都能过，
    不用引第三方依赖，服务端用标准库就能实现。
  * `since` 落盘（`.remote_state.json`）：电脑关机/断网期间的消息，
    下次连上会自动补发，不会丢。
  * 线程只负责收，收完丢进队列；窗口线程每帧 drain，避免跨线程碰 UI。
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class RemoteClient(threading.Thread):
    daemon = True

    def __init__(self, url: str, token: str, state_path: str, poll_timeout: int = 25):
        super().__init__(name="pet-remote")
        self.base = url.rstrip("/")
        self.token = token
        self.state_path = state_path
        self.poll_timeout = poll_timeout
        self.since = self._load_since()
        self.status = "offline"          # offline | online | error
        self.last_error = ""
        self.last_seen = 0.0
        self._queue: list[dict] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ------------------------------------------------------------ 状态
    def _load_since(self) -> int:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("since", 0))
        except Exception:
            return 0

    def _save_since(self):
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"since": self.since}, f)
            os.replace(tmp, self.state_path)
        except Exception:
            pass

    def drain(self) -> list[dict]:
        with self._lock:
            out, self._queue = self._queue, []
        return out

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------ 主循环
    def run(self):
        backoff = 2.0
        self.health()
        while not self._stop.is_set():
            try:
                msgs = self._poll()
                if msgs is None:
                    time.sleep(backoff)
                    backoff = min(30.0, backoff * 1.6)
                    continue
                backoff = 2.0
                self.status = "online"
                self.last_seen = time.time()
                if msgs:
                    with self._lock:
                        self._queue.extend(msgs)
                    self.since = max(int(m.get("id", 0)) for m in msgs)
                    self._save_since()
            except Exception as exc:                 # 网络错误 → 退避重连
                self.status = "error"
                self.last_error = f"{type(exc).__name__}: {exc}"
                time.sleep(backoff)
                backoff = min(30.0, backoff * 1.6)
        self.status = "offline"

    def health(self) -> bool:
        """快速探一下服务器，面板上的状态点不用等到第一次长轮询返回。"""
        try:
            req = urllib.request.Request(f"{self.base}/api/health")
            with urllib.request.urlopen(req, timeout=6) as resp:
                ok = resp.status == 200
            self.status = "online" if ok else "error"
            if ok:
                self.last_seen = time.time()
            return ok
        except Exception as exc:
            self.status = "error"
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def _poll(self) -> list[dict] | None:
        q = urllib.parse.urlencode({"since": self.since, "timeout": self.poll_timeout})
        req = urllib.request.Request(
            f"{self.base}/api/poll?{q}",
            headers={"X-Pet-Token": self.token, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.poll_timeout + 12) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(req.full_url, resp.status, "bad status", resp.headers, None)
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.status = "error"
            self.last_error = f"HTTP {exc.code}"
            time.sleep(3.0)
            return None
        return data.get("messages", [])

    # ------------------------------------------------------------ 发送（自测/双向用）
    def send(self, text: str, when: str = "", repeat: str = "", urgent: bool = False) -> dict:
        body = json.dumps({"text": text, "at": when, "repeat": repeat,
                           "urgent": urgent}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/api/send", data=body, method="POST",
            headers={"Content-Type": "application/json", "X-Pet-Token": self.token},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
