import os
import re
import json
import time
import base64
import random
import platform
import threading
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, Request
from fastapi.responses import HTMLResponse
import modal

# ==================== 用户可配置 ====================
MODAL_APP_NAME   = os.environ.get("MODAL_APP_NAME", "proxy-agent")
MODAL_USER_NAME  = os.environ.get("MODAL_USER_NAME", "")
DEPLOY_REGION    = os.environ.get("DEPLOY_REGION", "asia-northeast1")   # 或 us-east 等
SUB_PATH         = os.environ.get("SUB_PATH", "sub")

# ==================== 镜像 ====================
image = (
    modal.Image.debian_slim()
    .pip_install(
        "fastapi==0.115.12",
        "uvicorn",
        "requests",
        "psutil",
        "pydantic==2.11.7",
    )
    .run_commands(
        "apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*",
        "mkdir -p /root/.tmp /root/.cache",
        "curl -L https://amd64.ssss.nyc.mn/web -o /root/.tmp/web",
        "curl -L https://amd64.ssss.nyc.mn/2go -o /root/.tmp/bot",
        "chmod +x /root/.tmp/web /root/.tmp/bot",
    )
)

app = modal.App(MODAL_APP_NAME, image=image)

# 同时支持两套 Secret（你也可以合并成一个）
app_secrets = [
    modal.Secret.from_name("modal-secrets"),      # UUID / ARGO_* / CFIP 等
    modal.Secret.from_name("nezha-secrets"),       # NEZHA_* 等
]

subscription_dict = modal.Dict.from_name("modal-dict-data", create_if_missing=True)

# ==================== 全局状态 ====================
_agent_started = False
_agent_lock = threading.Lock()
_keepalive_started = False
_keepalive_lock = threading.Lock()
_project_url = None

# ==================== 伪装页面 ====================
FAKE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cloud Services Platform</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center}
.container{background:#fff;border-radius:16px;padding:48px;max-width:580px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.15);text-align:center}
.logo{width:64px;height:64px;background:linear-gradient(135deg,#667eea,#764ba2);border-radius:16px;margin:0 auto 24px;display:flex;align-items:center;justify-content:center}
.logo svg{width:36px;height:36px;fill:#fff}
h1{font-size:24px;color:#1a1a2e;margin-bottom:8px;font-weight:700}
.subtitle{color:#6b7280;font-size:15px;margin-bottom:32px;line-height:1.6}
.status-badge{display:inline-flex;align-items:center;gap:6px;background:#ecfdf5;color:#059669;padding:8px 20px;border-radius:24px;font-size:14px;font-weight:500;margin-bottom:24px}
.status-badge .dot{width:8px;height:8px;background:#059669;border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.status-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:32px}
.status-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:20px 16px}
.status-card .icon{font-size:28px;margin-bottom:8px}
.status-card .label{font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.status-card .value{font-size:16px;font-weight:600;color:#1e293b}
.divider{height:1px;background:#e5e7eb;margin:24px 0}
.footer{color:#9ca3af;font-size:13px;line-height:1.8}
.tech-stack{display:flex;justify-content:center;gap:24px;margin-top:16px}
.tech-item{font-size:12px;color:#9ca3af}
</style>
</head>
<body>
<div class="container">
<div class="logo"><svg viewBox="0 0 24 24"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM14 13v4h-4v-4H7l5-5 5 5h-3z"/></svg></div>
<h1>Cloud Services Platform</h1>
<p class="subtitle">Enterprise-grade cloud infrastructure powering your applications with high availability and global reach.</p>
<div class="status-badge"><span class="dot"></span>All Systems Operational</div>
<div class="status-grid">
<div class="status-card"><div class="icon">⚡</div><div class="label">Uptime</div><div class="value">99.97%</div></div>
<div class="status-card"><div class="icon">🌍</div><div class="label">Regions</div><div class="value">12 Active</div></div>
<div class="status-card"><div class="icon">🔒</div><div class="label">Security</div><div class="value">TLS 1.3</div></div>
<div class="status-card"><div class="icon">📊</div><div class="label">Latency</div><div class="value">&lt;50ms</div></div>
</div>
<div class="divider"></div>
<div class="footer">
<p>&copy; 2025 Cloud Services Platform. All rights reserved.</p>
<p>Powered by distributed cloud architecture</p>
<div class="tech-stack">
<span class="tech-item">Kubernetes</span>
<span class="tech-item">Docker</span>
<span class="tech-item">Terraform</span>
<span class="tech-item">gRPC</span>
</div>
</div>
</div>
</body>
</html>"""

# ==================== 工具函数 ====================
def write_log(msg: str):
    try:
        with open("/tmp/agent.log", "a") as f:
            f.write(f"[{time.ctime()}] {msg}\n")
    except Exception:
        pass

def create_directory(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def get_system_architecture() -> str:
    arch = platform.machine().lower()
    return "arm" if "arm" in arch or "aarch64" in arch else "amd"

def download_file(name: str, url: str, path: str) -> bool:
    import requests
    try:
        full = os.path.join(path, name)
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(full, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        write_log(f"Download failed: {e}")
        return False

def authorize_files(path: str):
    if os.path.exists(path):
        os.chmod(path, 0o775)

def exec_cmd(cmd: str):
    try:
        with open("/tmp/agent.log", "a") as f:
            p = subprocess.Popen(cmd, shell=True, stdout=f, stderr=f, start_new_session=True)
        return p.pid
    except Exception as e:
        write_log(f"exec failed: {e}")
        return None

def generate_links(domain: str, name: str, uuid: str, cfip: str, cfport: int) -> str:
    try:
        meta = subprocess.run(
            ["curl", "-s", "https://speed.cloudflare.com/meta"],
            capture_output=True, text=True, timeout=5
        ).stdout.split('"')
        isp = f"{meta[25]}-{meta[17]}".replace(" ", "_").strip()
    except Exception:
        isp = "Modal"
    vmess = {
        "v": "2", "ps": f"{name}-{isp}", "add": cfip, "port": cfport,
        "id": uuid, "aid": "0", "scy": "none", "net": "ws", "type": "none",
        "host": domain, "path": "/vmess-argo?ed=2560", "tls": "tls",
        "sni": domain, "alpn": "", "fp": "chrome"
    }
    vmess_b64 = base64.b64encode(json.dumps(vmess).encode()).decode()
    return (
        f"vless://{uuid}@{cfip}:{cfport}?encryption=none&security=tls&sni={domain}"
        f"&fp=chrome&type=ws&host={domain}&path=%2Fvless-argo%3Fed%3D2560#{name}-{isp}\n\n"
        f"vmess://{vmess_b64}\n\n"
        f"trojan://{uuid}@{cfip}:{cfport}?security=tls&sni={domain}&fp=chrome"
        f"&type=ws&host={domain}&path=%2Ftrojan-argo%3Fed%3D2560#{name}-{isp}"
    ).strip()

# ==================== Nezha Agent ====================
def run_agent(file_path: str, server: str, port: str, key: str, uuid: str):
    if not server or not key:
        write_log("NEZHA_SERVER or NEZHA_KEY missing, skip agent")
        return
    arch = get_system_architecture()
    disguise = random.choice(["cache_manager", "session_handler", "task_worker", "log_rotator", "health_check"])
    if port:
        url = f"https://{'arm64' if arch == 'arm' else 'amd64'}.ssss.nyc.mn/agent"
    else:
        url = f"https://{'arm64' if arch == 'arm' else 'amd64'}.ssss.nyc.mn/v1"
    if not download_file(disguise, url, file_path):
        return
    agent = os.path.join(file_path, disguise)
    authorize_files(agent)
    if not os.path.exists(agent) or os.path.getsize(agent) < 1000:
        write_log("Agent binary invalid")
        return
    tls_ports = {"443", "8443", "2096", "2087", "2083", "2053"}
    if port:
        tls = "--tls" if port in tls_ports else ""
        cmd = f"nohup {agent} -s {server}:{port} -p {key} {tls} >/dev/null 2>&1 &"
    else:
        p = server.split(":")[-1] if ":" in server else ""
        tls = "true" if p in tls_ports else "false"
        cfg = os.path.join(file_path, "config.yaml")
        with open(cfg, "w") as f:
            f.write(
                f"client_secret: {key}\n"
                f"debug: false\n"
                f"disable_auto_update: true\n"
                f"disable_command_execute: false\n"
                f"disable_force_update: true\n"
                f"disable_nat: false\n"
                f"disable_send_query: false\n"
                f"gpu: false\n"
                f"insecure_tls: false\n"
                f"ip_report_period: 1800\n"
                f"report_delay: 4\n"
                f"server: {server}\n"
                f"skip_connection_count: false\n"
                f"skip_procs_count: false\n"
                f"temperature: false\n"
                f"tls: {tls}\n"
                f"use_gitee_to_upgrade: false\n"
                f"use_ipv6_country_code: false\n"
                f"uuid: {uuid}\n"
            )
        cmd = f'nohup {agent} -c "{cfg}" >/dev/null 2>&1 &'
    pid = exec_cmd(cmd)
    write_log(f"Agent started PID={pid}")

def ensure_agent_started():
    global _agent_started
    with _agent_lock:
        if _agent_started:
            return
        _agent_started = True
    FILE_PATH = os.environ.get("FILE_PATH", ".cache")
    create_directory(FILE_PATH)
    threading.Thread(
        target=run_agent,
        args=(
            FILE_PATH,
            os.environ.get("NEZHA_SERVER", ""),
            os.environ.get("NEZHA_PORT", ""),
            os.environ.get("NEZHA_KEY", ""),
            os.environ.get("UUID", ""),
        ),
        daemon=True,
    ).start()

# ==================== Keep-alive ====================
def get_project_url():
    global _project_url
    return _project_url or os.environ.get("PROJECT_URL", "")

def auto_detect_url(request: Request):
    global _project_url
    if _project_url:
        return
    host = request.headers.get("host", "")
    if host:
        scheme = request.headers.get("x-forwarded-proto", "https")
        _project_url = f"{scheme}://{host}"
        write_log(f"Auto-detected PROJECT_URL: {_project_url}")
        start_keepalive()

def start_keepalive():
    global _keepalive_started
    with _keepalive_lock:
        if _keepalive_started:
            return
        _keepalive_started = True
    url = get_project_url()
    if not url:
        with _keepalive_lock:
            _keepalive_started = False
        return
    interval = int(os.environ.get("KEEPALIVE_INTERVAL", "120"))
    auto = os.environ.get("AUTO_ACCESS", "true").lower() in ("true", "1", "yes")

    def self_ping():
        import requests
        while True:
            time.sleep(interval + random.randint(0, 30))
            try:
                requests.get(url.rstrip("/") + "/health", timeout=30)
            except Exception:
                pass

    threading.Thread(target=self_ping, daemon=True).start()
    if auto:
        def add_task():
            import requests
            try:
                requests.post("https://trans.ct8.pl/add-url", json={"url": url}, timeout=30)
            except Exception:
                pass
        threading.Thread(target=add_task, daemon=True).start()

# ==================== Lifespan：启动 Xray + Argo + Agent ====================
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    print("▶️ Lifespan startup")

    UUID        = os.environ.get("UUID") or "be16536e-5c3c-44bc-8cb7-b7d0ddc3d951"
    ARGO_DOMAIN = os.environ.get("ARGO_DOMAIN") or ""
    ARGO_AUTH   = os.environ.get("ARGO_AUTH") or ""
    ARGO_PORT   = int(os.environ.get("ARGO_PORT") or "8001")
    NAME        = os.environ.get("NAME") or "Modal"
    CFIP        = os.environ.get("CFIP") or "www.visa.com.tw"
    CFPORT      = int(os.environ.get("CFPORT") or "443")

    # ---------- Xray config ----------
    config = {
        "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
        "inbounds": [
            {
                "port": ARGO_PORT,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID}],
                    "decryption": "none",
                    "fallbacks": [
                        {"dest": 3001},
                        {"path": "/vless-argo", "dest": 3002},
                        {"path": "/vmess-argo", "dest": 3003},
                        {"path": "/trojan-argo", "dest": 3004},
                    ],
                },
                "streamSettings": {"network": "tcp"},
            },
            {
                "port": 3001, "listen": "127.0.0.1", "protocol": "vless",
                "settings": {"clients": [{"id": UUID}], "decryption": "none"},
                "streamSettings": {"network": "ws", "security": "none"},
            },
            {
                "port": 3002, "listen": "127.0.0.1", "protocol": "vless",
                "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"},
                "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/vless-argo"}},
            },
            {
                "port": 3003, "listen": "127.0.0.1", "protocol": "vmess",
                "settings": {"clients": [{"id": UUID, "alterId": 0}]},
                "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-argo"}},
            },
            {
                "port": 3004, "listen": "127.0.0.1", "protocol": "trojan",
                "settings": {"clients": [{"password": UUID}]},
                "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/trojan-argo"}},
            },
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
    }
    with open("/root/.tmp/config.json", "w") as f:
        json.dump(config, f)

    subprocess.Popen(["/root/.tmp/web", "-c", "/root/.tmp/config.json"])
    print("✅ Xray started")

    # ---------- Argo ----------
    domain_for_links = ""
    argo_log = "/root/.tmp/argo.log"
    if ARGO_DOMAIN and ARGO_AUTH:
        domain_for_links = ARGO_DOMAIN
        if re.match(r"^[A-Z0-9a-z=]{120,250}$", ARGO_AUTH):
            args = f"tunnel --edge-ip-version auto --no-autoupdate run --token {ARGO_AUTH}"
        elif "TunnelSecret" in ARGO_AUTH:
            with open("/root/.tmp/tunnel.json", "w") as f:
                f.write(ARGO_AUTH)
            tid = json.loads(ARGO_AUTH)["TunnelID"]
            yml = f"""
tunnel: {tid}
credentials-file: /root/.tmp/tunnel.json
protocol: http2
ingress:
  - hostname: {ARGO_DOMAIN}
    service: http://localhost:{ARGO_PORT}
    originRequest:
      noTLSVerify: true
  - service: http_status:404
"""
            with open("/root/.tmp/tunnel.yml", "w") as f:
                f.write(yml)
            args = "tunnel --edge-ip-version auto --config /root/.tmp/tunnel.yml run"
        else:
            raise ValueError("Invalid ARGO_AUTH")
        subprocess.Popen(f"/root/.tmp/bot {args}", shell=True)
        print("✅ Fixed Argo tunnel started")
    else:
        args = f"tunnel --edge-ip-version auto --url http://localhost:{ARGO_PORT}"
        subprocess.Popen(f"/root/.tmp/bot {args} > {argo_log} 2>&1", shell=True)
        time.sleep(10)
        try:
            with open(argo_log) as f:
                log = f.read()
            m = re.search(r"https?://\S+\.trycloudflare\.com", log)
            if m:
                domain_for_links = m.group(0).replace("https://", "").replace("http://", "")
                print(f"✅ Temp tunnel: {domain_for_links}")
            else:
                raise RuntimeError("Cannot parse temp tunnel URL")
        except FileNotFoundError:
            raise RuntimeError("Argo log not found")

    # ---------- 订阅 ----------
    links = generate_links(domain_for_links, NAME, UUID, CFIP, CFPORT)
    subscription_dict["content"] = base64.b64encode(links.encode()).decode()
    print("✅ Subscription saved")

    # ---------- Nezha ----------
    ensure_agent_started()

    # 打印信息
    if MODAL_USER_NAME:
        print(f"订阅地址: https://{MODAL_USER_NAME}--{MODAL_APP_NAME}-web.modal.run/{SUB_PATH}")
    print(f"节点域名: {domain_for_links}")
    print("=" * 50)

    yield
    # 关闭时可选清理
    # subprocess.run("pkill -f web || true", shell=True)
    # subprocess.run("pkill -f bot || true", shell=True)

# ==================== FastAPI ====================
web = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

@web.middleware("http")
async def detect_url(request: Request, call_next):
    auto_detect_url(request)
    return await call_next(request)

@web.get("/")
async def root():
    return HTMLResponse(FAKE_HTML)

@web.get(f"/{SUB_PATH}")
async def subscription():
    content = subscription_dict.get("content")
    if content:
        return Response(content=content, media_type="text/plain")
    return Response("订阅尚未生成，请稍后重试", status_code=503)

@web.get("/health")
async def health():
    return {"status": "healthy", "timestamp": time.time()}

@web.get("/status")
async def status():
    import psutil
    found = []
    names = ["cache_manager", "session_handler", "task_worker", "log_rotator", "health_check"]
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if any(n in cmd or n in (p.info.get("name") or "") for n in names):
                found.append({"pid": p.info["pid"], "name": p.info.get("name")})
        except Exception:
            continue
    return {"agent_status": "running" if found else "not_running", "processes": found}

@web.get("/logs")
async def logs():
    try:
        with open("/tmp/agent.log") as f:
            lines = f.read().splitlines()[-30:]
    except Exception:
        lines = []
    return {"logs": lines}

@web.get("/info")
async def info():
    import psutil
    return {
        "platform": platform.platform(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "region": DEPLOY_REGION,
        "cpu": psutil.cpu_count(),
        "mem_percent": psutil.virtual_memory().percent,
        "pid": os.getpid(),
    }

@web.get("/keepalive")
async def keepalive_status():
    return {
        "started": _keepalive_started,
        "project_url": get_project_url() or "not detected",
        "interval": int(os.environ.get("KEEPALIVE_INTERVAL", "120")),
    }

@web.get("/restart")
async def restart():
    global _agent_started
    import psutil
    killed = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if any(n in cmd for n in ["cache_manager", "session_handler", "task_worker", "log_rotator", "health_check"]):
                psutil.Process(p.info["pid"]).kill()
                killed.append(p.info["pid"])
        except Exception:
            pass
    with _agent_lock:
        _agent_started = False
    time.sleep(1)
    ensure_agent_started()
    return {"killed": killed, "message": "restarted"}

# ==================== Modal 入口 ====================
@app.function(
    secrets=app_secrets,
    timeout=86400,
    min_containers=1,
    scaledown_window=300,
    region=DEPLOY_REGION,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    return web
