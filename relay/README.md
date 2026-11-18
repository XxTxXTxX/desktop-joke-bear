# 手机 → 她的电脑：远程提醒

一只桌宠 + 一个中转服务。你在手机上打一句话，它出现在她电脑上那只熊的头顶，
并且**按她电脑的本地时间**决定什么时候说。

```
手机浏览器 ──HTTPS──> relay.py（VPS / 家里常开的机器）<──长轮询── 她的电脑（桌宠）
```

## 为什么是长轮询

- 不用 WebSocket：公司代理、手机热点、休眠唤醒都能过，实现只用标准库；
- `since` 落盘（`.remote_state.json`）：她电脑关机/断网期间的消息，下次连上自动补发；
- 服务端只存 7 天，消息落 `relay/messages.jsonl`，令牌鉴权（`secrets.compare_digest`）。

## 三种部署方式

### 1. 局域网（最快，零成本）

她电脑上开：

```bash
python relay/relay.py            # 默认 0.0.0.0:8787
```

手机连同一个 WiFi，浏览器打开 `http://<她电脑的内网IP>:8787`，
第一次填 `relay/token.txt` 里的令牌。Windows 防火墙放行 8787 即可。

### 2. VPS + HTTPS（她在外面也能收到）

```bash
# 服务器上
export PET_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(18))")
export PET_PORT=8787
python3 relay/relay.py
```

前面挂 Caddy（自动 HTTPS）：

```caddyfile
pet.example.com {
    reverse_proxy 127.0.0.1:8787
}
```

systemd 常驻：

```ini
# /etc/systemd/system/pet-relay.service
[Unit]
Description=Petdex relay
After=network.target

[Service]
WorkingDirectory=/opt/pet-relay
Environment=PET_TOKEN=REPLACE_WITH_TOKEN
Environment=PET_PORT=8787
ExecStart=/usr/bin/python3 /opt/pet-relay/relay.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`systemctl enable --now pet-relay`

### 3. Cloudflare Tunnel（不开放端口）

她电脑或 VPS 上：`cloudflared tunnel --url http://127.0.0.1:8787`，
把给出的 https 地址填进 `.bear.json` 的 `remote.url`。

## 客户端配置（她的电脑）

`.bear.json`：

```json
{
  "remote": { "url": "https://pet.example.com", "token": "<relay/token.txt>" },
  "quiet": ["23:30", "08:00"],
  "quiet_on": true
}
```

改完重启桌宠即可；右键 → 提醒，面板上的绿点表示"手机端已连接"。

## 时间怎么算（这是重点）

手机只发"规格"，**由她电脑的本地时钟解析**：

| 手机端选择 | 发出去的值 | 电脑端解析 |
|---|---|---|
| 现在就说 | `at: ""` | 立刻 |
| 10 分钟后 | `at: "in:10m"` | 本机时间 + 600s |
| 今天 20:00 | `at: "20:00"` | 下一个 20:00（过点顺延到明天）|
| 每天 | `repeat: "daily"` | 触发后自动排到次日同一时刻 |
| 工作日 | `repeat: "weekday"` | 跳过周六日 |

静音时段：`23:30–08:00` 之间收到的非紧急提醒会被压到 08:00 再说，
文字前面加「（补一句）」；勾了紧急的照常立刻送达。

## 她这边的透明性

这个功能是"提醒工具"，不是远程监控：

- 所有排队的提醒都在右键 → 提醒 面板里列出来，她随时能看见、能关静音；
- 客户端不采集任何屏幕内容、不做键鼠记录，只接收文本消息；
- 令牌在手机上只存 localStorage，不需要装 App、不需要登录。

## 自测

```bash
python tools/test_remote.py
```

会起一个真的中继（子进程）+ 真的桌宠，覆盖：鉴权 401、立即送达、`in:3s` 定时、
`daily` 重排、关机期间消息补发、长轮询超时、静音时段与紧急绕过。
