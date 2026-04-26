"""MSLX REST API 异步客户端封装"""

import asyncio
import aiohttp
import json
import time
from astrbot.api import logger

# SignalR JSON 协议消息分隔符
SIGNALR_SEPARATOR = "\x1e"


class MSLXClient:
    """MSLX Daemon REST API 客户端

    支持两种认证方式：
    1. 用户名+密码登录获取 Token（x-user-token）
    2. API Key 认证（x-api-key），无需登录
    """

    def __init__(self, base_url: str, username: str = "", password: str = "", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_key = api_key
        self._token: str | None = None
        self._token_time: float = 0
        self._token_ttl = 20 * 3600

    @property
    def _use_api_key(self) -> bool:
        return bool(self.api_key)

    async def _ensure_token(self):
        if self._use_api_key:
            return
        if self._token and (time.time() - self._token_time) < self._token_ttl:
            return
        await self._login()

    async def _login(self):
        url = f"{self.base_url}/api/auth/login"
        payload = {"username": self.username, "password": self.password}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    code = data.get("code") or data.get("Code")
                    if code == 200:
                        token = (data.get("data") or data.get("Data") or {}).get("token")
                        if token:
                            self._token = token
                            self._token_time = time.time()
                            logger.info("MSLX 登录成功")
                        else:
                            raise Exception("MSLX 登录响应中未找到 token 字段")
                    else:
                        msg = data.get("message") or data.get("Message") or "未知错误"
                        raise Exception(f"MSLX 登录失败: {msg}")
        except aiohttp.ClientError as e:
            raise Exception(f"MSLX 连接失败: {e}")

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._use_api_key:
            headers["x-api-key"] = self.api_key
        elif self._token:
            headers["x-user-token"] = self._token
        return headers

    def _auth_query(self) -> str:
        """构建认证查询参数（用于 SignalR 连接）"""
        if self._use_api_key:
            return f"x-api-key={self.api_key}"
        elif self._token:
            return f"x-user-token={self._token}"
        return ""

    async def _get(self, path: str, params: dict | None = None) -> dict:
        await self._ensure_token()
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers(), params=params,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    return await resp.json()
        except aiohttp.ClientError as e:
            return {"code": -1, "message": f"连接 MSLX 失败: {e}"}

    async def _get_bytes(self, path: str, params: dict | None = None) -> bytes:
        await self._ensure_token()
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers(), params=params,
                                       timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    return b""
        except aiohttp.ClientError:
            return b""

    async def _post(self, path: str, payload: dict | None = None) -> dict:
        await self._ensure_token()
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self._headers(), json=payload,
                                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    return await resp.json()
        except aiohttp.ClientError as e:
            return {"code": -1, "message": f"连接 MSLX 失败: {e}"}

    async def _delete(self, path: str, params: dict | None = None) -> dict:
        await self._ensure_token()
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=self._headers(), params=params,
                                          timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    return await resp.json()
        except aiohttp.ClientError as e:
            return {"code": -1, "message": f"连接 MSLX 失败: {e}"}

    # ==================== 系统 ====================

    async def ping(self) -> dict:
        url = f"{self.base_url}/api/ping"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return await resp.json()
        except aiohttp.ClientError as e:
            return {"code": -1, "message": f"无法连接到 MSLX: {e}"}

    async def get_status(self) -> dict:
        return await self._get("/api/status")

    # ==================== 实例管理 ====================

    async def get_instance_list(self) -> dict:
        return await self._get("/api/instance/list")

    async def get_instance_info(self, instance_id: int) -> dict:
        return await self._get("/api/instance/info", {"id": instance_id})

    async def instance_action(self, instance_id: int, action: str) -> dict:
        return await self._post("/api/instance/action", {"id": instance_id, "action": action})

    async def start_instance(self, instance_id: int) -> dict:
        return await self.instance_action(instance_id, "start")

    async def stop_instance(self, instance_id: int) -> dict:
        return await self.instance_action(instance_id, "stop")

    async def restart_instance(self, instance_id: int) -> dict:
        return await self.instance_action(instance_id, "restart")

    async def kill_instance(self, instance_id: int) -> dict:
        return await self.instance_action(instance_id, "forceExit")

    async def backup_instance(self, instance_id: int) -> dict:
        return await self.instance_action(instance_id, "backup")

    async def get_instance_backups(self, instance_id: int) -> dict:
        """获取实例的备份列表"""
        return await self._get(f"/api/instance/backups/{instance_id}")

    # ==================== 定时任务 ====================

    async def get_instance_tasks(self, instance_id: int) -> dict:
        return await self._get(f"/api/instance/tasks/list/{instance_id}")

    async def create_task(self, instance_id: int, name: str, cron: str, task_type: str, payload: str = "") -> dict:
        req = {
            "instanceId": instance_id,
            "name": name,
            "cron": cron,
            "type": task_type,
            "payload": payload,
            "enable": True
        }
        return await self._post("/api/instance/tasks/create", req)

    async def delete_task(self, task_id: str) -> dict:
        return await self._post(f"/api/instance/tasks/delete/{task_id}")

    # ==================== 用户管理 ====================

    async def get_users(self) -> dict:
        return await self._get("/api/admin/user/list")

    async def create_user(self, username: str, password: str, name: str, role: str = "user", resources: list = None) -> dict:
        if resources is None:
            resources = []
        req = {
            "username": username,
            "password": password,
            "name": name,
            "role": role,
            "resources": resources
        }
        return await self._post("/api/admin/user/create", req)

    async def update_user(self, user_id: str, **kwargs) -> dict:
        req = {}
        for k in ["name", "avatar", "password", "role", "resources"]:
            if k in kwargs:
                req[k] = kwargs[k]
        if "reset_api_key" in kwargs:
            req["resetApiKey"] = kwargs["reset_api_key"]
        return await self._post(f"/api/admin/user/update/{user_id}", req)

    async def delete_user(self, user_id: str) -> dict:
        return await self._post(f"/api/admin/user/delete/{user_id}")

    # ==================== Frp 隧道管理 ====================

    async def get_frp_list(self) -> dict:
        return await self._get("/api/frp/list")
        
    async def get_frp_info(self, frp_id: int) -> dict:
        return await self._get(f"/api/frp/info?id={frp_id}")

    async def action_frp(self, frp_id: int, action: str) -> dict:
        return await self._post("/api/frp/action", {"id": frp_id, "action": action})

    async def add_frp(self, name: str, config: str, format: str = "toml", provider: str = "custom") -> dict:
        req = {
            "name": name,
            "provider": provider,
            "format": format,
            "config": config
        }
        return await self._post("/api/frp/add", req)

    async def delete_frp(self, frp_id: int) -> dict:
        return await self._post("/api/frp/delete", {"id": frp_id})

    # ==================== 进阶管理：更新、文件、Java、渲染 ====================

    async def get_update_info(self) -> dict:
        return await self._get("/api/update/info")

    async def update_daemon(self, auto_restart: bool = True) -> dict:
        return await self._post(f"/api/update?autoRestart={'true' if auto_restart else 'false'}")

    async def get_java_list(self, refresh: bool = False) -> dict:
        return await self._get(f"/api/java/list?refresh={'true' if refresh else 'false'}")

    # ==================== 终极进阶管理：文件、模组、危险操作 ====================

    async def get_file_list(self, instance_id: int, path: str = "") -> dict:
        p = f"?path={path}" if path else ""
        return await self._get(f"/api/files/instance/{instance_id}/lists{p}")
        
    async def delete_file(self, instance_id: int, path: str) -> dict:
        return await self._post(f"/api/files/instance/{instance_id}/delete", {
            "paths": [path]
        })

    async def get_mods_plugins(self, instance_id: int, mode: str = "mods") -> dict:
        return await self._get(f"/api/files/pm/instance/{instance_id}/list?mode={mode}")

    async def set_mod_plugin_state(self, instance_id: int, mode: str, action: str, filenames: list) -> dict:
        return await self._post(f"/api/files/pm/instance/{instance_id}/set", {
            "mode": mode,
            "action": action,
            "targets": filenames
        })

    async def delete_instance(self, instance_id: int, delete_files: bool = False) -> dict:
        return await self._post("/api/instance/delete", {
            "id": instance_id,
            "deleteFiles": delete_files
        })

    # ==================== 控制台命令 ====================

    async def send_command(self, instance_id: int, command: str) -> dict:
        """通过 SignalR Hub 向实例发送控制台命令并捕获返回输出

        流程：negotiate → WebSocket → 握手 → JoinGroup（忽略历史日志）
              → SendCommand → 监听 ReceiveLog 收集输出 → LeaveGroup → 断开
        """
        await self._ensure_token()
        hub_path = "/api/hubs/instanceControlHub"
        auth_query = self._auth_query()

        try:
            async with aiohttp.ClientSession() as session:
                # 1. Negotiate
                negotiate_url = f"{self.base_url}{hub_path}/negotiate?negotiateVersion=1&{auth_query}"
                async with session.post(negotiate_url, headers=self._headers(),
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return {"success": False, "message": f"SignalR negotiate 失败: HTTP {resp.status}", "logs": []}
                    negotiate_data = await resp.json()

                conn_token = negotiate_data.get("connectionToken", "")
                if not conn_token:
                    return {"success": False, "message": "SignalR negotiate 未返回 connectionToken", "logs": []}

                # 2. WebSocket 连接
                ws_scheme = "ws" if self.base_url.startswith("http://") else "wss"
                base_host = self.base_url.replace("http://", "").replace("https://", "")
                ws_url = f"{ws_scheme}://{base_host}{hub_path}?id={conn_token}&{auth_query}"

                async with session.ws_connect(ws_url, timeout=10) as ws:
                    # 3. SignalR 握手
                    handshake = json.dumps({"protocol": "json", "version": 1}) + SIGNALR_SEPARATOR
                    await ws.send_str(handshake)

                    hs_resp = await ws.receive(timeout=5)
                    hs_text = hs_resp.data if hasattr(hs_resp, 'data') else str(hs_resp)
                    if isinstance(hs_text, str) and '"error"' in hs_text:
                        return {"success": False, "message": f"SignalR 握手失败: {hs_text}", "logs": []}

                    # 4. JoinGroup - 加入控制台日志组
                    join_msg = json.dumps({
                        "type": 1,
                        "invocationId": "join",
                        "target": "JoinGroup",
                        "arguments": [instance_id]
                    }) + SIGNALR_SEPARATOR
                    await ws.send_str(join_msg)

                    # 消费 JoinGroup 后推送的历史日志（忽略）
                    try:
                        while True:
                            msg = await asyncio.wait_for(ws.receive(), timeout=1)
                            if msg.type != aiohttp.WSMsgType.TEXT:
                                break
                            # 检查是否已无更多历史日志（收到 Ping 或其他非 ReceiveLog 消息）
                            has_log = False
                            for part in msg.data.split(SIGNALR_SEPARATOR):
                                part = part.strip()
                                if not part:
                                    continue
                                try:
                                    data = json.loads(part)
                                except json.JSONDecodeError:
                                    continue
                                if data.get("type") == 1 and data.get("target") == "ReceiveLog":
                                    has_log = True
                                elif data.get("type") == 6:
                                    await ws.send_str(json.dumps({"type": 6}) + SIGNALR_SEPARATOR)
                            if not has_log:
                                break
                    except asyncio.TimeoutError:
                        pass  # 历史日志接收完毕

                    # 5. 发送 SendCommand
                    invoke_msg = json.dumps({
                        "type": 1,
                        "invocationId": "cmd",
                        "target": "SendCommand",
                        "arguments": [instance_id, command]
                    }) + SIGNALR_SEPARATOR
                    await ws.send_str(invoke_msg)

                    # 6. 收集 CommandResult 和 ReceiveLog
                    cmd_result = {"success": False, "message": "未收到响应"}
                    logs = []
                    try:
                        deadline = asyncio.get_event_loop().time() + 3
                        got_result = False
                        while asyncio.get_event_loop().time() < deadline:
                            remaining = deadline - asyncio.get_event_loop().time()
                            if remaining <= 0:
                                break
                            msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                for part in msg.data.split(SIGNALR_SEPARATOR):
                                    part = part.strip()
                                    if not part:
                                        continue
                                    try:
                                        data = json.loads(part)
                                    except json.JSONDecodeError:
                                        continue
                                    if data.get("type") == 1:
                                        target = data.get("target", "")
                                        if target == "CommandResult":
                                            args = data.get("arguments", [{}])
                                            if args:
                                                cmd_result = args[0]
                                            got_result = True
                                        elif target == "ReceiveLog":
                                            args = data.get("arguments", [])
                                            if args:
                                                log_text = args[0] if isinstance(args[0], str) else str(args[0])
                                                logs.append(log_text)
                                    elif data.get("type") == 6:
                                        await ws.send_str(json.dumps({"type": 6}) + SIGNALR_SEPARATOR)
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                            # 拿到 CommandResult 后再等一小段时间收集日志
                            if got_result and (asyncio.get_event_loop().time() > deadline - 1):
                                break
                    except asyncio.TimeoutError:
                        if not cmd_result.get("success"):
                            cmd_result = {"success": True, "message": "命令已发送（等待响应超时）"}

                    # 7. LeaveGroup
                    try:
                        leave_msg = json.dumps({
                            "type": 1,
                            "target": "LeaveGroup",
                            "arguments": [instance_id]
                        }) + SIGNALR_SEPARATOR
                        await ws.send_str(leave_msg)
                    except Exception:
                        pass

                    cmd_result["logs"] = logs
                    return cmd_result

        except aiohttp.ClientError as e:
            return {"success": False, "message": f"连接 MSLX 失败: {e}", "logs": []}
        except Exception as e:
            return {"success": False, "message": f"发送命令失败: {e}", "logs": []}

    # ==================== 玩家管理 ====================

    async def get_online_players(self, instance_id: int) -> dict:
        return await self._get(f"/api/instance/players/online/{instance_id}")

    async def get_whitelist(self, instance_id: int) -> dict:
        return await self._get(f"/api/instance/players/whitelist/{instance_id}")

    async def add_whitelist(self, instance_id: int, name: str) -> dict:
        return await self._post(f"/api/instance/players/whitelist/add/{instance_id}", {"name": name})

    async def remove_whitelist(self, instance_id: int, name: str) -> dict:
        return await self._post(f"/api/instance/players/whitelist/remove/{instance_id}", {"name": name})

    async def get_banned_players(self, instance_id: int) -> dict:
        return await self._get(f"/api/instance/players/banplayer/{instance_id}")

    async def ban_player(self, instance_id: int, name: str, reason: str = "") -> dict:
        payload = {"name": name}
        if reason:
            payload["reason"] = reason
        return await self._post(f"/api/instance/players/banplayer/add/{instance_id}", payload)

    async def unban_player(self, instance_id: int, name: str) -> dict:
        return await self._post(f"/api/instance/players/banplayer/remove/{instance_id}", {"name": name})

    async def get_banned_ips(self, instance_id: int) -> dict:
        return await self._get(f"/api/instance/players/banip/{instance_id}")

    async def ban_ip(self, instance_id: int, ip: str, reason: str = "") -> dict:
        payload = {"ip": ip}
        if reason:
            payload["reason"] = reason
        return await self._post(f"/api/instance/players/banip/add/{instance_id}", payload)

    async def unban_ip(self, instance_id: int, ip: str) -> dict:
        return await self._post(f"/api/instance/players/banip/remove/{instance_id}", {"ip": ip})
