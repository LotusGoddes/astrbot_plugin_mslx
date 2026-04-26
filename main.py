"""AstrBot 插件 - 对接 MSLX Minecraft 服务器管理面板"""

from astrbot.api import star, logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.core.star.filter.command import GreedyStr
from .mslx_client import MSLXClient


STATUS_MAP = {
    0: "🔴 已停止",
    1: "🟡 启动中",
    2: "🟢 运行中",
    3: "🟠 停止中",
    4: "🔵 重启中",
}

HELP_CATEGORIES = {
    "system": """🔧 MSLX - 系统与通用指令
  /mslx status  - 查看面板系统状态
  /mslx help    - 查看本帮助
  /mslx list    - 列出所有服务器实例
  /mslx update  - 检查并执行面板更新
  /mslx java    - 罗列所有的 Java 环境版本""",

    "instance": """📋 MSLX - 实例管理指令
  /mslx info <id>     - 查看服务器详细信息
  /mslx start <id>    - 启动服务器
  /mslx stop <id>     - 停止服务器
  /mslx restart <id>  - 重启服务器
  /mslx kill <id>     - 强制结束服务器进程
  /mslx backup <id>   - 触发服务器备份
  /mslx backups <id>  - 查看现有备份列表
  /mslx cmd <id> <命令> - 发送控制台命令
  /mslx delinstance <id> [yes] - 极危：彻底销毁实例""",

    "frp": """🌐 MSLX - 隧道管理指令
  /mslx frps - 查看所有隧道
  /mslx frpstart <id> - 启动隧道
  /mslx frpstop <id> - 停止隧道
  /mslx frpinfo <id> - 查看隧道详情
  /mslx frpeasy <名> <Server> <SPort> <LPort> <RPort> [Token] - 快捷建隧道
  /mslx frpadd <名> <TOML> - 高级自定义创建隧道
  /mslx frpdel <id> - 删除隧道""",

    "file": """📁 MSLX - 文件与模组管控
  /mslx filels <id> [路径] - 遍历目录文件列表
  /mslx filedel <id> <路径> - 物理删除服务端文件/夹
  /mslx modls <id> - 展示模组与插件安装状况
  /mslx modtoggle <id> <文件名> - 切换 Mod/插件冻结状态""",

    "player": """👥 MSLX - 玩家管理指令
  /mslx players <id>        - 查看在线玩家
  /mslx whitelist <id>      - 查看白名单
  /mslx wladd <id> <玩家名>  - 添加白名单
  /mslx wldel <id> <玩家名>  - 移除白名单
  /mslx ban <id> <玩家名>    - 封禁玩家
  /mslx unban <id> <玩家名>  - 解封玩家
  /mslx banip <id> <IP>     - 封禁 IP
  /mslx unbanip <id> <IP>   - 解封 IP""",

    "user": """💻 MSLX - 面板用户管理
  /mslx users - 查看面板用户
  /mslx adduser <账号> <密码> <昵称> [角色] - 添加面板用户
  /mslx deluser <用户ID> - 删除面板用户
  /mslx assign <用户ID> <服务器ID> - 分配服务器管理权限
  /mslx unassign <用户ID> <服务器ID> - 移除指定服务器管理权限""",

    "task": """⏰ MSLX - 定时任务管理
  /mslx tasks <id> - 查看服务器定时任务
  /mslx addtask <id> <任务名> <cron> <类型> [命令] - 添加任务
  /mslx deltask <任务ID> - 删除定时任务"""
}

HELP_INDEX = """📦 MSLX 服务器管理插件 - 模块化帮助菜单
请使用 /mslx help [模块] 查看详细指令：

🔧 系统 - system
📋 实例 - instance
🌐 隧道 - frp
📁 文件 - file
👥 玩家 - player
💻 用户 - user
⏰ 任务 - task

💡 提示：<id> 为服务器实例 ID，通过 /mslx list 获取。"""


def _rcode(data: dict) -> int | None:
    """获取响应状态码"""
    return data.get("code") or data.get("Code")


def _rmsg(data: dict) -> str:
    """获取响应消息"""
    return data.get("message") or data.get("Message") or "未知错误"


def _rdata(data: dict):
    """获取响应数据"""
    return data.get("data") or data.get("Data")


def _format_uptime(raw) -> str:
    """将 .NET TimeSpan 格式转为中文可读时长，精确到秒

    支持格式：
    - "HH:MM:SS" → 如 "02:30:45"
    - "d.HH:MM:SS" 或 "d.HH:MM:SS.fffffff" → 如 "1.02:30:45.1234567"
    """
    if not raw or raw == "00:00:00":
        return "未运行"

    try:
        s = str(raw)
        days = 0
        # 去掉小数秒部分
        if "." in s:
            # 可能是 "d.HH:MM:SS.fff" 或 "HH:MM:SS.fff"
            parts = s.split(".")
            if len(parts) == 3:
                # "d.HH:MM:SS.fff"
                days = int(parts[0])
                s = parts[1]
            elif len(parts) == 2:
                # 判断是 "d.HH:MM:SS" 还是 "HH:MM:SS.fff"
                if ":" in parts[0]:
                    # "HH:MM:SS.fff"
                    s = parts[0]
                else:
                    # "d.HH:MM:SS"
                    days = int(parts[0])
                    s = parts[1]

        time_parts = s.split(":")
        hours = int(time_parts[0]) if len(time_parts) > 0 else 0
        minutes = int(time_parts[1]) if len(time_parts) > 1 else 0
        seconds = int(time_parts[2].split(".")[0]) if len(time_parts) > 2 else 0

        result = []
        if days > 0:
            result.append(f"{days}天")
        if hours > 0:
            result.append(f"{hours}小时")
        if minutes > 0:
            result.append(f"{minutes}分")
        result.append(f"{seconds}秒")
        return "".join(result)
    except Exception:
        return str(raw)


def _format_datetime(raw) -> str:
    """格式化系统时间为主流中文可读格式"""
    if not isinstance(raw, str) or not raw:
        return str(raw)
    try:
        s = raw.replace("T", " ")
        if len(s) >= 19:
            base = s[:19]
            parts = base.split(" ")
            if len(parts) == 2:
                date_parts = parts[0].split("-")
                time_parts = parts[1].split(":")
                if len(date_parts) == 3 and len(time_parts) == 3:
                    return f"{date_parts[0]}年{date_parts[1]}月{date_parts[2]}日 {time_parts[0]}:{time_parts[1]}:{time_parts[2]}"
        return raw
    except Exception:
        return str(raw)


class MSLXPlugin(star.Star):
    """对接 MSLX Minecraft 服务器管理面板，通过聊天指令远程管理 MC 服务器"""

    def __init__(self, context: star.Context, config=None):
        super().__init__(context, config)
        self.config = config
        self.client: MSLXClient | None = None

    def _ensure_client(self):
        """根据配置初始化或重建客户端"""
        if self.config is None:
            raise ValueError("插件配置未加载，请检查 _conf_schema.json 是否存在")

        url = self.config.get("mslx_url", "http://127.0.0.1:1027")
        auth_mode = self.config.get("auth_mode", "password")

        if auth_mode == "apikey":
            api_key = self.config.get("api_key", "")
            if not api_key:
                raise ValueError("请先在 AstrBot 管理面板中配置 MSLX API Key")
            if (
                self.client is None
                or self.client.base_url != url.rstrip("/")
                or self.client.api_key != api_key
            ):
                self.client = MSLXClient(url, api_key=api_key)
                logger.info(f"MSLX 客户端已初始化 (API Key 模式): {url}")
        else:
            username = self.config.get("username", "admin")
            password = self.config.get("password", "")
            if not password:
                raise ValueError("请先在 AstrBot 管理面板中配置 MSLX 登录密码")
            if (
                self.client is None
                or self.client.base_url != url.rstrip("/")
                or self.client.username != username
                or self.client.password != password
            ):
                self.client = MSLXClient(url, username=username, password=password)
                logger.info(f"MSLX 客户端已初始化 (密码模式): {url}")
    def _parse_id(self, text: str) -> int:
        """解析实例 ID"""
        try:
            return int(text.strip())
        except (ValueError, AttributeError):
            raise ValueError(f"无效的服务器 ID: {text}")

    # ==================== 帮助 ====================

    @filter.command("mslx help")
    async def mslx_help(self, event: AstrMessageEvent, category: str = ""):
        """查看 MSLX 插件模块化指令帮助"""
        if not category:
            event.set_result(MessageEventResult().message(HELP_INDEX))
            return
            
        # 兼容中文关键字查询
        mapping = {
            "系统": "system", "实例": "instance", "隧道": "frp",
            "文件": "file", "玩家": "player", "用户": "user", "任务": "task"
        }
        key = category.lower()
        key = mapping.get(key, key)
        
        if key in HELP_CATEGORIES:
            event.set_result(MessageEventResult().message(HELP_CATEGORIES[key]))
        else:
            event.set_result(MessageEventResult().message(f"❓ 未找到模块 '{category}'。可用的模块有：{', '.join(HELP_CATEGORIES.keys())}"))


    # ==================== 系统 ====================

    @filter.command("mslx status")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_status(self, event: AstrMessageEvent):
        """
查看 MSLX 面板系统状态"""
        try:
            self._ensure_client()
            data = await self.client.get_status()

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取状态失败: {_rmsg(data)}"))
                return

            info = _rdata(data)
            if not info:
                event.set_result(MessageEventResult().message("❌ 获取状态失败: 响应数据为空"))
                return

            sys_info = info.get("systemInfo") or info.get("SystemInfo") or {}
            text = (
                f"📊 MSLX 面板状态\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🏷️ 版本: {info.get('version', '未知')}\n"
                f"👤 用户: {info.get('user', '未知')}\n"
                f"🖥️ 系统: {sys_info.get('osType', '未知')} ({sys_info.get('osArchitecture', '')})\n"
                f"📦 运行时: {sys_info.get('netVersion', '未知')}\n"
                f"🏠 主机名: {sys_info.get('hostname', '未知')}\n"
                f"🐳 Docker: {'是' if sys_info.get('docker') else '否'}\n"
                f"🕐 服务器时间: {_format_datetime(info.get('serverTime'))}"
            )
            event.set_result(MessageEventResult().message(text))
        except Exception as e:
            logger.error(f"mslx status error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取状态失败: {e}"))

    # ==================== 实例列表 ====================

    @filter.command("mslx list")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_list(self, event: AstrMessageEvent):
        """
列出所有服务器实例"""
        try:
            self._ensure_client()
            data = await self.client.get_instance_list()

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取列表失败: {_rmsg(data)}"))
                return

            servers = _rdata(data) or []
            if not servers:
                event.set_result(MessageEventResult().message("📭 暂无服务器实例"))
                return

            lines = ["📋 服务器实例列表", "━━━━━━━━━━━━━━━"]
            for s in servers:
                status = STATUS_MAP.get(s.get("status", -1), "❓ 未知")
                online = (s.get("extra") or {}).get("onlinePlayers", 0)
                name = s.get("name", "未命名")
                sid = s.get("id", "?")
                core = s.get("core", "未知")
                lines.append(f"[{sid}] {name}\n    {status} | 核心: {core} | 在线: {online}人")

            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx list error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取列表失败: {e}"))

    # ==================== 实例详情 ====================

    @filter.command("mslx info")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_info(self, event: AstrMessageEvent, id: str = ""):
        """
查看指定服务器详细信息"""
        try:
            if not id:
                event.set_result(MessageEventResult().message("❌ 请指定服务器 ID，用法: /mslx info <id>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.get_instance_info(sid)

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取详情失败: {_rmsg(data)}"))
                return

            info = _rdata(data)
            if not info:
                event.set_result(MessageEventResult().message("❌ 获取详情失败: 响应数据为空"))
                return

            mc = info.get("mcConfig") or info.get("McConfig") or {}
            status = STATUS_MAP.get(info.get("status", -1), "❓ 未知")

            # 格式化运行时长（TimeSpan → 中文）
            uptime_raw = info.get("uptime", "00:00:00")
            uptime_str = _format_uptime(uptime_raw)

            # 获取在线玩家名单
            player_count = info.get("onlinePlayers", 0)
            player_section = f"👥 在线人数: {player_count}"
            try:
                players_data = await self.client.get_online_players(sid)
                if _rcode(players_data) == 200:
                    players = _rdata(players_data) or []
                    if players:
                        names = [p.get("name", "未知") if isinstance(p, dict) else str(p) for p in players]
                        player_section = f"👥 在线玩家 ({len(names)}人):\n" + "\n".join(f"    • {n}" for n in names)
                    else:
                        player_section = "👥 在线玩家: 无"
            except Exception:
                pass  # 获取玩家列表失败时使用数字

            text = (
                f"📋 服务器详情 [{info.get('id')}]\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📝 名称: {info.get('name', '未命名')}\n"
                f"📊 状态: {status}\n"
                f"⏱️ 运行时长: {uptime_str}\n"
                f"🎮 核心: {info.get('core', '未知')}\n"
                f"☕ Java: {info.get('java', '未知')}\n"
                f"💾 内存: {info.get('minM', '?')} - {info.get('maxM', '?')} MB\n"
                f"{player_section}\n"
                f"━━━ MC 配置 ━━━\n"
                f"🎯 难度: {mc.get('difficulty', '未知')}\n"
                f"🕹️ 模式: {mc.get('gamemode', '未知')}\n"
                f"🗺️ 地图: {mc.get('levelName', '未知')}\n"
                f"🔌 端口: {mc.get('serverPort', '未知')}\n"
                f"🌐 正版验证: {mc.get('onlineMode', '未知')}"
            )
            event.set_result(MessageEventResult().message(text))
        except Exception as e:
            logger.error(f"mslx info error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取详情失败: {e}"))

    # ==================== 实例操作 ====================

    async def _do_action(self, event: AstrMessageEvent, id_str: str, action: str, action_name: str):
        """通用实例操作"""
        try:
            if not id_str:
                event.set_result(MessageEventResult().message(f"❌ 请指定服务器 ID，用法: /mslx {action} <id>"))
                return

            self._ensure_client()
            sid = self._parse_id(id_str)
            data = await self.client.instance_action(sid, action)

            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ {action_name}成功: {_rmsg(data)}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ {action_name}失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx {action} error: {e}")
            event.set_result(MessageEventResult().message(f"❌ {action_name}失败: {e}"))

    @filter.command("mslx start")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_start(self, event: AstrMessageEvent, id: str = ""):
        """
启动服务器"""
        await self._do_action(event, id, "start", "启动")

    @filter.command("mslx stop")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_stop(self, event: AstrMessageEvent, id: str = ""):
        """
停止服务器"""
        await self._do_action(event, id, "stop", "停止")

    @filter.command("mslx restart")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_restart(self, event: AstrMessageEvent, id: str = ""):
        """
重启服务器"""
        await self._do_action(event, id, "restart", "重启")

    @filter.command("mslx kill")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_kill(self, event: AstrMessageEvent, id: str = ""):
        """
强制结束服务器进程"""
        await self._do_action(event, id, "forceExit", "强制结束")

    @filter.command("mslx backups")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_backups(self, event: AstrMessageEvent, id: str = ""):
        """
查看某个服务器的备份列表"""
        try:
            if not id:
                event.set_result(MessageEventResult().message("❌ 请指定服务器 ID，用法: /mslx backups <id>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.get_instance_backups(sid)

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取备份列表失败: {_rmsg(data)}"))
                return

            backups = _rdata(data)
            if not backups:
                event.set_result(MessageEventResult().message(f"服务器 [{sid}] 暂无备份，或备份目录不存在。"))
                return

            lines = [f"📦 服务器 [{sid}] 备份列表 ({len(backups)}个)：", "━━━━━━━━━━━━━━━"]
            for i, b in enumerate(backups[:15]):  # 最多显示15个以防过长
                # 兼容大小写字段名
                name = b.get("fileName") or b.get("FileName", "未知文件")
                size = b.get("fileSizeStr") or b.get("FileSizeStr", "未知大小")
                ctime = b.get("createTime") or b.get("CreateTime", "未知时间")
                lines.append(f"• {name}\n  大小: {size} | 时间: {ctime}")

            if len(backups) > 15:
                lines.append(f"... 还有 {len(backups) - 15} 个备份")

            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx backups error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取备份列表失败: {e}"))

    @filter.command("mslx backup")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_backup(self, event: AstrMessageEvent, id: str = ""):
        """
触发服务器备份"""
        await self._do_action(event, id, "backup", "备份")

    # ==================== 控制台命令 ====================

    @filter.command("mslx cmd")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_cmd(self, event: AstrMessageEvent, id: str, command: GreedyStr):
        """
向服务器发送控制台命令"""
        try:
            self._ensure_client()
            sid = self._parse_id(id)
            result = await self.client.send_command(sid, command)

            success = result.get("success", False)
            message = result.get("message", "未知结果")
            logs = result.get("logs", [])

            lines = []
            if success:
                lines.append(f"✅ 命令已发送到服务器 [{sid}]")
                lines.append(f"📝 {message}")
            else:
                lines.append(f"❌ 命令发送失败: {message}")

            if logs:
                lines.append("━━━ 控制台输出 ━━━")
                # 限制最多显示 20 行
                display_logs = logs[:20]
                for log in display_logs:
                    lines.append(log.rstrip())
                if len(logs) > 20:
                    lines.append(f"... 还有 {len(logs) - 20} 行输出被省略")

            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx cmd error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 发送命令失败: {e}"))

    # ==================== 定时任务 ====================

    @filter.command("mslx tasks")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_tasks(self, event: AstrMessageEvent, id: str = ""):
        """
查看某个服务器的定时任务列表"""
        try:
            if not id:
                event.set_result(MessageEventResult().message("❌ 请指定服务器 ID，用法: /mslx tasks <id>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.get_instance_tasks(sid)

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取任务列表失败: {_rmsg(data)}"))
                return

            tasks = _rdata(data) or []
            if not tasks:
                event.set_result(MessageEventResult().message(f"服务器 [{sid}] 暂无定时任务。"))
                return

            lines = [f"⏰ 服务器 [{sid}] 定时任务列表 ({len(tasks)}个)：", "━━━━━━━━━━━━━━━"]
            for t in tasks:
                t_id = t.get("id") or t.get("ID", "未知")
                name = t.get("name") or t.get("Name", "未命名")
                cron = t.get("cron") or t.get("Cron", "未知")
                t_type = t.get("type") or t.get("Type", "未知")
                payload = t.get("payload") or t.get("Payload", "")
                enable = "✅启用" if t.get("enable") or t.get("Enable") else "❌禁用"
                last_run = t.get("lastRunTime") or t.get("LastRunTime", "未运行过")
                line = f"[{t_id}] {name} ({enable})\n  规则: {cron} | 类型: {t_type}"
                if payload:
                    line += f"\n  参数: {payload}"
                line += f"\n  最后执行: {last_run}"
                lines.append(line)

            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx tasks error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取任务列表失败: {e}"))

    @filter.command("mslx addtask")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_addtask(self, event: AstrMessageEvent, id: str, name: str, cron: str, task_type: str, payload: GreedyStr = ""):
        """
添加定时任务"""
        try:
            self._ensure_client()
            sid = self._parse_id(id)
            # 允许用下划线代替空格输入cron表达式以防AstrBot解析错位，或者是引号包裹。这里做一点兼容（如果传入的cron本来是带空格的引号包裹也会匹配）
            real_cron = cron.replace("_", " ") if "_" in cron else cron
            
            data = await self.client.create_task(sid, name, real_cron, task_type, payload)
            if _rcode(data) == 200:
                task_id = _rdata(data)
                event.set_result(MessageEventResult().message(f"✅ 任务 [{name}] 创建成功！\n任务 ID: {task_id}\nCron: {real_cron}\n类型: {task_type}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 任务创建失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx addtask error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 任务创建失败: 参数不齐或解析错误。用法:\n/mslx addtask <id> <任务名> <cron表达式(可用双引号包裹)> <任务类型> [附加文本]\n附言: 若含有空格可使用双引号将Cron包裹。"))

    @filter.command("mslx deltask")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_deltask(self, event: AstrMessageEvent, task_id: str):
        """
删除定时任务"""
        try:
            self._ensure_client()
            data = await self.client.delete_task(task_id)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 任务 [{task_id}] 已删除！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 任务删除失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx deltask error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 任务删除失败: {e}"))

    # ==================== 面板用户管理 ====================

    @filter.command("mslx users")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_users(self, event: AstrMessageEvent):
        """
查看所有面板用户"""
        try:
            self._ensure_client()
            data = await self.client.get_users()

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取用户列表失败: {_rmsg(data)}"))
                return

            users = _rdata(data) or []
            if not users:
                event.set_result(MessageEventResult().message("没有找到任何用户。"))
                return

            lines = [f"👤 面板用户列表 ({len(users)}人)：", "━━━━━━━━━━━━━━━"]
            for u in users:
                uid = u.get("id") or u.get("Id", "未知")
                username = u.get("username") or u.get("Username", "未知账号")
                name = u.get("name") or u.get("Name", "未命名")
                role = "管理员" if str(u.get("role") or u.get("Role", "")) == "admin" else "普通用户"
                last_login = u.get("lastLoginTime") or u.get("LastLoginTime")
                last_login_str = _format_datetime(last_login) if last_login else "从未登录"
                lines.append(f"[{uid}] {username} ({name}) - {role}\n  最后登录: {last_login_str}")

            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx users error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取用户列表失败: {e}"))

    @filter.command("mslx adduser")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_adduser(self, event: AstrMessageEvent, username: str, password: str, name: str, role: str = "user"):
        """
添加面板用户"""
        try:
            self._ensure_client()
            data = await self.client.create_user(username, password, name, role)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 用户 [{username}] 创建成功！\n角色: {role}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 用户创建失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx adduser error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 用户创建失败: 参数错误（用户名、密码长度需 8-32 位并包含大小写数字特殊符号中的3种）。用法:\n/mslx adduser <账号> <密码> <昵称> [角色(admin/user)]"))

    @filter.command("mslx deluser")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_deluser(self, event: AstrMessageEvent, user_id: str):
        """
删除面板用户"""
        try:
            self._ensure_client()
            data = await self.client.delete_user(user_id)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 用户 [{user_id}] 已删除！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 用户删除失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx deluser error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 用户删除失败: {e}"))

    @filter.command("mslx assign")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_assign(self, event: AstrMessageEvent, user_id: str, server_id: str):
        """
给面板用户分配服务器使用权限"""
        try:
            self._ensure_client()
            sid = self._parse_id(server_id)
            users_res = await self.client.get_users()
            if _rcode(users_res) != 200:
                event.set_result(MessageEventResult().message(f"❌ 查无该用户: 获取列表异常"))
                return
            
            users = _rdata(users_res) or []
            target = next((u for u in users if str(u.get("id", "")) == user_id), None)
            if not target:
                event.set_result(MessageEventResult().message(f"❌ 查无该用户 ID: {user_id}"))
                return

            resources = list(target.get("resources") or target.get("Resources") or [])
            res_str = f"server:{sid}"
            if res_str in resources:
                event.set_result(MessageEventResult().message(f"✅ 用户已拥有该服务器的权限，无需重复分配。"))
                return
            
            resources.append(res_str)
            upd_res = await self.client.update_user(user_id, resources=resources)
            if _rcode(upd_res) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已成功赋予用户对服务器 [{sid}] 的权限！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 权限赋予失败: {_rmsg(upd_res)}"))

        except Exception as e:
            logger.error(f"mslx assign error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 权限赋予失败: {e}"))

    @filter.command("mslx unassign")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_unassign(self, event: AstrMessageEvent, user_id: str, server_id: str):
        """
移除面板用户关于某个服务器的权限"""
        try:
            self._ensure_client()
            sid = self._parse_id(server_id)
            users_res = await self.client.get_users()
            if _rcode(users_res) != 200:
                event.set_result(MessageEventResult().message(f"❌ 查无该用户: 获取列表异常"))
                return
            
            users = _rdata(users_res) or []
            target = next((u for u in users if str(u.get("id", "")) == user_id), None)
            if not target:
                event.set_result(MessageEventResult().message(f"❌ 查无该用户 ID: {user_id}"))
                return

            resources = list(target.get("resources") or target.get("Resources") or [])
            res_str = f"server:{sid}"
            if res_str not in resources:
                event.set_result(MessageEventResult().message(f"⚠️ 用户并没有拥有该服务器的权限，无法被移除。"))
                return
            
            resources.remove(res_str)
            upd_res = await self.client.update_user(user_id, resources=resources)
            if _rcode(upd_res) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已成功移除用户对服务器 [{sid}] 的权限。"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 权限移除失败: {_rmsg(upd_res)}"))

        except Exception as e:
            logger.error(f"mslx unassign error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 权限移除失败: {e}"))

    # ==================== 隧道管理 ====================

    @filter.command("mslx frps")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_frps(self, event: AstrMessageEvent):
        """查看所有内网穿透隧道"""
        try:
            self._ensure_client()
            data = await self.client.get_frp_list()
            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取隧道列表失败: {_rmsg(data)}"))
                return
            
            frps = _rdata(data) or []
            if not frps:
                event.set_result(MessageEventResult().message("没有任何配置的隧道。"))
                return

            lines = [f"🌐 面板所属隧道列表 ({len(frps)}个)：", "━━━━━━━━━━━━━━━"]
            for f in frps:
                fid = f.get("id") or f.get("Id", "未知")
                name = f.get("name") or f.get("Name", "未命名")
                service = f.get("service") or f.get("Service", "未知提供商")
                status = "✅运行中" if f.get("status") else "⛔已停止"
                lines.append(f"[{fid}] {name} ({service}) - {status}")

            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx frps error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取隧道列表失败: {e}"))

    @filter.command("mslx frpstart")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_frpstart(self, event: AstrMessageEvent, frp_id: str):
        """启动内网穿透隧道"""
        try:
            self._ensure_client()
            fid = self._parse_id(frp_id)
            data = await self.client.action_frp(fid, "start")
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 隧道 [{fid}] 启动成功！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 隧道启动失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx frpstart error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 隧道启动失败: {e}"))

    @filter.command("mslx frpstop")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_frpstop(self, event: AstrMessageEvent, frp_id: str):
        """停止内网穿透隧道"""
        try:
            self._ensure_client()
            fid = self._parse_id(frp_id)
            data = await self.client.action_frp(fid, "stop")
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 隧道 [{fid}] 已停止！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 隧道停止失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx frpstop error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 隧道停止失败: {e}"))

    @filter.command("mslx frpdel")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_frpdel(self, event: AstrMessageEvent, frp_id: str):
        """删除某个隧道配置"""
        try:
            self._ensure_client()
            fid = self._parse_id(frp_id)
            data = await self.client.delete_frp(fid)
            # MSLX的ApiResponse通常 200就是成功如果是业务错误会根据不同接口返回不同
            # CreateFrpController DeleteTunnel 可能返回200或者400
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 隧道 [{fid}] 删除成功！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 隧道删除失败: {_rmsg(data, '如隧道正在运行请先停止它')}"))
        except Exception as e:
            logger.error(f"mslx frpdel error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 隧道删除失败: {e}"))

    @filter.command("mslx frpinfo")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_frpinfo(self, event: AstrMessageEvent, frp_id: str):
        """获取隧道连接信息与代理规则"""
        try:
            self._ensure_client()
            fid = self._parse_id(frp_id)
            data = await self.client.get_frp_info(fid)
            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取详情失败: {_rmsg(data)}"))
                return

            info = _rdata(data) or {}
            proxies = info.get("proxies") or info.get("Proxies", [])
            running = info.get("isRunning") or info.get("IsRunning", False)

            status_str = "✅ 运行中" if running else "⛔ 已停止"
            lines = [f"🔍 隧道 [{fid}] 详情 ({status_str})", "━━━━━━━━━━━━━━━"]
            if not proxies:
                lines.append("无法解析代理映射 或 无代理信息。")
            else:
                for p in proxies:
                    pname = p.get("proxyName") or p.get("ProxyName", "未知映射")
                    ptype = p.get("type") or p.get("Type", "未知协议")
                    laddr = p.get("localAddress") or p.get("LocalAddress", "未知")
                    rmain = p.get("remoteAddressMain") or p.get("RemoteAddressMain", "未知")
                    rback = p.get("remoteAddressBackup") or p.get("RemoteAddressBackup", "无备用")
                    
                    lines.append(f"🔌 规则名称：{pname} ({ptype})")
                    lines.append(f"  • 本地指向：{laddr}")
                    lines.append(f"  • 远程地址：{rmain}")
                    if rback != rmain and rback and rmain != "Unknown":
                        lines.append(f"  • 备用地址：{rback}")
                    lines.append("")

            event.set_result(MessageEventResult().message("\n".join(lines).strip()))
        except Exception as e:
            logger.error(f"mslx frpinfo error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取详情失败: {e}"))

    @filter.command("mslx frpeasy")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_frpeasy(self, event: AstrMessageEvent, name: str, server_addr: str, server_port: str, local_port: str, remote_port: str, token: str = ""):
        """快捷创建一个内网穿透隧道配置"""
        try:
            self._ensure_client()
            toml_config = f'serverAddr = "{server_addr}"\nserverPort = {server_port}\n'
            if token:
                 toml_config += f'\n[auth]\ntoken = "{token}"\n'
            toml_config += f'\n[[proxies]]\nname = "Proxy-{local_port}"\ntype = "tcp"\nlocalIP = "127.0.0.1"\nlocalPort = {local_port}\nremotePort = {remote_port}\n'
            
            data = await self.client.add_frp(name, toml_config)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 快捷隧道 [{name}] 创建成功！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 快捷隧道创建失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx frpeasy error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 快捷隧道创建失败: 参数格式有误或异常。用法：\n/mslx frpeasy <隧道名> <Frp服务器地址> <服务端口> <本地应用端口> <远程开放端口> [连接密码Token(可选)]\n例如：/mslx frpeasy 本地联机 frp.net 7000 25565 12345"))

    @filter.command("mslx frpadd")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_frpadd(self, event: AstrMessageEvent, name: str, config: GreedyStr):
        """创建一个内网穿透隧道配置"""
        try:
            self._ensure_client()
            if not config.strip():
                event.set_result(MessageEventResult().message("❌ 隧道配置不能为空。"))
                return
            data = await self.client.add_frp(name, config.strip())
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 隧道 [{name}] 创建成功！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 隧道创建失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx frpadd error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 隧道创建失败: {e}"))

    # ==================== 系统进阶工具 ====================
    
    @filter.command("mslx update")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_update(self, event: AstrMessageEvent, force: str = ""):
        """检查或触发后台守护进程端自动更新"""
        try:
            self._ensure_client()
            info_data = await self.client.get_update_info()
            if _rcode(info_data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 探针请求异常: {_rmsg(info_data)}"))
                return
                
            info = _rdata(info_data) or {}
            need_update = info.get("needUpdate", False)
            cur = info.get("currentVersion", "未知")
            latest = info.get("latestVersion", "未知")
            status = info.get("status", "未知")
            log = info.get("log", "")
            
            if force == "yes":
                if not need_update:
                    event.set_result(MessageEventResult().message("当前已是最新或管理受控版本，无需强制更新。"))
                    return
                # 下发指令执行更新
                update_data = await self.client.update_daemon(True)
                if _rcode(update_data) == 200:
                    event.set_result(MessageEventResult().message("🔥 已向后端下发静默自解析更新指令！\n面板可能会出现短时间连接不上等重启中断想象，在此期间请勿强行操作服务器，稍作等待即自动完成。"))
                else:
                    event.set_result(MessageEventResult().message(f"❌ 更新发起失败：{_rmsg(update_data)}"))
                return
                
            lines = ["♻️ 面板核心服务后台 (Daemon) 探测更新"]
            lines.append("━━━━━━━━━━━━━━━")
            lines.append(f"当前版本：{cur}")
            lines.append(f"最新线上版本：{latest}")
            if status == "managed" or status == "docker":
                lines.append("❗️当前环境暂不支持从应用内一键无感热更新（这通常代表你正在使用 Docker 或专属固件），请通过源拉取镜像等形式覆盖更新。")
            elif need_update:
                lines.append(f"💡 发现新版本！更新内容与修复日志如下：\n{log[:300]}{'...' if len(log)>300 else ''}")
                lines.append("\n━━━━━━━━━━━━━━━")
                lines.append("如有需要立即在后端覆盖生效并重启框架，请回复：\n/mslx update yes")
            else:
                lines.append("✅ 您当前的守护进程核心已经是最新版噜！继续畅玩吧。")
                
            event.set_result(MessageEventResult().message("\n".join(lines)))
            
        except Exception as e:
            logger.error(f"mslx update error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 查询更新失败: {e}"))
            
    @filter.command("mslx java")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_java(self, event: AstrMessageEvent):
        """罗列出守护进程端识别到的本机 Java 环境"""
        try:
            self._ensure_client()
            data = await self.client.get_java_list()
            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 读取配置环境失败: {_rmsg(data)}"))
                return
                
            javas = _rdata(data) or []
            if not javas:
                event.set_result(MessageEventResult().message("您的服务器目前未安装或是未被面板扫描到任何 Java 环境记录。"))
                return
                
            lines = [f"☕ 面板受管 Java 列表 ({len(javas)} 条记录)", "━━━━━━━━━━━━━━━"]
            for i, j in enumerate(javas):
                path = j.get("path") or j.get("Path", "未知路径")
                version = j.get("version") or j.get("Version", "未知版本")
                major = j.get("majorVersion") or j.get("MajorVersion") or "?"
                lines.append(f"[{i+1}] Java {major} ({version})\n 📂 {path}")
                
            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx java error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 查询 Java 失败: {e}"))



    # ==================== 极限管理 ====================

    @filter.command("mslx filels")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_filels(self, event: AstrMessageEvent, id: str, path: str = ""):
        """查看指定容器路径下的文件列表"""
        try:
            self._ensure_client()
            fid = self._parse_id(id)
            data = await self.client.get_file_list(fid, path)
            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 读取文件清单失败: {_rmsg(data)}"))
                return
                
            items = _rdata(data) or []
            if not items:
                event.set_result(MessageEventResult().message("📁 当前目录下非常空虚，没有任何文件或文件夹。"))
                return
                
            lines = [f"📂 实例 [{fid}] 的目录扫描结果：{path or '/'}", "━━━━━━━━━━━━━━━"]
            for f in items:
                name = f.get("name", "未知")
                is_dir = f.get("isDirectory", False)
                size = f.get("size", 0)
                icon = "📁" if is_dir else "📄"
                size_str = "" if is_dir else f" [{round(size/1024,1)}KB]"
                lines.append(f"{icon} {name}{size_str}")
                
            event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx filels error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 浏览文件失败: {e}"))
            
    @filter.command("mslx filedel")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_filedel(self, event: AstrMessageEvent, id: str, path: str):
        """强制删除指定服务端下的文件或文件夹"""
        try:
            self._ensure_client()
            fid = self._parse_id(id)
            data = await self.client.delete_file(fid, path)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 文件目标 [{path}] 已从实例 [{fid}] 磁盘完全抹除！"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 物理擦除失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx filedel error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 删除异常: {e}"))
            
    @filter.command("mslx modls")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_modls(self, event: AstrMessageEvent, id: str):
        """列出实例的 Mod 和插件列表"""
        try:
            self._ensure_client()
            fid = self._parse_id(id)
            
            # 同时获取 mods 和 plugins
            mods_data = await self.client.get_mods_plugins(fid, "mods")
            plugins_data = await self.client.get_mods_plugins(fid, "plugins")
            
            lines = [f"🧩 实例 [{fid}] 的组件扫描：", "━━━━━━━━━━━━━━━"]
            
            def process_data(data, title):
                if _rcode(data) == 200:
                    d = _rdata(data) or {}
                    jars = d.get("jarFiles", [])
                    disables = d.get("disableJarFiles", [])
                    if jars or disables:
                        lines.append(f"📦 {title}:")
                        for j in jars: lines.append(f"  🟢 {j}")
                        for d_file in disables: lines.append(f"  🔴 {d_file}")
                
            process_data(mods_data, "模组 (Mods)")
            process_data(plugins_data, "插件 (Plugins)")
            
            if len(lines) <= 2:
                event.set_result(MessageEventResult().message("🧩 未发现任何模组或插件。"))
            else:
                lines.append("━━━━━━━━━━━━━━━\n使用 /mslx modtoggle <ID> <文件名> 切换状态 (自动识别目录)")
                event.set_result(MessageEventResult().message("\n".join(lines)))
        except Exception as e:
            logger.error(f"mslx modls error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 查询组件失败: {e}"))
            
    @filter.command("mslx modtoggle")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_modtoggle(self, event: AstrMessageEvent, id: str, file_name: str):
        """一键切换模组/插件的启用与禁用状态"""
        try:
            self._ensure_client()
            fid = self._parse_id(id)
            
            # 自动判断是 mod 还是 plugin 并决定 action
            mode = "plugins" if "plugins" in file_name.lower() or ".jar" in file_name.lower() else "mods" # 默认 fallback
            # 这里的逻辑建议是先判断后缀
            is_disabled = file_name.endswith(".disabled")
            action = "enable" if is_disabled else "disable"
            
            # 更靠谱的办法是看文件名包含路径特征，或者我们默认尝试 mods 下的行为，如果失败由用户指定
            # 但 MSLX 接口需要明确 Mode。我们简单判定：如果文件名里没写路径，我们先尝试在两个目录下寻找（通过 list 结果）
            # 或者直接让用户填 mode？为了方便，我们写个简单的探测
            
            target_mode = "mods"
            if "plugin" in file_name.lower(): target_mode = "plugins"
            
            # 调用接口
            data = await self.client.set_mod_plugin_state(fid, target_mode, action, [file_name])
            
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 操作成功：{_rmsg(data)}。重启服务器后生效。"))
            else:
                # 如果失败，尝试另一种模式
                other_mode = "plugins" if target_mode == "mods" else "mods"
                data2 = await self.client.set_mod_plugin_state(fid, other_mode, action, [file_name])
                if _rcode(data2) == 200:
                    event.set_result(MessageEventResult().message(f"✅ 操作成功：{_rmsg(data2)}。重启服务器后生效。"))
                else:
                    event.set_result(MessageEventResult().message(f"❌ 切换失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx modtoggle error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 操作异常: {e}"))
            
    @filter.command("mslx delinstance")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_delinstance(self, event: AstrMessageEvent, id: str, yes: str = ""):
        """毁灭倒计时——爆破销毁服务端容器"""
        try:
            self._ensure_client()
            fid = self._parse_id(id)
            del_files = (yes == "yes")
            
            data = await self.client.delete_instance(fid, del_files)
            if _rcode(data) == 200:
                suf = "（由于附加了终极清洗参数，它的遗留文件也都被全盘清空炸得灰飞烟灭）" if del_files else "（它的底层原始文件依然得到了安详的保留暂未清空，通过 ftp 仍可访问遗骸）"
                event.set_result(MessageEventResult().message(f"💥 轰！服务器实例 [{fid}] 及它的所有运行规则、守护参数在这一刻都被您下令强行抹除。{suf}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 核武器投送遭遇外力干预阻遏，拦截系统原话（有可能它的引擎还未停转）：{_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx delinstance error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 爆破指令引信失效抛出异常: {e}"))

    # ==================== 玩家管理 ====================

    @filter.command("mslx players")
    async def mslx_players(self, event: AstrMessageEvent, id: str = ""):
        """查看在线玩家"""
        try:
            if not id:
                event.set_result(MessageEventResult().message("❌ 请指定服务器 ID，用法: /mslx players <id>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.get_online_players(sid)

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取失败: {_rmsg(data)}"))
                return

            players = _rdata(data) or []
            if not players:
                event.set_result(MessageEventResult().message(f"📭 服务器 [{sid}] 当前无在线玩家"))
                return

            names = [p.get("name", "未知") if isinstance(p, dict) else str(p) for p in players]
            text = f"👥 服务器 [{sid}] 在线玩家 ({len(names)}人)\n━━━━━━━━━━━━━━━\n" + "\n".join(f"  • {n}" for n in names)
            event.set_result(MessageEventResult().message(text))
        except Exception as e:
            logger.error(f"mslx players error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取在线玩家失败: {e}"))

    @filter.command("mslx whitelist")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_whitelist(self, event: AstrMessageEvent, id: str = ""):
        """
查看白名单"""
        try:
            if not id:
                event.set_result(MessageEventResult().message("❌ 请指定服务器 ID，用法: /mslx whitelist <id>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.get_whitelist(sid)

            if _rcode(data) != 200:
                event.set_result(MessageEventResult().message(f"❌ 获取失败: {_rmsg(data)}"))
                return

            players = _rdata(data) or []
            if not players:
                event.set_result(MessageEventResult().message(f"📭 服务器 [{sid}] 白名单为空"))
                return

            names = [p.get("name", "未知") if isinstance(p, dict) else str(p) for p in players]
            text = f"📋 服务器 [{sid}] 白名单 ({len(names)}人)\n━━━━━━━━━━━━━━━\n" + "\n".join(f"  • {n}" for n in names)
            event.set_result(MessageEventResult().message(text))
        except Exception as e:
            logger.error(f"mslx whitelist error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 获取白名单失败: {e}"))

    @filter.command("mslx wladd")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_wladd(self, event: AstrMessageEvent, id: str = "", name: str = ""):
        """
添加白名单"""
        try:
            if not id or not name:
                event.set_result(MessageEventResult().message("❌ 用法: /mslx wladd <id> <玩家名>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.add_whitelist(sid, name)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已将 {name} 添加到服务器 [{sid}] 白名单"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 添加失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx wladd error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 添加白名单失败: {e}"))

    @filter.command("mslx wldel")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_wldel(self, event: AstrMessageEvent, id: str = "", name: str = ""):
        """
移除白名单"""
        try:
            if not id or not name:
                event.set_result(MessageEventResult().message("❌ 用法: /mslx wldel <id> <玩家名>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.remove_whitelist(sid, name)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已从服务器 [{sid}] 白名单移除 {name}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 移除失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx wldel error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 移除白名单失败: {e}"))

    @filter.command("mslx ban")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_ban(self, event: AstrMessageEvent, id: str = "", name: str = ""):
        """
封禁玩家"""
        try:
            if not id or not name:
                event.set_result(MessageEventResult().message("❌ 用法: /mslx ban <id> <玩家名>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.ban_player(sid, name)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已封禁服务器 [{sid}] 的玩家 {name}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 封禁失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx ban error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 封禁玩家失败: {e}"))

    @filter.command("mslx unban")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_unban(self, event: AstrMessageEvent, id: str = "", name: str = ""):
        """
解封玩家"""
        try:
            if not id or not name:
                event.set_result(MessageEventResult().message("❌ 用法: /mslx unban <id> <玩家名>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.unban_player(sid, name)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已解封服务器 [{sid}] 的玩家 {name}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 解封失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx unban error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 解封玩家失败: {e}"))

    @filter.command("mslx banip")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_banip(self, event: AstrMessageEvent, id: str = "", ip: str = ""):
        """
封禁 IP"""
        try:
            if not id or not ip:
                event.set_result(MessageEventResult().message("❌ 用法: /mslx banip <id> <IP>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.ban_ip(sid, ip)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已在服务器 [{sid}] 封禁 IP {ip}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 封禁 IP 失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx banip error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 封禁 IP 失败: {e}"))

    @filter.command("mslx unbanip")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mslx_unbanip(self, event: AstrMessageEvent, id: str = "", ip: str = ""):
        """
解封 IP"""
        try:
            if not id or not ip:
                event.set_result(MessageEventResult().message("❌ 用法: /mslx unbanip <id> <IP>"))
                return

            self._ensure_client()
            sid = self._parse_id(id)
            data = await self.client.unban_ip(sid, ip)
            if _rcode(data) == 200:
                event.set_result(MessageEventResult().message(f"✅ 已在服务器 [{sid}] 解封 IP {ip}"))
            else:
                event.set_result(MessageEventResult().message(f"❌ 解封 IP 失败: {_rmsg(data)}"))
        except Exception as e:
            logger.error(f"mslx unbanip error: {e}")
            event.set_result(MessageEventResult().message(f"❌ 解封 IP 失败: {e}"))

    # ==================== 生命周期 ====================

    async def terminate(self):
        """插件卸载时清理"""
        logger.info("MSLX 插件已卸载")
