#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wake_wechatsync.py — 无人值守唤醒 Wechatsync 扩展的 Service Worker

问题背景
--------
Wechatsync 的 Chrome 扩展(MV3)只在「工具栏弹窗打开」时给后台 Service Worker 发
MCP_WATCH_START，SW 才与 CLI 的 WebSocket(ws://localhost:9527)保持连接；
弹窗一关就发 MCP_WATCH_STOP，连接即断。把弹窗页当普通标签页打开也不会发
WATCH_START(组件用 is-popup 标记早退)，所以无法靠「常驻标签页」自动化。

本脚本用 Chrome DevTools 协议(CDP, 内部协议，不受浏览器外 open/osascript 限制)
直接向扩展上下文注入 MCP_WATCH_START，让 SW 进入永久保活，从而 wechatsync
无需人工开弹窗即可连接。

实现要点(相比旧版彻底修正)
--------------------------
* 旧版依赖 HTTP 写入接口打开扩展页面 —— 但 Chrome 在非 headless 下禁用了该写入
  接口(GET/POST 均 405)，故必失败。
* 新版完全不依赖 /json/new。统一走 CDP 的 Target.getTargets 找到扩展的
  Service Worker(或 popup 页面) target，再用 Target.attachToTarget(flatten)
  拿到调试会话，在扩展上下文里执行 chrome.runtime.sendMessage(WATCH_START)。
* 优先 SW：SW 上下文里 chrome.runtime 必然可用，且注入后 SW 自身进入保活循环，
  不依赖任何可见页面，最契合「无人值守定时」。
* 兜底 page：若 SW 当前未运行(getTargets 不列出)，则找/建一个扩展 popup 页面
  注入；非 headless 下 createTarget 建扩展页可能被拒，此时提示用户手动在地址栏
  打开一次 popup 页面(脚本会自动复用该页面注入，无需组件自动发消息)。

前置条件
--------
Chrome 必须以带远程调试端口且非默认 user-data-dir 启动:
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
      --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-debug-profile"
(端口可用 --port 覆盖；仅监听 127.0.0.1，本地进程才能连)

用法
----
  python3 wake_wechatsync.py [--port 9222] [--ext-id ID] [--popup src/popup/index.html]
退出码: 0=成功, 1=Chrome 未开调试端口, 2=未能注入

依赖: 仅 Python 标准库(手写最小化 WebSocket 客户端)，无需 pip install。
"""
import sys
import os
import json
import time
import struct
import socket
import base64
import argparse
import urllib.request

# 始终对 localhost 绕过任何 HTTP 代理(CDP 只在 127.0.0.1 监听)
os.environ["no_proxy"] = "127.0.0.1,localhost," + os.environ.get("no_proxy", "")
os.environ["NO_PROXY"] = os.environ["no_proxy"]


# ---------------------------------------------------------------------------
# 最小化 WebSocket 客户端(纯标准库，仅实现 CDP 所需最小子集)
# ---------------------------------------------------------------------------
class MiniWebSocket:
    """极简 WebSocket 客户端：支持握手、发送(客户端必带掩码)、接收(自动处理
    分片 / ping-pong / close)。足以驱动 CDP，不引入任何第三方依赖。"""

    def __init__(self, ws_url: str, timeout: float = 10):
        if not ws_url.startswith("ws://"):
            raise ValueError("仅支持 ws:// (本机 CDP)")
        rest = ws_url[len("ws://"):]
        host_port, _, path = rest.partition("/")
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
            port = int(port)
        else:
            host, port = host_port, 80
        path = "/" + path if path else "/"

        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b""

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ) % (path, host, port, key)
        self.sock.sendall(req.encode("ascii"))

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("WebSocket 握手失败：连接被关闭")
            resp += chunk
        header, _, rest = resp.partition(b"\r\n\r\n")
        self.buf = rest
        status_line = header.split(b"\r\n", 1)[0]
        if b"101" not in status_line:
            raise ConnectionError("WebSocket 握手失败: " + status_line.decode(errors="replace"))

    def _read_frame(self):
        while True:
            if len(self.buf) < 2:
                self._recv_some()
                continue
            b0 = self.buf[0]
            b1 = self.buf[1]
            fin = (b0 & 0x80) != 0
            opcode = b0 & 0x0F
            masked = (b1 & 0x80) != 0
            length = b1 & 0x7F
            idx = 2
            if length == 126:
                if len(self.buf) < idx + 2:
                    self._recv_some()
                    continue
                length = struct.unpack(">H", self.buf[idx:idx + 2])[0]
                idx += 2
            elif length == 127:
                if len(self.buf) < idx + 8:
                    self._recv_some()
                    continue
                length = struct.unpack(">Q", self.buf[idx:idx + 8])[0]
                idx += 8
            if masked:
                if len(self.buf) < idx + 4:
                    self._recv_some()
                    continue
                mask = self.buf[idx:idx + 4]
                idx += 4
            else:
                mask = None
            if len(self.buf) < idx + length:
                self._recv_some()
                continue
            payload = self.buf[idx:idx + length]
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            self.buf = self.buf[idx + length:]
            return fin, opcode, payload

    def _recv_some(self):
        data = self.sock.recv(65536)
        if not data:
            raise ConnectionError("WebSocket 连接被服务端关闭")
        self.buf += data

    def recv(self):
        frag_data = b""
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode == 0x8:  # close
                self.close()
                raise ConnectionError("服务端发送了 close 帧")
            elif opcode == 0x9:  # ping -> pong
                self._send(0xA, payload)
                continue
            elif opcode == 0xA:  # pong
                continue
            elif opcode == 0x0:  # 续帧
                frag_data += payload
                if fin:
                    return frag_data
            elif opcode in (0x1, 0x2):  # 文本 / 二进制
                if fin:
                    return payload
                frag_data = payload

    def _send(self, opcode: int, data: bytes):
        header = bytes([0x80 | opcode])
        length = len(data)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", length)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        try:
            self.sock.sendall(header + mask + masked)
        except OSError as e:
            raise ConnectionError("发送失败: %s" % e)

    def send(self, text: str):
        self._send(0x1, text.encode("utf-8"))

    def close(self):
        try:
            self._send(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CDP 命令封装(基于浏览器级 WebSocket，支持 sessionId 以调试具体 target)
# ---------------------------------------------------------------------------
def cdp(ws: MiniWebSocket, method: str, params=None, msg_id: int = 1,
        session_id=None, timeout: float = 10):
    """在已建立的 ws 上发一条 CDP 命令并等待其响应(按 id 匹配)。

    说明: CDP 响应一定携带与该命令相同的 id，且本封装为串行调用(同一条 ws
    上一次只等一条命令的响应)，故仅按 id 匹配即可。sessionId 仅用于「发出」
    命令时指定目标会话(flatten 调试)，不影响响应匹配 —— 否则 attachToTarget
    这类「请求无 sessionId、响应带 sessionId」的命令会误判超时。
    """
    msg = {"id": msg_id, "method": method}
    if session_id:
        msg["sessionId"] = session_id
    if params:
        msg["params"] = params
    ws.send(json.dumps(msg))

    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ws.recv()
        m = json.loads(raw)
        if m.get("id") == msg_id:
            if "error" in m:
                raise RuntimeError("CDP %s 错误: %s" % (method, m["error"]))
            return m
        # 其它消息(事件/其它会话)忽略，继续读
    raise TimeoutError("CDP %s 超时未收到响应" % method)


def get_browser_ws(port: int) -> str:
    req = urllib.request.Request("http://127.0.0.1:%d/json/version" % port,
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("webSocketDebuggerUrl"), data.get("Browser", "unknown")


def find_target(browser_ws: str, ext_id: str, want_type=None):
    """用 Target.getTargets 列出所有 target，返回与扩展匹配且类型相符的 targetInfo。"""
    ws = MiniWebSocket(browser_ws, timeout=10)
    try:
        res = cdp(ws, "Target.getTargets", msg_id=1)
        infos = (res.get("result") or {}).get("targetInfos") or []
        for t in infos:
            url = t.get("url") or ""
            if ext_id in url and (want_type is None or t.get("type") == want_type):
                return t
        return None
    finally:
        ws.close()


def create_target(browser_ws: str, ext_id: str, popup: str):
    """尝试用 CDP Target.createTarget 打开扩展 popup 页面(会激活 SW)。
    非 headless Chrome 可能拒绝创建扩展来源页面，返回 None。"""
    target = "chrome-extension://%s/%s" % (ext_id, popup)
    ws = MiniWebSocket(browser_ws, timeout=10)
    try:
        res = cdp(ws, "Target.createTarget", {"url": target}, msg_id=2)
        return (res.get("result") or {}).get("targetId")
    except Exception as e:
        sys.stderr.write("[wake] createTarget 失败(非 headless 可能禁建扩展页): %s\n" % e)
        return None
    finally:
        ws.close()


def inject_watch_start(browser_ws: str, target_id: str, label: str) -> bool:
    """附加到指定 target，在扩展上下文里发送 MCP_WATCH_START。"""
    ws = MiniWebSocket(browser_ws, timeout=10)
    try:
        att = cdp(ws, "Target.attachToTarget",
                  {"targetId": target_id, "flatten": True}, msg_id=5)
        sid = (att.get("result") or {}).get("sessionId")
        if not sid:
            sys.stderr.write("[wake] attachToTarget 未返回 sessionId\n")
            return False
        cdp(ws, "Runtime.enable", msg_id=6, session_id=sid)
        expr = "chrome.runtime.sendMessage({type:'MCP_WATCH_START'}, function(r){}); 'sent'"
        r = cdp(ws, "Runtime.evaluate",
                {"expression": expr, "returnByValue": True, "awaitPromise": False},
                msg_id=7, session_id=sid, timeout=8)
        result = r.get("result") or {}
        if "exceptionDetails" in result:
            sys.stderr.write("[wake] %s 注入 evaluate 异常: %s\n"
                            % (label, json.dumps(result["exceptionDetails"])))
            return False
        return True
    except Exception as e:
        sys.stderr.write("[wake] %s 注入失败: %s\n" % (label, e))
        return False
    finally:
        try:
            ws.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--ext-id", default="hchobocdmclopcbnibdnoafilagadion")
    ap.add_argument("--popup", default="src/popup/index.html")
    ap.add_argument("--wait", type=float, default=2.0, help="发完 WATCH_START 后等待秒数")
    args = ap.parse_args()

    # 1) 确认 Chrome 调试端口可达，并取得浏览器级 ws
    try:
        browser_ws, browser_ver = get_browser_ws(args.port)
        if not browser_ws:
            raise RuntimeError("version 接口缺少 webSocketDebuggerUrl")
        print("[wake] Chrome 调试端口就绪: %s" % browser_ver)
    except Exception as e:
        sys.stderr.write(
            "[wake] 无法连接 Chrome 调试端口 127.0.0.1:%d\n" % args.port
            + "        请先以带调试端口且非默认 user-data-dir 的方式启动 Chrome:\n"
            '        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" '
            "--remote-debugging-port=%d --user-data-dir=$HOME/chrome-debug-profile\n" % args.port
            + "        错误详情: %s\n" % e
        )
        return 1

    # 2) 优先：直接对 Service Worker 注入(最契合无人值守，无需任何可见页面)
    sw = find_target(browser_ws, args.ext_id, want_type="service_worker")
    if sw:
        print("[wake] 找到 Service Worker: %s" % sw.get("targetId"))
        if inject_watch_start(browser_ws, sw["targetId"], "ServiceWorker"):
            print("[wake] 已在 Service Worker 注入 MCP_WATCH_START，SW 进入保活")
            time.sleep(args.wait)
            print("[wake] 完成。现在 wechatsync 可无需人工开弹窗直接连接。")
            return 0
        sys.stderr.write("[wake] SW 注入失败，回退到 popup 页面路径\n")
    else:
        print("[wake] 当前未列出 Service Worker(可能处于休眠)，尝试 popup 页面路径")

    # 3) 兜底：复用或创建扩展 popup 页面注入
    page = find_target(browser_ws, args.ext_id, want_type="page")
    target_id = page["targetId"] if page else create_target(browser_ws, args.ext_id, args.popup)

    if not target_id:
        sys.stderr.write(
            "[wake] 无法自动创建扩展页面(非 headless 下 Chrome 可能禁用)。\n"
            "        请在你带调试端口的 Chrome 地址栏手动打开一次:\n"
            "          chrome-extension://%s/%s\n"
            "        并保持在后台(可钉住标签页)，然后重跑本脚本(会自动复用注入)。\n"
            % (args.ext_id, args.popup)
        )
        return 2

    if page:
        print("[wake] 复用已有扩展页面: %s" % page.get("url"))
    else:
        print("[wake] 已创建扩展页面 targetId=%s" % target_id)

    if inject_watch_start(browser_ws, target_id, "popup页面"):
        print("[wake] 已在扩展页面注入 MCP_WATCH_START，SW 进入保活")
        time.sleep(args.wait)
        print("[wake] 完成。现在 wechatsync 可无需人工开弹窗直接连接。")
        return 0

    sys.stderr.write("[wake] 注入失败，请检查扩展是否正确安装并启用 MCP。\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
