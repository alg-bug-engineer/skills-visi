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

安全组放行：**80**（HTTP）。8011 仅本机访问，无需公网暴露。

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
bash scripts/prod-start.sh
```

`prod-start.sh` 会：

1. 创建/更新 `backend/.venv` 并安装依赖
2. `npm ci && npm run build` 构建 `frontend-v2/dist`（`VITE_API_BASE=` 空，同源反代）
3. 后台启动 `uvicorn`（`0.0.0.0:8011`）
4. 若检测到 Nginx，安装 `deploy/nginx.host.conf` 并重载

---

## 3. Nginx 手动配置

若脚本未自动配置 Nginx：

```bash
sudo cp deploy/nginx.host.conf /etc/nginx/conf.d/intersection-agent.conf
# 确认 root 路径与项目部署目录一致
sudo nginx -t && sudo systemctl reload nginx
```

修改 `root` 行以匹配实际部署路径，默认：

```
root /var/www/intersection-agent/frontend-v2/dist;
```

---

## 4. systemd 持久化（推荐）

```bash
sudo cp deploy/intersection-agent-backend.service /etc/systemd/system/
# 确认 WorkingDirectory、ExecStart 路径
sudo systemctl daemon-reload
sudo systemctl enable intersection-agent-backend
sudo systemctl start intersection-agent-backend
```

之后可用 `systemctl status intersection-agent-backend` 管理后端进程。

---

## 5. 环境变量

| 变量 | 生产值 | 说明 |
|------|--------|------|
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
curl http://127.0.0.1/health

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

- [ ] `curl http://<ECS_IP>/health` 返回 200
- [ ] 浏览器访问 `http://<ECS_IP>/` 可打开三栏工作台
- [ ] 完成一次 SSE 诊断对话
- [ ] `DEMO_MODE=1` 时 TOP3 演示路口话术可用
