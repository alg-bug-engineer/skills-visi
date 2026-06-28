# 开发环境约束

> 版本：2026-06-28  
> 状态：本地开发约定（Agent 与开发者均需遵守）  
> Cursor 规则：`.cursor/rules/network-proxy.mdc`

---

## 1. 终端网络代理

访问 GitHub、npm、PyPI 等外网时，**先在本终端设置代理**，再执行 `git push`、`npm install`、`pip install`、`curl` 等命令。

### 1.1 每个新终端会话执行

```bash
export https_proxy=http://127.0.0.1:7897
export http_proxy=http://127.0.0.1:7897
export all_proxy=socks5://127.0.0.1:7897
```

### 1.2 典型场景

| 操作 | 说明 |
|------|------|
| `git push origin main` | 推送代码与 tag |
| `git fetch` / `git clone` | 拉取远程仓库 |
| `npm install` | frontend-v2 依赖 |
| `pip install` / backend venv | Python 依赖 |
| `curl` / `gh` | API、Release 等 |

### 1.3 故障排查

若出现以下错误，优先检查是否已 export 代理并重试：

- `Recv failure: Connection reset by peer`
- `LibreSSL SSL_connect: SSL_ERROR_SYSCALL`
- `fatal: unable to access 'https://github.com/...'`

### 1.4 注意事项

- 代理地址 `127.0.0.1:7897` 为本机常用 Clash/V2Ray HTTP/SOCKS 端口；若本地端口不同，请自行替换。
- 仅对**当前 shell 会话**生效；新开终端需重新 export。
- **禁止**将 proxy 配置写入仓库内 `.env` 或提交到 git。
- **后端/前端运行时不需要代理**：`httpx` 等库会继承 shell 的 `all_proxy`（SOCKS）导致报错。应用启动时会自动清除代理环境变量；代理仅用于 `git` / `npm` / `pip` 等 CLI，勿依赖代理访问 DashScope 或数据库。

### 1.5 可选：长期生效（开发者本地）

可加入 `~/.zshrc` 或 `~/.bashrc`（**不提交本仓库**）：

```bash
# export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897 all_proxy=socks5://127.0.0.1:7897
```

---

## 2. 其他开发约束索引

| 约束 | 文档 |
|------|------|
| 回归测试（合并前必跑） | [REGRESSION_POLICY.md](./REGRESSION_POLICY.md) |
| Python 版本 | backend 要求 **3.11+**，见 `scripts/lib/python.sh` |
| 端口 | 后端 8011 · frontend-v2 5568 |
