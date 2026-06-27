#!/bin/bash
# CVPS Installer — Made by @radoslavgeme
set -e
RED='\033[0;31m';GREEN='\033[0;32m';YELLOW='\033[1;33m';CYAN='\033[0;36m';BOLD='\033[1m';NC='\033[0m'
log(){ echo -e "${GREEN}[CVPS]${NC} $1"; }
err(){ echo -e "${RED}[ERR]${NC} $1"; exit 1; }

echo -e "${CYAN}${BOLD}"
echo "  ██████╗██╗   ██╗██████╗ ███████╗"
echo "  ██╔════╝██║   ██║██╔══██╗██╔════╝"
echo "  ██║     ██║   ██║██████╔╝███████╗"
echo "  ██║     ╚██╗ ██╔╝██╔═══╝ ╚════██║"
echo "  ╚██████╗ ╚████╔╝ ██║     ███████║"
echo "   ╚═════╝  ╚═══╝  ╚═╝     ╚══════╝"
echo -e "${NC}  Made by ${YELLOW}@radoslavgeme${NC}\n"

[[ $EUID -ne 0 ]] && err "Run as root: sudo bash install.sh"

log "Installing system deps..."
apt-get update -qq
apt-get install -y -qq lxc lxc-utils lxc-templates uidmap python3 python3-pip nginx curl jq net-tools iptables

log "Installing Python deps..."
pip3 install flask flask-cors bcrypt pyjwt discord.py psutil --break-system-packages -q

log "Setting up directories..."
mkdir -p /opt/cvps/{data,logs,panel}

log "Downloading CVPS files..."
BASE="https://raw.githubusercontent.com/yespleaselet2-create/cvps/main"
curl -sSL "$BASE/cvps" -o /usr/local/bin/cvps && chmod +x /usr/local/bin/cvps
curl -sSL "$BASE/api.py" -o /opt/cvps/api.py
curl -sSL "$BASE/bot.py" -o /opt/cvps/bot.py
curl -sSL "$BASE/panel/index.html" -o /opt/cvps/panel/index.html

log "Initializing database..."
python3 - << 'PYEOF'
import json, bcrypt, os
db_path = "/opt/cvps/data/db.json"
if not os.path.exists(db_path):
    pw = bcrypt.hashpw(b"techoblade", bcrypt.gensalt()).decode()
    db = {"users":{"admin":{"password":pw,"role":"admin","containers":[],"max_containers":999}},"containers":{},"settings":{"version":"1.0.0"}}
    with open(db_path,"w") as f: json.dump(db,f,indent=2)
    print("  DB initialized — admin / techoblade")
else:
    print("  DB already exists, skipping")
PYEOF

log "Setting up nginx..."
cat > /etc/nginx/sites-available/cvps << 'NGINXEOF'
server {
    listen 80;
    server_name _;
    root /opt/cvps/panel;
    index index.html;
    location /api/ {
        proxy_pass http://127.0.0.1:7821/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location / { try_files $uri $uri/ /index.html; }
}
NGINXEOF
ln -sf /etc/nginx/sites-available/cvps /etc/nginx/sites-enabled/cvps
rm -f /etc/nginx/sites-enabled/default
nginx -t -q && systemctl reload nginx

log "Setting up systemd services..."
cat > /etc/systemd/system/cvps-api.service << 'SVCEOF'
[Unit]
Description=CVPS API
After=network.target
[Service]
ExecStart=/usr/bin/python3 /opt/cvps/api.py
WorkingDirectory=/opt/cvps
Restart=always
RestartSec=3
EnvironmentFile=-/opt/cvps/.env
[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/cvps-bot.service << 'SVCEOF'
[Unit]
Description=CVPS Discord Bot
After=network.target cvps-api.service
[Service]
ExecStart=/usr/bin/python3 /opt/cvps/bot.py
WorkingDirectory=/opt/cvps
Restart=always
RestartSec=5
EnvironmentFile=/opt/cvps/.env
[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable cvps-api --now
log "CVPS API started"

if [[ -f /opt/cvps/.env ]] && grep -q "DISCORD_TOKEN" /opt/cvps/.env; then
    systemctl enable cvps-bot --now
    log "Discord bot started"
else
    echo -e "${YELLOW}  No .env found — bot not started${NC}"
    echo -e "${YELLOW}  Create /opt/cvps/.env with:${NC}"
    echo "  DISCORD_TOKEN=your_token_here"
    echo "  CVPS_ADMIN_TOKEN=your_admin_jwt_here"
fi

echo ""
echo -e "${GREEN}${BOLD}CVPS installed!${NC}"
echo -e "  Panel:    ${CYAN}http://$(curl -s ifconfig.me)${NC}"
echo -e "  Login:    ${CYAN}admin / techoblade${NC}"
echo -e "  CLI:      ${CYAN}cvps help${NC}"
echo -e "  API:      ${CYAN}http://localhost:7821${NC}"
echo -e "  Made by   ${YELLOW}@radoslavgeme${NC}"
