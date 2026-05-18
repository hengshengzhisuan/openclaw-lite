# OpenClaw Lite

本文档描述 **OpenClaw Lite** 的本地运行方式、功能概览与部署流程。

**仓库地址：** https://github.com/hengshengzhisuan/openclaw-lite

---

## 1. 项目概述

| 组件 | 技术栈 | 说明 |
| --- | --- | --- |
| **openclaw-lite** | Python 3.11+、FastAPI、Uvicorn、SQLAlchemy、Playwright、OpenAI SDK | 技术部门 IM 助手后端：自然语言解析 → 白名单工具执行 |
| **接入形态** | 飞书 / 企业微信 机器人 + HTTP API | 群聊 @ 机器人或私聊；亦可通过 `POST /execute` 直接调试 |

**产品定位：** 将「命令行式」运维/开发操作聊天化——查库、读日志、调白名单 API、打开网页文档等，由 LLM 识别意图后调用对应工具。

**架构分层：**

```
用户（飞书 / 企微 / HTTP）
        ↓
接入层  FastAPI  /execute  /health  /im/*
        ↓
解析层  LLM 意图识别 → tool + 参数
        ↓
执行层  browser | database | file | api
```

---

## 2. 环境要求

- **运行时：** Python 3.11+（推荐 3.12）
- **依赖服务（按需）：**
  - OpenAI 或兼容网关（`OPENAI_API_KEY`）
  - MySQL / PostgreSQL（只读账号，用于 `database` 工具）
  - 飞书 / 企业微信应用（用于 IM 回调，可选）
- **本地开发：** `pip`、`venv`
- **生产（推荐）：** Docker / Docker Compose；Playwright Chromium 已包含在镜像构建中

---

## 3. 本地运行

### 3.1 安装与配置

```bash
git clone https://github.com/hengshengzhisuan/openclaw-lite.git
cd openclaw-lite

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt

# Playwright 浏览器（本地非 Docker 时需执行一次）
playwright install chromium

cp .env.example .env
# 编辑 .env，至少配置 OPENAI_API_KEY；使用数据库工具时配置 DATABASE_* 等
```

编辑 **`config.yaml`**（或通过环境变量占位符覆盖）：

- `llm`：模型、`base_url`、`timeout`
- `database.*`：各连接名与只读 URL（与 `.env` 中 `DATABASE_RECORDING_URL`、`DATABASE_DREAM_URL` 等对应）
- `file.allowed_paths`、`api.whitelist`：安全白名单
- `im.feishu` / `im.wechat`：IM 应用凭证

> **说明：** `config.yaml` 中 `database.recording` 使用环境变量 **`DATABASE_RECORDING_URL`**；`database.dream` 使用 **`DATABASE_DREAM_URL`**。请与 `.env` 键名保持一致。

### 3.2 启动 API

```bash
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

| 地址 | 说明 |
| --- | --- |
| http://127.0.0.1:8000/docs | Swagger 交互文档 |
| http://127.0.0.1:8000/health | 健康检查 |
| http://127.0.0.1:8000/execute | 统一执行入口（调试） |
| http://127.0.0.1:8000/im/feishu/events | 飞书事件订阅回调 |
| http://127.0.0.1:8000/im/wechat/callback | 企业微信回调（部分能力为占位实现） |

### 3.3 快速验证（HTTP）

```bash
curl -s http://127.0.0.1:8000/health

curl -s -X POST http://127.0.0.1:8000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "dev_user",
    "platform": "http",
    "message": "查 recording 库 SELECT * FROM recordings LIMIT 3"
  }'
```

成功时响应体包含 `task_id`、`status`、`tool`、`result`、`duration` 等字段。

### 3.4 飞书联调（可选）

1. 在[飞书开放平台](https://open.feishu.cn/)创建应用，开通机器人与「接收消息」等权限。  
2. **事件订阅** Request URL 填：`https://<你的公网域名>/im/feishu/events`（本地可用 ngrok 等隧道）。  
3. 将 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_ENCRYPT_KEY`、`FEISHU_VERIFICATION_TOKEN` 写入 `.env`。  
4. 在群内 @ 机器人发送自然语言指令，后台异步执行并回复。

---

## 4. 项目功能

### 4.1 一句话执行

用户用自然语言描述需求，系统经 LLM 解析为结构化参数后调用工具。

**示例输入：** `查一下 recording 库前 3 条录音`

**处理流程：** 解析为 `database` 工具 → 生成/校验 SQL → 只读执行 → 格式化返回。

### 4.2 四大利器（工具集）

| 工具 | 标识 | 用途 | 安全机制 |
| --- | --- | --- | --- |
| 浏览器 | `browser` | 打开文档站、状态页，提取纯文本 | Playwright headless；仅 http/https |
| 数据库 | `database` | 只读查业务数据、统计 SQL | 非 SELECT 拦截；`max_rows`、超时、只读账号 |
| 文件 | `file` | 读应用/系统日志、配置文件 | 路径白名单；禁止写；`max_lines` 上限 |
| API | `api` | 调内部/白名单 HTTP 接口 | 域名白名单；请求超时；日志记录 |

### 4.3 双平台 IM

| 平台 | 回调路径 | 状态 |
| --- | --- | --- |
| 飞书 | `POST /im/feishu/events` | 支持 URL 验证、加解密、文本消息异步回复 |
| 企业微信 | `GET/POST /im/wechat/callback` | 基础回调与占位逻辑；完整加解密/主动发消息待完善 |

### 4.4 主要 HTTP 接口

#### `GET /health`

```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime": 3600
}
```

#### `POST /execute`

**请求体：**

```json
{
  "user_id": "user_123",
  "platform": "feishu",
  "message": "读 /var/log/nginx/access.log 最后 20 行"
}
```

**响应体（成功示例）：**

```json
{
  "task_id": "task_20240508_001",
  "status": "success",
  "tool": "file",
  "result": "【工具: file】\n...",
  "duration": 1.2,
  "error": null
}
```

---

## 5. 部署流程

### 5.1 Docker Compose（本地 / 小团队）

适用：单机、日请求量较小（&lt;1000），快速起服务。

```bash
cp .env.example .env
# 编辑 .env 与 config.yaml（Compose 会挂载 config.yaml）

docker compose up -d --build
curl -s http://127.0.0.1:8000/health
```

`docker-compose.yml` 会将 `./config.yaml` 挂载到容器，并将宿主机 `/var/log` 只读挂载供 `file` 工具使用（可按需修改）。

### 5.2 生产镜像（Docker 导入运行）——推荐

**制品命名：** `openclaw-lite_vX.Y.Z_linux_amd64.tar.gz`（由 CI 构建或本地 `docker build` + `docker save` 生成）。

#### 概要步骤

1. 获取制品：GitHub Release（推送 `v*` tag）或 Actions 手动 workflow 下载。  
2. 服务器安装 Docker，导入镜像：  
   `gunzip -c openclaw-lite_v0.0.6_linux_amd64.tar.gz | docker load`  
3. 在部署目录准备 `.env`（参考 `.env.example`）与 `config.yaml`。  
4. 停止旧容器并启动新容器（示例）：  

```bash
docker stop openclaw_api 2>/dev/null || true
docker rm openclaw_api 2>/dev/null || true

docker run -d \
  --name openclaw_api \
  --restart unless-stopped \
  --env-file .env \
  -p 6002:8000 \
  -v "$(pwd)/config.yaml:/app/config.yaml" \
  openclaw-lite:v0.0.6

docker logs -f openclaw_api
```

5. 验证：`curl http://<宿主机>:6002/health` 与 `/docs`。

#### 服务器上传示例（scp）

在**本机**打包目录或 Release 下载目录执行（将路径、用户、IP 替换为实际值）：

```bash
# 本机：确认制品路径
ls openclaw-lite_v0.0.6_linux_amd64.tar.gz

# 上传到服务器（示例目录 /www/backup/openclaw-lite）
scp openclaw-lite_v0.0.6_linux_amd64.tar.gz user@<服务器IP>:/www/backup/openclaw-lite/

# 登录服务器后
cd /www/backup/openclaw-lite
gunzip -c openclaw-lite_v0.0.6_linux_amd64.tar.gz | docker load
docker images | grep openclaw-lite
```

> **安全提示：** 勿在文档或 Git 中提交真实服务器密码、`.env` 密钥；生产务必轮换 `OPENAI_API_KEY`、飞书/企微 Secret。

### 5.3 本地构建镜像

```bash
docker build -t openclaw-lite:v0.0.6 .
docker save openclaw-lite:v0.0.6 | gzip -c > openclaw-lite_v0.0.6_linux_amd64.tar.gz
```

### 5.4 CI/CD（Git Tag 发版）

- **工作流：** `.github/workflows/zip.yml`  
- **触发：** 推送符合 `v*` 的 Git tag（如 `v1.0.0`），或 Actions 页面手动 `workflow_dispatch`。  
- **产物：** `openclaw-lite_<version>_linux_amd64.tar.gz`；tag 推送时自动创建 GitHub Release 并上传制品。

```bash
git tag v1.0.0
git push origin v1.0.0
```

### 5.5 IM 与反向代理

- 飞书/企微回调必须使用 **HTTPS 公网地址**，建议在 Nginx/Caddy 反代到容器 `8000` 端口。  
- 回调路径示例：  
  - 飞书：`https://api.example.com/im/feishu/events`  
  - 企微：`https://api.example.com/im/wechat/callback`  
- 确保防火墙放行反代端口，且 `config.yaml` / `.env` 与线上一致。

### 5.6 运维注意

- **日志：** 默认输出到容器 stdout，使用 `docker logs` 查看；关键字段含 `user`、`platform`、`tool`、`duration`。  
- **配置变更：** 修改 `config.yaml` 后需重启容器；`.env` 变更后 `docker run` 需带新 `--env-file`。  
- **Playwright：** 已打入镜像；宿主机直接 `pip install` 时需额外 `playwright install chromium`。  
- **数据库：** 仅配置只读账号；`max_rows`、`timeout` 在 `config.yaml` 的 `database.*` 下调整。

---

## 6. 环境变量说明

| 变量名 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | LLM API 密钥（必填，否则 `/execute` 返回配置错误） |
| `OPENAI_BASE_URL` | 兼容网关地址（可选） |
| `OPENAI_MODEL` | 模型名，默认 `gpt-3.5-turbo` |
| `DATABASE_RECORDING_URL` | `config.yaml` → `database.recording` 的 SQLAlchemy URL |
| `DATABASE_DREAM_URL` | `config.yaml` → `database.dream` 的 SQLAlchemy URL |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书应用凭证 |
| `FEISHU_ENCRYPT_KEY` | 飞书事件加解密 Key |
| `FEISHU_VERIFICATION_TOKEN` | 飞书 Verification Token（可选校验） |
| `WECHAT_CORP_ID` / `WECHAT_SECRET` / `WECHAT_AGENT_ID` | 企业微信应用 |
| `WECHAT_CALLBACK_TOKEN` | 企微回调 Token |
| `OPENCLAW_CONFIG` | 配置文件路径，默认 `config.yaml` |

---

## 7. 相关文档索引

| 文档 | 路径 |
| --- | --- |
| 项目排期与进度 | [docs/项目排期.md](docs/项目排期.md) |
| 环境变量模板 | [.env.example](.env.example) |
| 运行配置 | [config.yaml](config.yaml) |
| Docker 编排 | [docker-compose.yml](docker-compose.yml) |
| 发版工作流 | [.github/workflows/zip.yml](.github/workflows/zip.yml) |

---

## 8. 常见问题

| 现象 | 排查建议 |
| --- | --- |
| `OPENAI_API_KEY is not configured` | 检查 `.env` 是否加载、`OPENAI_API_KEY` 是否为空 |
| 数据库工具报错 connection 不存在 | `config.yaml` 中 `database` 键名与 LLM 解析的 `connection` 一致；必要时配置 `database_connection_aliases` |
| 飞书回调 403 | `FEISHU_VERIFICATION_TOKEN` 与飞书后台不一致 |
| 飞书无回复 | 查看 `docker logs`；确认 `FEISHU_APP_ID/SECRET`、发消息 API 权限、事件订阅已启用 |
| `file` 工具路径拒绝 | 路径须在 `file.allowed_paths` 白名单内；Docker 需挂载对应宿主机目录 |
| `api` 工具域名拒绝 | 目标 host 须加入 `api.whitelist` |

---

**文档版本：** V1.0  
**适用对象：** 技术部门（开发、运维、测试、数据团队）
