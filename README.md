# AstrBot Plugin - MSLX 服务器管理

对接 [MSLX](https://github.com/MSLTeam/MSLX) Minecraft 服务器管理面板的 AstrBot 插件，通过聊天指令远程管理并控制您的 MC 服务器。

## 功能特性

本插件提供丰富的模块化指令，全面覆盖日常管理需求：

- � **系统管理**：查看面板状态、检查更新、管理 Java 环境。
- 📋 **实例管理**：启停服务器、查看详情、备份、发送控制台命令、彻底销毁实例。
- 🌐 **隧道管理**：配置和启停内网穿透（FRP）隧道。
- � **文件与模组**：浏览或删除服务端文件，管理和冻结 Mod/插件。
- 👥 **玩家管控**：查看在线玩家、白名单管理（添加/移除）、封禁（玩家/IP）。
- � **面板用户**：管理面板账户的角色及权限，分配实例控制权。
- ⏰ **定时任务**：查看及管理各实例的定时任务规则。

## 安装说明

1. 将本目录（`astrbot_plugin_mslx`）复制到 AstrBot 的 `data/plugins/` 目录下。
2. 在 AstrBot 管理面板 → 插件管理 -> 重新加载插件（或者重启 AstrBot）。
3. 进入插件配置，填写 MSLX 面板的地址及认证信息。

## 配置说明

支持两种认证方式：密码登录（主要用于管理员）和 API Key 认证（推荐）。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `mslx_url` | MSLX Daemon 的完整 URL（如 `http://127.0.0.1:1027`） | `http://127.0.0.1:1027` |
| `auth_mode` | 认证方式：`password` 或 `apikey` | `password` |
| `username` | 登录用户名（若使用 password 模式必填） | `admin` |
| `password` | 登录密码（若使用 password 模式必填） | - |
| `api_key` | API Key（若使用 apikey 模式必填，在面板设置中获取） | - |

## 指令列表

插件全面支持模块化查询，您可以直接输入 `/mslx help` 获取主帮助，或输入 `/mslx help [模块名]`（如 `/mslx help 实例`）查看具体指令详情。所有指令均以 `/mslx` 开头。

### 🔧 系统指令 (system)
| 指令 | 说明 |
|---|---|
| `/mslx status` | 查看面板系统状态 |
| `/mslx help [模块]` | 查看帮助菜单 |
| `/mslx list` | 列出所有服务器 |
| `/mslx update` | 检查并执行面板更新 |
| `/mslx java` | 罗列所有的 Java 环境版本 |

### 📋 实例指令 (instance)
| 指令 | 说明 |
|---|---|
| `/mslx info <id>` | 服务器详情 |
| `/mslx start <id>` | 启动服务器 |
| `/mslx stop <id>` | 停止服务器 |
| `/mslx restart <id>` | 重启服务器 |
| `/mslx kill <id>` | 强制结束服务器进程 |
| `/mslx backup <id>` | 触发服务器备份 |
| `/mslx backups <id>`| 查看现有备份列表 |
| `/mslx cmd <id> <命令>` | 发送控制台命令 |
| `/mslx delinstance <id> [yes]`| 彻底销毁实例 (极危) |

*( `<id>` 为服务器实例 ID，可通过 `/mslx list` 查看。)*

### 🌐 隧道指令 (frp)
| 指令 | 说明 |
|---|---|
| `/mslx frps` | 查看所有隧道 |
| `/mslx frpstart <id>` | 启动隧道 |
| `/mslx frpstop <id>` | 停止隧道 |
| `/mslx frpinfo <id>` | 查看隧道详情 |
| `/mslx frpeasy <名>...` | 快捷建隧道 |
| `/mslx frpadd <名>...` | 高级自定义创建隧道 |
| `/mslx frpdel <id>` | 删除隧道 |

### 📁 文件与模组指令 (file)
| 指令 | 说明 |
|---|---|
| `/mslx filels <id> [路径]` | 遍历目录文件列表 |
| `/mslx filedel <id> <路径>` | 物理删除服务端文件 |
| `/mslx modls <id>` | 展示模组与插件安装状况 |
| `/mslx modtoggle <id> <名>` | 切换 Mod/插件冻结状态 |

### 👥 玩家管理指令 (player)
| 指令 | 说明 |
|---|---|
| `/mslx players <id>` | 在线玩家 |
| `/mslx whitelist <id>` | 白名单列表 |
| `/mslx wladd <id> <name>`| 添加白名单 |
| `/mslx wldel <id> <name>`| 移除白名单 |
| `/mslx ban <id> <name>` | 封禁玩家 |
| `/mslx unban <id> <name>` | 解封玩家 |
| `/mslx banip <id> <ip>` | 封禁 IP |
| `/mslx unbanip <id> <ip>` | 解封 IP |

### 💻 用户管理指令 (user)
| 指令 | 说明 |
|---|---|
| `/mslx users` | 查看面板用户 |
| `/mslx adduser <账号>...`| 添加面板用户 |
| `/mslx deluser <用户ID>` | 删除面板用户 |
| `/mslx assign <用户ID> <服ID>` | 分配服务器管理权限 |
| `/mslx unassign <用户ID> <服ID>`| 移除服务器管理权限 |

### ⏰ 任务管理指令 (task)
| 指令 | 说明 |
|---|---|
| `/mslx tasks <id>` | 查看服务器定时任务 |
| `/mslx addtask <id>...` | 添加任务 |
| `/mslx deltask <任务ID>` | 删除定时任务 |

## 依赖

- `aiohttp` (自动安装)
