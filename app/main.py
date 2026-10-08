import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import auth, config, history, library, ssh

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SECRET_FIELDS = ("password", "key_data", "key_passphrase", "sudo_password")
SERVER_FIELDS = ("name", "host", "port", "username", "auth", "key_path", "tags", "mac", "sudo_mode") + SECRET_FIELDS
SUDO_MODES = ("none", "ssh", "stored", "ask")
SCRIPT_FIELDS = ("name", "description", "body")

# server id -> {"online": bool, "checked": timestamp}
status: dict[str, dict] = {}


async def status_loop():
    while True:
        cfg = config.load()
        await refresh_status(cfg["servers"])
        await asyncio.sleep(max(5, int(cfg["settings"]["status_interval"])))


async def refresh_status(servers: list[dict]):
    async def check(s):
        online = await ssh.check_online(s["host"], int(s.get("port") or 22))
        status[s["id"]] = {"online": online, "checked": time.time()}

    await asyncio.gather(*(check(s) for s in servers))


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_data_dir()
    config.load()
    history.init()
    task = asyncio.create_task(status_loop())
    yield
    task.cancel()


app = FastAPI(title="Rackoon", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- auth -----------------------------------------------------------------

PUBLIC_PATHS = {"/api/auth/state", "/api/auth/setup", "/api/auth/login"}


def is_logged_in(cookies) -> bool:
    cfg = config.load()
    return auth.check_token(cookies.get(auth.COOKIE_NAME), cfg["auth"]["secret"], cfg["auth"]["password_hash"])


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_PATHS and not is_logged_in(request.cookies):
        return JSONResponse({"detail": "Not logged in"}, status_code=401)
    return await call_next(request)


def set_session(request: Request, response: Response, cfg: dict):
    token = auth.make_token(cfg["auth"]["secret"], cfg["auth"]["password_hash"])
    response.set_cookie(
        auth.COOKIE_NAME, token, max_age=auth.SESSION_TTL, httponly=True, samesite="strict",
        secure=request.url.scheme == "https",
    )


@app.get("/api/auth/state")
def auth_state(request: Request):
    cfg = config.load()
    return {
        "setup_required": not cfg["auth"]["password_hash"],
        "logged_in": is_logged_in(request.cookies),
    }


@app.post("/api/auth/setup")
async def auth_setup(request: Request, response: Response):
    cfg = config.load()
    if cfg["auth"]["password_hash"]:
        raise HTTPException(400, "Password already set")
    password = (await request.json()).get("password", "")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    cfg["auth"]["password_hash"] = auth.hash_password(password)
    config.save(cfg)
    set_session(request, response, cfg)
    return {"ok": True}


@app.post("/api/auth/login")
async def auth_login(request: Request, response: Response):
    cfg = config.load()
    password = (await request.json()).get("password", "")
    if not auth.verify_password(password, cfg["auth"]["password_hash"]):
        await asyncio.sleep(1)  # slow down guessing
        raise HTTPException(401, "Wrong password")
    set_session(request, response, cfg)
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)
    return {"ok": True}


@app.post("/api/auth/password")
async def auth_change_password(request: Request, response: Response):
    data = await request.json()
    cfg = config.load()
    if not auth.verify_password(data.get("current", ""), cfg["auth"]["password_hash"]):
        raise HTTPException(400, "Current password is wrong")
    if len(data.get("new", "")) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    cfg["auth"]["password_hash"] = auth.hash_password(data["new"])
    config.save(cfg)
    set_session(request, response, cfg)
    return {"ok": True}


# --- servers ----------------------------------------------------------------


def public_server(s: dict) -> dict:
    out = {k: v for k, v in s.items() if k not in SECRET_FIELDS}
    out["has_password"] = bool(s.get("password"))
    out["has_key_data"] = bool(s.get("key_data"))
    out["has_sudo_password"] = bool(s.get("sudo_password"))
    out["status"] = status.get(s["id"])
    return out


def apply_server_fields(server: dict, data: dict):
    for key in SERVER_FIELDS:
        if key not in data:
            continue
        # Secrets are write-only: an empty value from the UI means "keep".
        if key in SECRET_FIELDS and not data[key]:
            continue
        server[key] = data[key]
    if not server.get("name") or not server.get("host"):
        raise HTTPException(400, "Name and host are required")
    server["port"] = int(server.get("port") or 22)
    server.setdefault("auth", "default")
    if server.get("sudo_mode", "none") not in SUDO_MODES:
        raise HTTPException(400, "Invalid sudo mode")
    if server.get("sudo_mode") != "stored":
        server.pop("sudo_password", None)  # don't keep a secret that isn't used


def find(items: list[dict], item_id: str) -> dict:
    for item in items:
        if item["id"] == item_id:
            return item
    raise HTTPException(404, "Not found")


@app.get("/api/servers")
def list_servers():
    return [public_server(s) for s in config.load()["servers"]]


@app.post("/api/servers")
async def create_server(request: Request):
    cfg = config.load()
    server = {"id": config.new_id()}
    apply_server_fields(server, await request.json())
    cfg["servers"].append(server)
    config.save(cfg)
    asyncio.create_task(refresh_status([server]))
    return public_server(server)


@app.put("/api/servers/{server_id}")
async def update_server(server_id: str, request: Request):
    cfg = config.load()
    server = find(cfg["servers"], server_id)
    apply_server_fields(server, await request.json())
    config.save(cfg)
    asyncio.create_task(refresh_status([server]))
    return public_server(server)


@app.delete("/api/servers/{server_id}")
def delete_server(server_id: str):
    cfg = config.load()
    cfg["servers"] = [s for s in cfg["servers"] if s["id"] != server_id]
    config.save(cfg)
    status.pop(server_id, None)
    return {"ok": True}


@app.get("/api/servers/{server_id}/stats")
async def server_stats(server_id: str):
    cfg = config.load()
    server = find(cfg["servers"], server_id)
    try:
        return await ssh.get_stats(server, cfg["settings"]["ssh_timeout"])
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.get("/api/servers/{server_id}/details")
async def server_details(server_id: str):
    cfg = config.load()
    server = find(cfg["servers"], server_id)
    try:
        return await ssh.get_details(server, cfg["settings"]["ssh_timeout"])
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.post("/api/servers/{server_id}/wake")
def server_wake(server_id: str):
    server = find(config.load()["servers"], server_id)
    if not server.get("mac"):
        raise HTTPException(400, "No MAC address set for this server")
    try:
        ssh.wake_on_lan(server["mac"])
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/status/refresh")
async def status_refresh():
    await refresh_status(config.load()["servers"])
    return status


# --- scripts ----------------------------------------------------------------


@app.get("/api/scripts")
def list_scripts():
    return config.load()["scripts"]


def apply_script_fields(script: dict, data: dict):
    for key in SCRIPT_FIELDS:
        if key in data:
            script[key] = data[key]
    if not script.get("name") or not script.get("body"):
        raise HTTPException(400, "Name and script body are required")


@app.get("/api/library")
def get_library():
    return library.LIBRARY


@app.post("/api/scripts")
async def create_script(request: Request):
    cfg = config.load()
    script = {"id": config.new_id()}
    apply_script_fields(script, await request.json())
    cfg["scripts"].append(script)
    config.save(cfg)
    return script


@app.put("/api/scripts/{script_id}")
async def update_script(script_id: str, request: Request):
    cfg = config.load()
    script = find(cfg["scripts"], script_id)
    apply_script_fields(script, await request.json())
    config.save(cfg)
    return script


@app.delete("/api/scripts/{script_id}")
def delete_script(script_id: str):
    cfg = config.load()
    cfg["scripts"] = [s for s in cfg["scripts"] if s["id"] != script_id]
    config.save(cfg)
    return {"ok": True}


# --- running ----------------------------------------------------------------


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    """Client sends {script_id | command, server_ids, args, sudo_passwords: {server_id: pw}};
    we stream back events:
    {type: "start"|"output"|"done"|"error", server_id, ...}."""
    await ws.accept()
    if not is_logged_in(ws.cookies):
        await ws.close(code=4401)
        return
    try:
        req = await ws.receive_json()
        cfg = config.load()
        if req.get("command"):
            script = {"name": "Ad-hoc command", "body": req["command"]}
        else:
            script = find(cfg["scripts"], req["script_id"])
        servers = [find(cfg["servers"], sid) for sid in req.get("server_ids", [])]
    except (HTTPException, KeyError, json.JSONDecodeError):
        await ws.send_json({"type": "error", "message": "Invalid request"})
        await ws.close()
        return

    typed_passwords = req.get("sudo_passwords") or {}

    def sudo_password_for(server: dict) -> str | None:
        mode = server.get("sudo_mode", "none")
        if mode == "ssh" and server.get("auth") == "password":
            return server.get("password")
        if mode == "stored":
            return server.get("sudo_password")
        if mode == "ask":
            return typed_passwords.get(server["id"])
        return None

    send_lock = asyncio.Lock()

    async def send(msg):
        async with send_lock:
            await ws.send_json(msg)

    async def run_on(server):
        sid = server["id"]
        run_id = history.start(script["name"], server["name"], server["host"])
        output: list[str] = []
        sudo_password = sudo_password_for(server)
        await send({"type": "start", "server_id": sid, "run_id": run_id})

        async def on_output(stream, text):
            if sudo_password:  # in case a script echoes it
                text = text.replace(sudo_password, "********")
            output.append(text)
            await send({"type": "output", "server_id": sid, "stream": stream, "data": text})

        exit_code = None
        try:
            exit_code = await ssh.run_script(
                server, script["body"], req.get("args", ""), on_output, cfg["settings"]["ssh_timeout"],
                sudo_password,
            )
            await send({"type": "done", "server_id": sid, "exit_code": exit_code})
        except asyncio.CancelledError:
            output.append("\n[stopped]\n")
            raise
        except WebSocketDisconnect:
            raise
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            output.append(f"\n[connection error] {msg}\n")
            await send({"type": "error", "server_id": sid, "message": msg})
        finally:
            history.finish(run_id, exit_code, "".join(output))

    runs = asyncio.gather(*(run_on(s) for s in servers))

    async def cancel_on_disconnect():
        # The Stop button (or closing the tab) closes the socket.
        try:
            while (await ws.receive())["type"] != "websocket.disconnect":
                pass
        except Exception:
            pass
        runs.cancel()

    watcher = asyncio.create_task(cancel_on_disconnect())
    try:
        await runs
        await ws.close()
    except (asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
        pass  # browser went away; history is still saved
    finally:
        watcher.cancel()


# --- history ----------------------------------------------------------------


@app.get("/api/history")
def get_history(limit: int = 100):
    return history.list_runs(limit)


@app.get("/api/history/{run_id}")
def get_history_run(run_id: int):
    run = history.get_run(run_id)
    if not run:
        raise HTTPException(404, "Not found")
    return run


@app.delete("/api/history")
def clear_history():
    history.clear()
    return {"ok": True}


# --- settings & config transfer ---------------------------------------------


@app.get("/api/settings")
def get_settings():
    return config.load()["settings"]


@app.put("/api/settings")
async def put_settings(request: Request):
    data = await request.json()
    cfg = config.load()
    for key in config.DEFAULT_SETTINGS:
        if key in data:
            cfg["settings"][key] = max(1, int(data[key]))
    config.save(cfg)
    return cfg["settings"]


@app.get("/api/config/export")
def export_config():
    cfg = config.load()
    # The login password is not exported; the target machine keeps its own.
    data = {k: v for k, v in cfg.items() if k != "auth"}
    filename = f"rackoon-{time.strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/config/import")
async def import_config(file: UploadFile = File(...), mode: str = "replace"):
    try:
        data = json.loads(await file.read())
        servers, scripts = data.get("servers", []), data.get("scripts", [])
        assert isinstance(servers, list) and isinstance(scripts, list)
    except Exception:
        raise HTTPException(400, "Not a valid Rackoon export")
    cfg = config.load()
    if mode == "merge":
        # Imported items win when ids collide.
        for key, items in (("servers", servers), ("scripts", scripts)):
            incoming = {i["id"] for i in items}
            cfg[key] = [i for i in cfg[key] if i["id"] not in incoming] + items
    else:
        cfg["servers"], cfg["scripts"] = servers, scripts
    if isinstance(data.get("settings"), dict):
        cfg["settings"].update(data["settings"])
    for item in cfg["servers"] + cfg["scripts"]:
        item.setdefault("id", config.new_id())
    config.save(cfg)
    status.clear()
    asyncio.create_task(refresh_status(cfg["servers"]))
    return {"servers": len(cfg["servers"]), "scripts": len(cfg["scripts"])}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
