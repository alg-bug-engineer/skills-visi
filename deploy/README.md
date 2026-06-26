# ECS 部署指南（原生方式）

> 默认部署路径：**宿主机 Python + Node 构建 + Nginx**，与 `scripts/dev-v2.sh` 开发模式一致，不使用 Docker。

---

## 1. 前置条件

| 组件 | 版本建议 |
|------|----------|
| Python | 3.11+ |
| Node.js | 22+ |
| Nginx | 1.20+ |
| 系统 | 阿里云 ECS（CentOS / Ubuntu / Alibaba Cloud Linux） |

安全组放行：**5568**（前端 HTTP，默认）。8011 仅本机访问，无需公网暴露。**不使用 80 端口。**

### 安装 Python 3.11（ECS 默认常为 3.10，需单独安装）

```bash
# Ubuntu 22.04 / Debian
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# 验证
python3.11 --version   # 应 >= 3.11

# 若曾用 3.10 创建过 venv，需删除后重装
rm -rf backend/.venv
```

Alibaba Cloud Linux 3：

```bash
sudo dnf install -y python3.11 python3.11-devel
# 若仓库无 3.11，请用 pyenv 或源码编译，然后:
# PYTHON_BIN=/path/to/python3.11 bash scripts/prod-start.sh
```

---

## 2. 首次部署

```bash
# 1. 克隆/同步代码到 ECS（示例路径）
sudo mkdir -p /var/www/intersection-agent
sudo chown "$USER:$USER" /var/www/intersection-agent
# rsync 或 git clone 到 /var/www/intersection-agent

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 PG、DASHSCOPE_API_KEY、DEMO_MODE 等

# 3. 一键构建并启动
HTTP_PORT=5568 bash scripts/prod-start.sh   # 默认 5568，禁止 80
```

`prod-start.sh` 会：

1. 创建/更新 `backend/.venv` 并安装依赖
2. `npm ci && npm run build` 构建 `frontend-v2/dist`（`VITE_API_BASE=` 空，同源反代）
3. 后台启动 `uvicorn`（`0.0.0.0:8011`）
4. 若检测到 Nginx，渲染 `deploy/nginx.host.conf`（默认监听 **5568**，非 80）并重载

---

## 3. Nginx 配置（公网 IP + 端口，无域名）

本服务与 `ppt.conf` 等站点**独立**，写入 `sites-available/intersection-agent.conf`，监听 **HTTP 5568**（非 80/443）。

```bash
# 脚本自动完成；或手动：
bash scripts/prod-start.sh
bash scripts/prod-check.sh    # 自检
```

**访问地址（必须用 HTTP，不要用 HTTPS）：**

```
http://8.149.232.39:5568/
http://8.149.232.39:5568/health
```

`https://IP:5568` 无效——5568 未配置 SSL 证书。`ppt.conf` 的 443 证书只绑定域名 `ppt.ai-knowledgepoints.cn`。

### 手动配置（若脚本未生效）

```bash
cd ~/workspaces/skills-visi
DEPLOY_ROOT="$(pwd)" HTTP_PORT=5568 BACKEND_PORT=8011

sed -e "s|__DEPLOY_ROOT__|${DEPLOY_ROOT}|g" \
    -e "s|__HTTP_PORT__|${HTTP_PORT}|g" \
    -e "s|__BACKEND_PORT__|${BACKEND_PORT}|g" \
    deploy/nginx.host.conf | sudo tee /etc/nginx/sites-available/intersection-agent.conf

sudo ln -sf /etc/nginx/sites-available/intersection-agent.conf \
  /etc/nginx/sites-enabled/intersection-agent.conf
sudo nginx -t && sudo systemctl reload nginx
```

---

## 4. 外网无法访问排查

| 检查项 | 命令 |
|--------|------|
| 本机后端 | `curl http://127.0.0.1:8011/health` |
| 本机 Nginx | `curl http://127.0.0.1:5568/health` |
| 端口监听 | `ss -tlnp \| grep 5568` |
| Nginx 配置 | `nginx -T \| grep 5568` |
| 一键自检 | `bash scripts/prod-check.sh` |

**常见原因：**

1. **用了 https** → 改为 `http://IP:5568`
2. **Nginx 写在 conf.d 但未 include** → 已改为 `sites-enabled`（与 ppt.conf 同机制）
3. **阿里云安全组未放行 5568** → 控制台 → 安全组 → 入方向添加 `5568/tcp`（**ufw 放行不够，还有云安全组一层**）
4. **nginx -t 失败未 reload** → 查看 `sudo nginx -t` 报错

---

## 5. systemd 持久化（推荐）

```bash
sudo cp deploy/intersection-agent-backend.service /etc/systemd/system/
# 确认 WorkingDirectory、ExecStart 路径
sudo systemctl daemon-reload
sudo systemctl enable intersection-agent-backend
sudo systemctl start intersection-agent-backend
```

之后可用 `systemctl status intersection-agent-backend` 管理后端进程。

---

## 6. 环境变量

| 变量 | 生产值 | 说明 |
|------|--------|------|
| `HTTP_PORT` | `5568` | 前端 Nginx 监听端口（**禁止 80**） |
| `HOST` | `0.0.0.0` | 后端监听地址 |
| `PORT` | `8011` | 后端端口 |
| `CORS_ORIGINS` | `*` 或域名 | 跨域 |
| `DEMO_MODE` | `1` | 演示汇报时开启 |
| `PGHOST` 等 | — | PostgreSQL 连接 |
| `DASHSCOPE_API_KEY` | — | LLM |

前端构建：`VITE_API_BASE=`（空字符串，由 Nginx 反代 `/api`）。

---

## 6. 运维命令

```bash
bash scripts/prod-start.sh    # 构建 + 启动
bash scripts/prod-stop.sh     # 停止后端与相关进程

# 健康检查
curl http://127.0.0.1:8011/health
curl http://127.0.0.1:5568/health

# 日志
tail -f backend/data/logs/app.log
tail -f .prod-logs/backend.log
```

---

## 7. Docker 部署（备选，非默认）

若需容器化，可使用：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Docker 配置见 `deploy/Dockerfile.*` 与 `deploy/nginx.conf`（容器内 `backend:8011` 网络）。**日常 ECS 部署请使用本节以上的原生方式。**

---

## 8. 验收清单

- [ ] `curl http://<ECS_IP>:5568/health` 返回 200
- [ ] 浏览器访问 `http://<ECS_IP>:5568/` 可打开三栏工作台
- [ ] 完成一次 SSE 诊断对话
- [ ] `DEMO_MODE=1` 时 TOP3 演示路口话术可用
