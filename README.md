# Modal Argo + 哪吒探针 混合部署

合并自两个项目：
- **python-argo-modal**：Argo 隧道 + VLESS/VMess/Trojan 节点 + 订阅
- **modal-nz**：哪吒探针 (V0/V1) + 伪装 + 保活

现已**混合成一个统一工作流**。

---

## 🚀 快速开始

1. Fork 本仓库
2. 在 **Settings → Secrets and variables → Actions** 配置 Secrets（见下方）
3. 进入 **Actions → Modal Argo + 哪吒 混合部署 → Run workflow**
4. 选择 `deploy` + 部署区域 → 运行
5. 等待完成，访问订阅地址获取节点

---

## 🔐 Secrets 配置

### 必填

| Secret | 说明 |
|--------|------|
| `MODAL_TOKEN_ID` | Modal 令牌 ID（ak-xxx） |
| `MODAL_TOKEN_SECRET` | Modal 令牌密钥（as-xxx） |
| `MODAL_USER_NAME` | Modal 账号用户名 |
| `ARGO_DOMAIN` | Argo 固定隧道域名（推荐） |
| `ARGO_AUTH` | Argo Token 或 TunnelSecret JSON |

### 推荐 / 可选

| Secret | 说明 | 默认 |
|--------|------|------|
| `MODAL_APP_NAME` | Modal 应用名 | `proxy-app` |
| `UUID` | 节点 UUID | 内置默认 |
| `NEZHA_SERVER` | 哪吒地址（v1: `domain:port`） | - |
| `NEZHA_KEY` | 哪吒密钥 | - |
| `NEZHA_PORT` | 哪吒端口（仅 v0） | - |
| `CFIP` | 优选 IP/域名 | `www.visa.com.tw` |
| `CFPORT` | 端口 | `443` |
| `NAME` | 节点名称前缀 | `Modal` |
| `SUB_PATH` | 订阅路径 | `sub` |
| `BOT_TOKEN` | Telegram Bot Token | - |
| `CHAT_ID` | Telegram Chat ID | - |
| `ARGO_PORT` | Argo 本地端口 | `8001` |

---

## 📋 工作流说明（单一文件）

**文件位置**：`.github/workflows/modal-deploy.yml`

### 触发方式

| 方式 | 说明 |
|------|------|
| **手动** | Actions 界面选择区域 + 运行 |
| **定时** | 每月 1-23 日 UTC 18:00 自动部署（防休眠） |
| **自动恢复** | 接收 `repository_dispatch`（`service-down-alert`）后重新部署 |

### 操作选项

- **deploy**：部署 / 更新
- **stop**：停止应用（释放资源）

### 区域选择

支持 Broad（自动分配）和 Specific（精确区域），覆盖全球 80+ 区域（AWS / GCP / OCI / Azure）。

---

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `app.py` | **推荐主入口**（基于 argo2，含 Argo + 节点 + 哪吒下载） |
| `app_nz.py` | 原哪吒版本（保活/伪装更完整，可参考） |
| `modal_app_argo.py` | 原 argo 版本 |
| `modal_app_argo2.py` | 原 argo2 版本 |
| `.github/workflows/modal-deploy.yml` | **唯一工作流**（已合并所有功能） |

部署时工作流会自动优先使用 `app.py`。

---

## 🔗 部署后访问

假设用户名为 `yourname`，应用名为 `proxy-app`：

- 服务根路径：`https://yourname--proxy-app-web_server.modal.run`
- 订阅地址：`https://yourname--proxy-app-web_server.modal.run/sub`

---

## ⚠️ 注意事项

1. **推荐使用固定 Argo 隧道**（临时隧道在 Modal 上不稳定）
2. Modal 免费额度有限，注意用量
3. 哪吒探针需正确配置 `NEZHA_SERVER` + `NEZHA_KEY` 才能上线
4. 不同部署区域建议使用不同 UUID，避免哪吒面板互相覆盖

---

## License

MIT
