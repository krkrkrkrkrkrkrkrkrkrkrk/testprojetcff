"""
SCAT Panel — Server
Host this on your VPS. Serves the web UI and relays between client apps and dashboards.
"""
import asyncio
import json
import os
from typing import Dict, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

app = FastAPI()
BASE = os.path.dirname(os.path.abspath(__file__))

# Registry
clients: Dict[str, dict] = {}            # client_id → {ws, status, dashes}
waiting: Dict[str, List[WebSocket]] = {}  # client_id → dashboards waiting for client


def _page(name: str) -> str:
    with open(os.path.join(BASE, "static", name), encoding="utf-8") as f:
        return f.read()


# ── Pages ──────────────────────────────────────────────────
@app.get("/")
async def index():
    return HTMLResponse(_page("index.html"))


@app.get("/panel/{client_id}")
async def panel(client_id: str):
    return HTMLResponse(_page("panel.html"))


@app.get("/download")
async def download():
    exe = os.path.join(BASE, "dist", "SCAT Panel.exe")
    if os.path.exists(exe):
        return FileResponse(
            exe, filename="SCAT Panel.exe", media_type="application/octet-stream"
        )
    return HTMLResponse("<h1>Build not available</h1>", status_code=404)


# ── Helpers ────────────────────────────────────────────────
async def _fwd(targets: list, data):
    """Forward message to list of WebSockets, prune dead ones."""
    msg = data if isinstance(data, str) else json.dumps(data)
    dead = []
    for ws in targets:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in targets:
            targets.remove(ws)


# ── Client WebSocket ──────────────────────────────────────
@app.websocket("/ws/client/{client_id}")
async def ws_client(ws: WebSocket, client_id: str):
    await ws.accept()
    entry = {"ws": ws, "status": {}, "dashes": []}

    # Adopt any dashboards that were already waiting
    for d in waiting.pop(client_id, []):
        entry["dashes"].append(d)
        try:
            await d.send_text(json.dumps({"type": "client_online"}))
        except Exception:
            pass

    clients[client_id] = entry

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            if data.get("type") == "status":
                entry["status"] = data
            # Forward everything to dashboards
            await _fwd(entry["dashes"], raw)
    except WebSocketDisconnect:
        # Tell dashboards the client went offline
        await _fwd(entry.get("dashes", []), {"type": "client_offline"})
        # Move dashboards to waiting list so they reconnect when client comes back
        for d in entry.get("dashes", []):
            waiting.setdefault(client_id, []).append(d)
        clients.pop(client_id, None)


# ── Dashboard WebSocket ───────────────────────────────────
@app.websocket("/ws/dash/{client_id}")
async def ws_dash(ws: WebSocket, client_id: str):
    await ws.accept()

    if client_id in clients:
        clients[client_id]["dashes"].append(ws)
        st = clients[client_id].get("status")
        if st:
            await ws.send_text(json.dumps(st))
        await ws.send_text(json.dumps({"type": "client_online"}))
    else:
        waiting.setdefault(client_id, []).append(ws)
        await ws.send_text(json.dumps({"type": "client_offline"}))

    try:
        while True:
            raw = await ws.receive_text()
            # Forward commands to the client
            if client_id in clients:
                try:
                    await clients[client_id]["ws"].send_text(raw)
                except Exception:
                    await ws.send_text(json.dumps({
                        "type": "log", "level": "error",
                        "message": "Client not responding",
                    }))
            else:
                await ws.send_text(json.dumps({
                    "type": "log", "level": "error",
                    "message": "Client is offline",
                }))
    except WebSocketDisconnect:
        if client_id in clients:
            dd = clients[client_id]["dashes"]
            if ws in dd:
                dd.remove(ws)
        for cid in list(waiting):
            if ws in waiting[cid]:
                waiting[cid].remove(ws)


# ── Entry ──────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("  ╔═══════════════════════════════╗")
    print("  ║     SCAT PANEL  — Server      ║")
    print("  ╠═══════════════════════════════╣")
    print("  ║  http://0.0.0.0:8888          ║")
    print("  ╚═══════════════════════════════╝")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8888)
