# Star Office UI — Agent 指南

> 本文件面向 AI 编程助手（Agent）。如果你第一次接触这个项目，请通读本文件后再动手改代码。

---

## 项目概述

**Star Office UI** 是一个像素风格的 AI 办公室看板（Pixel Office Dashboard）。它将 AI Agent 的实时工作状态可视化：Agent 在不同的工作状态下会走到办公室的不同区域（休息区沙发、工作区办公桌、Bug 区）。

项目分为两部分：
1. **主仓库**（`~/projects/Star-Office-UI`）：包含后端、前端、脚本、文档等所有代码和资产。
2. **macOS App Bundle**（`/Applications/Star Office.app`）：只是一个启动器包装壳，负责启动 OpenClaw Gateway + Star-Office-UI 后端，并自动打开浏览器。它本身不包含业务代码。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.10+、Flask 3.0.2、Pillow 10.4.0、python-telegram-bot 21.6、requests>=2.31.0 |
| 前端 | 原生 HTML/CSS/JS、Phaser 3.80.1（像素渲染引擎） |
| 桌面壳 | **Tauri v2**（Rust，透明窗口，位于 `desktop-pet/`）；另有旧版 Electron 壳（`electron-shell/`） |
| 可选依赖 | ImageMagick (`magick`) 或 ffmpeg（用于动图转精灵表） |
| 生图 | Gemini API（`scripts/gemini_image_generate.py`，运行在独立虚拟环境 `../skills/gemini-image-generate/.venv`） |
| 包管理 | `uv` 支持（`pyproject.toml` + `uv.lock`），也兼容 `pip` |

> **注意**：代码中大量使用了 Python 3.10 的 `X | Y` union type 语法，**不支持 Python 3.9 及以下**。

---

## 项目结构

```text
Star-Office-UI/
├── backend/                    # Flask 后端
│   ├── app.py                  # 主服务（~2100 行），包含所有 API 路由
│   ├── requirements.txt        # flask==3.0.2, pillow==10.4.0, python-telegram-bot==21.6, requests>=2.31.0
│   ├── run.sh                  # 启动脚本（自动加载 .env，优先使用 .venv/bin/python）
│   ├── security_utils.py       # 生产模式检测、密钥/密码强度校验
│   ├── memo_utils.py           # 昨日小记提取、内容脱敏
│   ├── store_utils.py          # JSON 文件读写（agents-state、asset-positions、runtime-config、join-keys）
│   ├── claw_office_bridge.py   # OpenClaw 状态推送桥接脚本
│   └── telegram_bot.py         # Telegram Bot（俄语界面，集成 DeepSeek API）
├── frontend/                   # 前端页面与美术资产
│   ├── index.html              # 主页面（内嵌 CSS/JS，~4900 行）
│   ├── game.js                 # Phaser 游戏逻辑（WebP 检测、动画、状态映射）
│   ├── layout.js               # 布局与 UI 交互（坐标、depth、多语切换）
│   ├── join.html               # 访客 Agent 加入页面
│   ├── invite.html             # 人类邀请说明页面
│   ├── electron-standalone.html # Electron/Tauri 专用页面快照
│   ├── vendor/phaser-3.80.1.min.js
│   └── *.webp / *.png          # 像素资产（角色、场景、装饰）
├── desktop-pet/                # Tauri v2 桌面宠物版（透明窗口）
│   ├── package.json            # npm scripts: dev / build（使用 @tauri-apps/cli ^2）
│   ├── README.md               # Tauri 开发说明
│   ├── STATE_API.md            # 状态 API 说明
│   └── src-tauri/              # Rust + Tauri v2 配置
├── electron-shell/             # 旧版 Electron 桌面壳（Electron ^40.6.1）
├── scripts/
│   ├── smoke_test.py           # 部署后冒烟测试
│   ├── security_check.py       # 安全预检（密钥强度、git 追踪敏感文件、API key 模式扫描）
│   └── gemini_image_generate.py # 生图脚本（需独立 .venv）
├── launchd/                    # macOS launchd 自动启动配置
│   ├── install-launchd.sh      # 安装脚本（注册 Gateway + Backend + Telegram Bot）
│   ├── uninstall-launchd.sh
│   └── com.staroffice.*.plist  # 三个服务的 plist 模板
├── docs/                       # 更新日志、截图、发布检查清单
├── assets/                     # 静态资产、参考图、bg-history、home-favorites
├── set_state.py                # 命令行状态切换脚本（Agent 调用）
├── office-agent-push.py        # 访客 Agent 远程推送脚本
├── pyproject.toml              # uv/pip 项目元数据（仅声明依赖，无构建步骤）
├── uv.lock                     # uv 锁定文件
├── state.sample.json           # 状态文件模板
├── join-keys.sample.json       # Join Key 模板（首次启动时自动生成 join-keys.json）
├── .env.example                # 生产环境变量模板
├── healthcheck.sh              # systemd 健康检查 + 自动重启示例
├── SKILL.md                    # 面向 OpenClaw 的部署 Skill
└── README.md / README.en.md / README.ja.md  # 用户文档（中英日）
```

---

## 构建与运行命令

### 1. 安装依赖

```bash
cd ~/projects/Star-Office-UI
python3 -m pip install -r backend/requirements.txt
# 或若使用 uv：
# uv venv .venv && uv pip install -r backend/requirements.txt
```

### 2. 初始化状态文件

```bash
cp state.sample.json state.json
```

### 3. 启动后端

```bash
# 方式 A：直接启动
cd backend && python3 app.py

# 方式 B：通过 run.sh（自动加载 .env、使用 .venv/bin/python）
cd backend && bash run.sh
```

默认监听 `http://0.0.0.0:19000`。可通过环境变量 `STAR_BACKEND_PORT` 修改端口。

### 4. 启动桌面宠物版（Tauri）

```bash
cd desktop-pet
npm install
npm run dev   # 会自动拉起 Python 后端
```

> ⚠️ 注意：README.md 中写的 "Electron 桌面宠物" 是旧描述，实际 `desktop-pet/` 已是 **Tauri v2**。

### 5. 验证部署

```bash
python3 scripts/smoke_test.py --base-url http://127.0.0.1:19000
python3 scripts/security_check.py
```

### 6. 手动切换状态（体验）

```bash
python3 set_state.py writing "正在整理文档"
python3 set_state.py idle "待命中"
```

---

## 后端架构与关键模块

### `backend/app.py`

这是唯一的主服务文件，包含所有 Flask 路由。核心职责：

- **静态文件服务**：从 `frontend/` 目录提供 HTML、JS、图片资产。
- **状态管理**：读写 `state.json`（主 Agent 状态）、`agents-state.json`（多 Agent 状态）。
- **多 Agent 协作**：`join-agent`、`agent-push`、`leave-agent`、`agent-approve`、`agent-reject`。访客通过 `joinKey` 加入，受并发上限（默认 3 人/key）和过期时间控制。
- **资产管理系统**：侧边栏上传/替换美术资产，支持动图自动转精灵表（GIF/WEBP → spritesheet）。所有资产操作需通过 `ASSET_DRAWER_PASS` 验证（基于 Flask session）。
- **Home Favorites**：收藏当前底图（上限 30 张），支持应用/删除/列表。
- **AI 生图**：异步后台生成办公室背景（调用 `scripts/gemini_image_generate.py`），前端轮询进度，避免 Cloudflare 524 超时。支持 `fast` / `quality` 两档速度模式，带模型多级回退。
- **昨日小记**：从 `../memory/YYYY-MM-DD.md` 读取最近一天的工作记录，脱敏后返回。
- **缓存策略**：HTML/API 强制 no-cache；静态资源（2xx）长期缓存，404 不缓存。
- **首页背景轮换**：默认关闭（`AUTO_ROTATE_HOME_ON_PAGE_OPEN` 默认 `0`），避免首屏被磁盘复制拖慢。

### `backend/security_utils.py`

- `is_production_mode()`：`STAR_OFFICE_ENV=production` 或 `FLASK_ENV=production` 时返回 True。
- `is_strong_secret()`：长度 >= 24，且不含 `change-me`/`dev`/`test`/`example`/`default` 等弱标记。
- `is_strong_drawer_pass()`：不能是默认 `1234`，长度 >= 8。

**生产模式启动时**，如果密钥或密码不满足强度要求，服务会直接抛出 `RuntimeError` 拒绝启动。

### `backend/store_utils.py`

所有持久化数据的 JSON 读写封装：
- `load/save_agents_state`
- `load/save_asset_positions`
- `load/save_asset_defaults`
- `load/save_runtime_config`（Gemini API key 和模型配置，文件权限自动设为 `0o600`）
- `load/save_join_keys`
- `_normalize_user_model()`：将 provider 模型名映射到 `nanobanana-pro` / `nanobanana-2`

### `backend/memo_utils.py`

- `sanitize_content()`：脱敏处理（OpenID、路径、IP、邮箱、手机号）。
- `extract_memo_from_file()`：从 markdown 提取要点，截断 + 添加随机语录。

### `backend/telegram_bot.py`

独立的 Telegram Bot，俄语界面。功能：查看状态、切换状态、查看 Agent 列表、读取昨日小记、与 DeepSeek API 聊天、检查 OpenClaw Gateway 健康。默认 webhook/port 25700，支持 long polling fallback。通过 PID 文件防止重复启动。

### `backend/claw_office_bridge.py`

OpenClaw 状态桥接脚本。自动 join 办公室并定时推送 `idle` 状态，SIGTERM/SIGINT 时自动 leave。

---

## 前端架构

### `frontend/game.js`

Phaser 3 游戏主逻辑：
- WebP 支持检测（canvas + image fallback）。
- 角色状态 → 区域坐标映射（依赖 `layout.js` 的 `LAYOUT.areas`）。
- 动画系统：idle/walking 状态机，帧同步避免闪烁。
- 气泡、进度条、多 Agent 渲染。

### `frontend/layout.js`

布局与层级配置中心：
- 所有坐标、depth、资源路径统一管理。
- 多语言切换逻辑（CN / EN / JP）。
- 移动端侧边栏适配（遮罩层、body 滚动锁定、`100dvh`、`overscroll-behavior: contain`）。

### `frontend/index.html`

主页面（~4900 行，内嵌 CSS/JS）。启动时被后端加载到 `_INDEX_HTML_CACHE` 并替换 `{{VERSION_TIMESTAMP}}` 实现缓存刷新。修改后必须重启后端才能生效。

---

## 状态系统

### 6 种标准状态（后端 canonical）

| 状态 | 办公室区域 | 含义 |
|------|-----------|------|
| `idle` | breakroom（休息区/沙发） | 待命 / 任务完成 |
| `writing` | writing（工作区/办公桌） | 写代码 / 写文档 |
| `researching` | writing | 搜索 / 调研 |
| `executing` | writing | 执行命令 / 跑任务 |
| `syncing` | writing | 同步数据 / 推送 |
| `error` | error（Bug 区） | 报错 / 异常排查 |

> 后端 `VALID_AGENT_STATES = frozenset({"idle", "writing", "researching", "executing", "syncing", "error"})` 是校验的唯一来源。`normalize_agent_state()` 会把别名（`working`/`busy`/`write` → `writing`，`run`/`running`/`execute`/`exec` → `executing` 等）映射进来；**未知状态一律回退到 `idle`**。

### 重要不一致

`set_state.py` 的 `VALID_STATES` 列表包含 `receiving` 和 `replying`，但这两个状态**不在后端 canonical 集合中**。通过 `set_state.py` 写入后，后端读取时会因 `normalize_agent_state()` 未知而将其视为 `idle`。若需支持这两个状态，必须同步修改 `backend/app.py` 的 `VALID_AGENT_STATES`、`WORKING_STATES`、`STATE_TO_AREA_MAP` 以及 `normalize_agent_state()`。

### 状态持久化

- 主 Agent 状态保存在项目根目录的 `state.json`。
- 多 Agent 状态保存在 `agents-state.json`。
- 后端有**自动 idle 机制**：如果工作状态（`writing`/`researching`/`executing`）超过 `ttl_seconds`（默认 300s）未更新，会自动回退到 `idle`。

### Agent 状态同步约定

OpenClaw 或其他外部 Agent 通常按以下约定调用：

```bash
# 接到任务前
python3 set_state.py writing "正在处理 XX 任务"

# 任务完成后
python3 set_state.py idle "待命中"
```

---

## 开发约定与代码风格

1. **Python 版本**：严格使用 Python 3.10+ 特性（如 `X | Y` union types、`match/case` 可用但项目中未大量使用）。
2. **字符串编码**：所有 JSON 读写使用 `encoding="utf-8"`，`ensure_ascii=False`。
3. **路径处理**：后端使用 `os.path` 和 `pathlib.Path`，**禁止硬编码绝对路径**。项目根目录通过 `__file__` 相对计算。
4. **错误处理**：API 返回统一格式 `{"ok": bool, ...}` 或 `{"status": "ok/error", ...}`。异常捕获后返回 500 并附带错误信息。
5. **注释语言**：后端代码注释以中文为主，Telegram Bot 以俄语为主，README 支持中英日三语。
6. **资产命名**：美术资产使用 kebab-case 或 snake_case，精灵表后缀常带 `-grid` 或 `-spritesheet`。
7. **缓存版本控制**：静态资源 URL 带 `?v={{VERSION_TIMESTAMP}}`，由后端在启动时注入到 `index.html`。
8. **虚拟环境**：`backend/run.sh` 硬编码使用 `.venv/bin/python`。`desktop-pet` 的 Tauri 启动逻辑也优先寻找 `.venv`。

---

## 测试策略

本项目没有使用 pytest/unittest 等框架编写单元测试，而是采用**脚本化验收测试**：

- **`scripts/smoke_test.py`**：非破坏性冒烟测试。检查 `GET /`、`/health`、`/status`、`/agents`、`/yesterday-memo` 等端点是否返回 200，并探测 `POST /set_state` 是否正常工作。支持 `SMOKE_AUTH_BEARER` 环境变量。
- **`scripts/security_check.py`**：安全预检。检查环境变量密钥强度、git 是否追踪了敏感运行时文件（`runtime-config.json`、`join-keys.json` 等）、追踪文件中是否有 API key 模式（Google/Gemini、sk-*、AWS）。

**运行方式**：

```bash
python3 scripts/smoke_test.py --base-url http://127.0.0.1:19000
python3 scripts/security_check.py
```

---

## 部署与进程管理

### macOS（推荐）

使用 `launchd/` 目录下的脚本实现开机自启：

```bash
bash launchd/install-launchd.sh
```

这会注册三个服务：
- `com.staroffice.gateway` — OpenClaw Gateway（端口 18790）
- `com.staroffice.backend` — Star Office UI 后端（端口 19000）
- `com.staroffice.telegram` — Telegram Bot

日志位置：
- `/tmp/openclaw-gateway.log`
- `/tmp/staroffice-backend.log`
- `/tmp/staroffice-telegram.log`

### Linux / 其他

直接通过 systemd 或 pm2 管理 `backend/app.py`。`healthcheck.sh` 提供了一个 systemd 健康检查 + 自动重启的示例（需配合 systemd timer 使用）。

### 公网访问

推荐使用 Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://127.0.0.1:19000
```

---

## 安全配置要点

生产环境部署前，必须完成以下配置：

1. **复制并填写 `.env`**：
   ```bash
   cp .env.example .env
   ```
   必须设置：
   - `STAR_OFFICE_ENV=production`
   - `FLASK_SECRET_KEY`（>=24 位随机字符串）
   - `ASSET_DRAWER_PASS`（不能是默认 `1234`，>=8 位）
   - 可选：`GEMINI_API_KEY`、`GEMINI_MODEL`

2. **避免将运行时文件提交到 git**：`.gitignore` 已排除 `state.json`、`agents-state.json`、`runtime-config.json`、`join-keys.json`、`* .log`、`.env` 等。

3. **runtime-config.json 权限**：后端在保存时会自动 `chmod 0o600`。

4. **资产抽屉密码**：侧边栏的资产管理和生图配置受 `ASSET_DRAWER_PASS` 保护，基于 Flask session 认证。生产环境必须改强密码。

5. **Session Cookie 加固**：生产模式下 `SESSION_COOKIE_SECURE=True`，`HTTPOnly=True`，`SameSite=Lax`，有效期 12 小时。

---

## 常见修改场景

| 场景 | 应该修改的文件 |
|------|---------------|
| 新增/修改 API 端点 | `backend/app.py` |
| 调整状态校验逻辑 | `backend/app.py`（`VALID_AGENT_STATES`、`normalize_agent_state`） |
| 修改安全策略 | `backend/security_utils.py` + `backend/app.py` 启动硬检查 |
| 调整昨日小记提取规则 | `backend/memo_utils.py` |
| 修改前端游戏画面 | `frontend/game.js`、`frontend/layout.js`、`frontend/index.html` |
| 新增前端页面路由 | `backend/app.py`（新增 `@app.route`）+ `frontend/` 下新增 HTML |
| 调整桌面宠物窗口行为 | `desktop-pet/src-tauri/`（Tauri）或 `electron-shell/`（Electron） |
| 修改 Telegram Bot 指令 | `backend/telegram_bot.py` |
| 调整 OpenClaw 桥接 | `backend/claw_office_bridge.py` |
| 添加新的生图模型映射 | `backend/app.py`（`USER_MODEL_TO_PROVIDER_MODELS`）+ `backend/store_utils.py`（`_normalize_user_model`） |
| 调整访客接入说明 | `frontend/join-office-skill.md` |

---

## 注意事项

- **不要**将 `.env`、`runtime-config.json`、自定义 API key 提交到 git。
- **不要**在 `backend/app.py` 中硬编码用户主目录或绝对路径，始终通过 `ROOT_DIR` 相对定位。
- 修改 `frontend/index.html` 后，重启后端才能刷新 `_INDEX_HTML_CACHE`（它在启动时加载并替换 `{{VERSION_TIMESTAMP}}`）。
- 生图功能依赖独立的 Python 虚拟环境（`../skills/gemini-image-generate/.venv`），不在主 `.venv` 中。如果生图失败，先检查该环境是否存在。
- 当前项目同时存在 **Electron**（`electron-shell/`）和 **Tauri v2**（`desktop-pet/`）两个桌面壳。活跃开发的是 `desktop-pet/`（Tauri），`electron-shell/` 为旧版保留。
- `set_state.py` 允许 `receiving` 和 `replying` 状态，但后端 `app.py` 不识别，会回退为 `idle`。如需支持，需同步修改后端 canonical 状态集合。
- `backend/run.sh` 强制使用 `.venv/bin/python`。若未创建 `.venv`，需先 `python3 -m venv .venv` 并安装依赖。

---

## 相关文件速查

- 主入口：`backend/app.py`
- 状态脚本：`set_state.py`
- 访客推送：`office-agent-push.py`
- 环境模板：`.env.example`
- 依赖清单：`backend/requirements.txt`
- 启动脚本：`backend/run.sh`
- 桌面壳说明：`desktop-pet/README.md`（Tauri v2）
- OpenClaw Skill：`SKILL.md`
- 访客 Skill：`frontend/join-office-skill.md`
- 用户文档：`README.md`（中文）、`README.en.md`（英文）、`README.ja.md`（日文）
