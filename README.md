# Modal Argo + 哪吒探针 混合部署

本仓库合并了两个项目的功能：
- **python-argo-modal**：Argo 隧道 + VLESS/VMess/Trojan 节点 + 订阅
- **modal-nz**：哪吒探针（V0/V1）部署 + 伪装页面 + 保活机制

支持在 Modal.com 上一键部署免费节点 + 监控探针。

## 功能特性

- ✅ Cloudflare Argo 固定/临时隧道
- ✅ VLESS / VMess / Trojan 协议支持
- ✅ 哪吒探针 V0 / V1 支持
- ✅ 自动保活（防止 Modal 休眠）
- ✅ 伪装 HTML 页面
- ✅ Telegram 通知（可选）
- ✅ GitHub Actions 多区域部署
- ✅ 订阅链接生成

## 快速开始

1. Fork 本仓库
2. 在 Settings → Secrets and variables → Actions 配置 Secrets
3. 进入 Actions 选择工作流运行
4. 选择部署区域并执行

## 必填 Secrets

| 名称 | 说明 |
|------|------|
| `MODAL_TOKEN_ID` | Modal Token ID |
| `MODAL_TOKEN_SECRET` | Modal Token Secret |
| `MODAL_USER_NAME` | Modal 用户名 |
| `ARGO_DOMAIN` | Argo 固定隧道域名（推荐） |
| `ARGO_AUTH` | Argo Token 或 TunnelSecret |

## 可选 Secrets

| 名称 | 说明 |
|------|------|
| `UUID` | 节点 UUID |
| `NEZHA_SERVER` | 哪吒服务器地址 |
| `NEZHA_KEY` | 哪吒密钥 |
| `NEZHA_PORT` | 哪吒端口（V0） |
| `CFIP` | 优选 IP/域名 |
| `CFPORT` | 端口 |
| `NAME` | 节点名称前缀 |
| `BOT_TOKEN` | Telegram Bot Token |
| `CHAT_ID` | Telegram Chat ID |
| `SUB_PATH` | 订阅路径（默认 sub） |
| `MODAL_APP_NAME` | Modal App 名称 |
| `DEPLOY_REGION` | 部署区域 |

## 文件说明

- `app.py`：推荐主入口（合并版，含 Argo + 哪吒 + 保活 + 伪装）
- `modal_app_argo.py`：原 argo 版本
- `modal_app_argo2.py`：原 argo2 版本（含更多下载）
- `app_nz.py`：原哪吒版本
- `.github/workflows/`：多个部署工作流

## 注意事项

- Modal 免费额度有限，建议使用固定 Argo 隧道
- 部署后访问 `https://{user}--{app}-web_server.modal.run/sub` 获取订阅
- 哪吒探针需要正确配置服务器地址和密钥才能上线

## License

MIT
