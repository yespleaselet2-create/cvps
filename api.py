#!/usr/bin/env python3
# CVPS API — Made by @radoslavgeme
from flask import Flask, request, jsonify
from flask_cors import CORS
import json, os, subprocess, bcrypt, jwt, datetime, time, psutil, re

app = Flask(__name__)
CORS(app)
SECRET = "cvps_secret_changeme"
DB = "/opt/cvps/data/db.json"
LOG = "/opt/cvps/logs/cvps.log"
VERSION = "1.0.0"

def load_db():
    with open(DB) as f: return json.load(f)

def save_db(db):
    with open(DB, "w") as f: json.dump(db, f, indent=2)

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a") as f: f.write(f"[{ts}] {msg}\n")

def auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization","").replace("Bearer ","")
        try:
            data = jwt.decode(token, SECRET, algorithms=["HS256"])
            request.user = data["username"]
            request.role = data["role"]
        except: return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization","").replace("Bearer ","")
        try:
            data = jwt.decode(token, SECRET, algorithms=["HS256"])
            if data["role"] != "admin": return jsonify({"error": "Admin only"}), 403
            request.user = data["username"]
            request.role = data["role"]
        except: return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def lxc_run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def get_container_ip(name):
    out, _, _ = lxc_run(f"lxc-info -n {name} -iH")
    return out.strip() or "-"

def container_status(name):
    out, _, _ = lxc_run(f"lxc-info -n {name} -sH")
    return out.strip().lower() or "stopped"

@app.route("/auth/login", methods=["POST"])
def login():
    d = request.json
    db = load_db()
    u = db["users"].get(d.get("username",""))
    if not u: return jsonify({"error": "Invalid credentials"}), 401
    if not bcrypt.checkpw(d.get("password","").encode(), u["password"].encode()):
        return jsonify({"error": "Invalid credentials"}), 401
    token = jwt.encode({"username": d["username"], "role": u["role"],
        "exp": datetime.datetime.utcnow()+datetime.timedelta(days=7)}, SECRET)
    log(f"LOGIN {d['username']}")
    return jsonify({"token": token})

@app.route("/auth/me")
@auth_required
def me():
    db = load_db()
    u = db["users"][request.user]
    return jsonify({"username": request.user, "role": request.role, "containers": u.get("containers",[])})

@app.route("/auth/passwd", methods=["POST"])
@auth_required
def passwd():
    d = request.json
    db = load_db()
    pw = bcrypt.hashpw(d["password"].encode(), bcrypt.gensalt()).decode()
    db["users"][request.user]["password"] = pw
    save_db(db); log(f"PASSWD {request.user}")
    return jsonify({"message": "Password changed"})

@app.route("/containers/create", methods=["POST"])
@auth_required
def create():
    d = request.json
    name = re.sub(r"[^a-z0-9-]","",d["name"].lower())
    ram = int(d["ram"]); cpus = int(d["cpus"]); disk = int(d["disk"])
    db = load_db()
    user = db["users"][request.user]
    limit = user.get("max_containers", 10)
    if len(user.get("containers",[])) >= limit:
        return jsonify({"error": f"Container limit reached ({limit})"}), 400
    if name in db["containers"]:
        return jsonify({"error": "Name already exists"}), 400
    log(f"CREATE {name} by {request.user}")
    lxc_run(f"lxc-create -n {name} -t download -- -d ubuntu -r jammy -a amd64")
    cfg = f"/var/lib/lxc/{name}/config"
    with open(cfg, "a") as f:
        f.write(f"\nlxc.cgroup2.memory.max = {ram}M\n")
        f.write(f"lxc.cgroup2.cpu.weight = {cpus * 100}\n")
    lxc_run(f"lxc-start -n {name}")
    time.sleep(3)
    ip = get_container_ip(name)
    db["containers"][name] = {"name":name,"ram":ram,"cpus":cpus,"disk":disk,"ip":ip,"owner":request.user,"ports":[],"status":"running"}
    db["users"][request.user].setdefault("containers",[]).append(name)
    save_db(db)
    return jsonify(db["containers"][name])

@app.route("/containers/list")
@auth_required
def list_containers():
    db = load_db()
    if request.role == "admin":
        containers = list(db["containers"].values())
    else:
        containers = [db["containers"][n] for n in db["users"][request.user].get("containers",[]) if n in db["containers"]]
    for c in containers:
        c["status"] = container_status(c["name"])
        c["ip"] = get_container_ip(c["name"])
    return jsonify(containers)

@app.route("/containers/<name>/info")
@auth_required
def info(name):
    db = load_db()
    c = db["containers"].get(name)
    if not c: return jsonify({"error": "Not found"}), 404
    if request.role != "admin" and c["owner"] != request.user:
        return jsonify({"error": "Access denied"}), 403
    c["status"] = container_status(name)
    c["ip"] = get_container_ip(name)
    return jsonify(c)

@app.route("/containers/<name>/start", methods=["POST"])
@auth_required
def start(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    if request.role!="admin" and c["owner"]!=request.user: return jsonify({"error":"Access denied"}),403
    lxc_run(f"lxc-start -n {name}")
    log(f"START {name} by {request.user}")
    return jsonify({"message": f"{name} started"})

@app.route("/containers/<name>/stop", methods=["POST"])
@auth_required
def stop(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    if request.role!="admin" and c["owner"]!=request.user: return jsonify({"error":"Access denied"}),403
    lxc_run(f"lxc-stop -n {name}")
    log(f"STOP {name} by {request.user}")
    return jsonify({"message": f"{name} stopped"})

@app.route("/containers/<name>", methods=["DELETE"])
@auth_required
def delete(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    if request.role!="admin" and c["owner"]!=request.user: return jsonify({"error":"Access denied"}),403
    lxc_run(f"lxc-stop -n {name} -k")
    lxc_run(f"lxc-destroy -n {name}")
    del db["containers"][name]
    for u in db["users"].values():
        if name in u.get("containers",[]): u["containers"].remove(name)
    save_db(db); log(f"DELETE {name} by {request.user}")
    return jsonify({"message": f"{name} deleted"})

@app.route("/containers/<name>/exec", methods=["POST"])
@auth_required
def exec_cmd(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    if request.role!="admin" and c["owner"]!=request.user: return jsonify({"error":"Access denied"}),403
    cmd = request.json.get("cmd","")
    out, err, _ = lxc_run(f"lxc-attach -n {name} -- /bin/sh -c {repr(cmd)}")
    return jsonify({"output": out or err})

@app.route("/containers/<name>/stats")
@auth_required
def stats(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    try:
        cpu_out, _, _ = lxc_run(f"cat /sys/fs/cgroup/lxc.payload.{name}/cpu.stat 2>/dev/null || echo usage_usec 0")
        mem_out, _, _ = lxc_run(f"cat /sys/fs/cgroup/lxc.payload.{name}/memory.current 2>/dev/null || echo 0")
        ram_used = int(mem_out.strip() or 0) // (1024*1024)
        return jsonify({"cpu":0,"ram_used":ram_used,"ram_total":c["ram"],"disk_used":0,"disk_total":c["disk"],"net_tx":"0B","net_rx":"0B"})
    except: return jsonify({"cpu":0,"ram_used":0,"ram_total":c["ram"],"disk_used":0,"disk_total":c["disk"],"net_tx":"0B","net_rx":"0B"})

@app.route("/containers/<name>/port", methods=["POST"])
@auth_required
def add_port(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    if request.role!="admin" and c["owner"]!=request.user: return jsonify({"error":"Access denied"}),403
    hp = request.json["host_port"]; cp = request.json["cont_port"]
    ip = c.get("ip","-")
    lxc_run(f"iptables -t nat -A PREROUTING -p tcp --dport {hp} -j DNAT --to-destination {ip}:{cp}")
    lxc_run(f"iptables -A FORWARD -p tcp -d {ip} --dport {cp} -j ACCEPT")
    c["ports"].append({"host_port":hp,"cont_port":cp})
    save_db(db); log(f"PORT {name} {hp}->{cp} by {request.user}")
    return jsonify({"message":f"Port {hp} -> {cp} forwarded"})

@app.route("/containers/<name>/ports")
@auth_required
def list_ports(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    return jsonify({"ports": c.get("ports",[])})

@app.route("/containers/<name>/port/<int:host_port>", methods=["DELETE"])
@auth_required
def del_port(name, host_port):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    c["ports"] = [p for p in c.get("ports",[]) if p["host_port"]!=host_port]
    save_db(db)
    return jsonify({"message":f"Port {host_port} removed"})

@app.route("/containers/<name>/resize", methods=["POST"])
@auth_required
def resize(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    if request.role!="admin" and c["owner"]!=request.user: return jsonify({"error":"Access denied"}),403
    ram=int(request.json["ram"]); cpus=int(request.json["cpus"]); disk=int(request.json["disk"])
    lxc_run(f"lxc-cgroup -n {name} memory.limit_in_bytes {ram}M")
    c.update({"ram":ram,"cpus":cpus,"disk":disk}); save_db(db)
    log(f"RESIZE {name} ram={ram} cpu={cpus} disk={disk} by {request.user}")
    return jsonify({"message":f"{name} resized"})

@app.route("/containers/<name>/snapshot", methods=["POST"])
@auth_required
def snapshot(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snap = f"{name}_{ts}"
    lxc_run(f"lxc-snapshot -n {name} -s {snap}")
    log(f"SNAPSHOT {name} -> {snap} by {request.user}")
    return jsonify({"message":f"Snapshot {snap} created"})

@app.route("/containers/<name>/restore", methods=["POST"])
@auth_required
def restore(name):
    snap = request.json.get("snapshot","")
    lxc_run(f"lxc-snapshot -n {name} -r {snap}")
    log(f"RESTORE {name} from {snap}")
    return jsonify({"message":f"Restored from {snap}"})

@app.route("/system/status")
def system_status():
    db = load_db()
    running = sum(1 for n in db["containers"] if container_status(n)=="running")
    mem = psutil.virtual_memory()
    return jsonify({
        "version": VERSION,
        "running": running,
        "total": len(db["containers"]),
        "users": len(db["users"]),
        "host_ram_used": mem.used//(1024*1024),
        "host_ram_total": mem.total//(1024*1024),
        "host_cpu": psutil.cpu_percent(interval=1),
        "uptime": os.popen("uptime -p").read().strip()
    })

@app.route("/admin/users", methods=["GET"])
@admin_required
def admin_list_users():
    db = load_db()
    return jsonify([{"username":k,"role":v["role"],"containers":v.get("containers",[])} for k,v in db["users"].items()])

@app.route("/admin/users", methods=["POST"])
@admin_required
def admin_add_user():
    d = request.json; db = load_db()
    if d["username"] in db["users"]: return jsonify({"error":"User exists"}),400
    pw = bcrypt.hashpw(d["password"].encode(), bcrypt.gensalt()).decode()
    db["users"][d["username"]] = {"password":pw,"role":"user","containers":[],"max_containers":5}
    save_db(db); log(f"USERADD {d['username']} by {request.user}")
    return jsonify({"message":f"User {d['username']} created"})

@app.route("/admin/users/<username>", methods=["DELETE"])
@admin_required
def admin_del_user(username):
    db = load_db()
    if username not in db["users"]: return jsonify({"error":"Not found"}),404
    if username == "admin": return jsonify({"error":"Cannot delete admin"}),400
    del db["users"][username]; save_db(db)
    log(f"USERDEL {username} by {request.user}")
    return jsonify({"message":f"User {username} deleted"})

@app.route("/admin/users/<username>/limit", methods=["POST"])
@admin_required
def admin_set_limit(username):
    db = load_db()
    db["users"][username]["max_containers"] = int(request.json["max_containers"])
    save_db(db)
    return jsonify({"message":"Limit updated"})

@app.route("/admin/containers/<name>/transfer", methods=["POST"])
@admin_required
def admin_transfer(name):
    db = load_db(); c = db["containers"].get(name)
    if not c: return jsonify({"error":"Not found"}),404
    to = request.json["to"]
    if to not in db["users"]: return jsonify({"error":"User not found"}),404
    old = c["owner"]
    if name in db["users"][old].get("containers",[]): db["users"][old]["containers"].remove(name)
    db["users"][to].setdefault("containers",[]).append(name)
    c["owner"] = to; save_db(db)
    return jsonify({"message":f"Transferred {name} to {to}"})

@app.route("/admin/logs")
@admin_required
def admin_logs():
    try:
        with open(LOG) as f: lines = f.readlines()[-100:]
        return jsonify({"logs":[l.strip() for l in lines]})
    except: return jsonify({"logs":[]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7821, debug=False)
