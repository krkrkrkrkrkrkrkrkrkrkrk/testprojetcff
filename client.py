"""
SCAT Panel — Client App
Compile to .exe and distribute to customers.
"""
import asyncio
import json
import os
import sys
import ctypes
import uuid
import webbrowser
import threading

import websockets
from beyondmem import MemFurqan

# ╔══════════════════════════════════════════════════╗
# ║  SET YOUR SERVER ADDRESS BEFORE BUILDING         ║
# ╚══════════════════════════════════════════════════╝
SERVER = "localhost:8888"
# ═══════════════════════════════════════════════════

AIMBOT_AOB = (
    "FF FF FF FF FF FF FF FF 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
    "?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? "
    "?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? "
    "?? ?? ?? ?? ?? "
    "00 00 00 00 00 00 00 00 00 00 00 00 A5 43"
)

mem = MemFurqan()

state = {
    "connected": False,
    "process": "HD-Player",
    "pid": 0,
    "scanning": False,
    "auto_inject": False,
    "target_offset": 0x80,
    "write_offset": 0x7C,
    "total_injections": 0,
    "last_entities": 0,
}


# ── Persistent ID ──────────────────────────────────────────
def get_id():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, ".scat_id")
    if os.path.exists(path):
        with open(path) as f:
            cid = f.read().strip()
            if cid:
                return cid
    cid = uuid.uuid4().hex[:10]
    with open(path, "w") as f:
        f.write(cid)
    return cid


CLIENT_ID = get_id()
PANEL_URL = f"http://{SERVER}/panel/{CLIENT_ID}"
WS_URL = f"ws://{SERVER}/ws/client/{CLIENT_ID}"


# ── Helpers ────────────────────────────────────────────────
async def send(ws, data):
    await ws.send(json.dumps(data))


async def log(ws, lvl, msg):
    await send(ws, {"type": "log", "level": lvl, "message": msg})


async def push(ws):
    p = {"type": "status"}
    for k, v in state.items():
        p[k] = hex(v) if k.endswith("_offset") else v
    await send(ws, p)


# ── Actions ────────────────────────────────────────────────
async def do_connect(ws, proc):
    state["process"] = proc
    await log(ws, "info", f"Connecting to {proc}...")
    ok = await asyncio.to_thread(mem.open_process_by_name, proc)
    if ok:
        state["connected"] = True
        state["pid"] = mem.the_proc_id
        await log(ws, "success", f"Connected — PID {mem.the_proc_id}")
    else:
        state["connected"] = False
        state["pid"] = 0
        await log(ws, "error", f"Process '{proc}' not found")
    await push(ws)


async def do_disconnect(ws):
    await asyncio.to_thread(mem.close_process)
    state.update(connected=False, pid=0, auto_inject=False, scanning=False)
    await log(ws, "info", "Disconnected")
    await push(ws)


async def do_inject(ws):
    if not state["connected"]:
        await log(ws, "error", "Not connected")
        return
    if state["scanning"]:
        await log(ws, "warning", "Scan in progress")
        return

    state["scanning"] = True
    await push(ws)
    await log(ws, "info", "Scanning memory for entities...")

    try:
        found = await asyncio.to_thread(
            mem.AoBScan, 0x10000, 0x7FFFFFEFFFF, AIMBOT_AOB
        )
        if not found:
            await log(ws, "warning", "No entities found")
            return

        await log(ws, "info", f"Found {len(found)} addresses — injecting...")
        count = 0
        for base in found:
            try:
                src = base + state["target_offset"]
                dst = base + state["write_offset"]
                val = mem.read_bytes(src, 4)
                if val and mem._write_raw(dst, val):
                    count += 1
            except Exception:
                continue

        state["last_entities"] = count
        state["total_injections"] += count
        if count:
            await log(ws, "success", f"Aimbot applied to {count} entities ✓")
        else:
            await log(ws, "warning", "No writable entities found")
    except Exception as e:
        await log(ws, "error", f"Error: {e}")
    finally:
        state["scanning"] = False
        await push(ws)


async def auto_loop(ws):
    while state["auto_inject"] and state["connected"]:
        await do_inject(ws)
        await asyncio.sleep(2.5)
    state["auto_inject"] = False
    await push(ws)


async def handle(ws, data):
    a = data.get("action")
    if a == "connect":
        await do_connect(ws, data.get("process", "HD-Player"))
    elif a == "disconnect":
        await do_disconnect(ws)
    elif a == "inject":
        asyncio.create_task(do_inject(ws))
    elif a == "auto_inject":
        state["auto_inject"] = data.get("enabled", False)
        await push(ws)
        if state["auto_inject"]:
            await log(ws, "info", "Auto-inject ON (2.5 s)")
            asyncio.create_task(auto_loop(ws))
        else:
            await log(ws, "info", "Auto-inject OFF")
    elif a == "config":
        try:
            for k in ("target_offset", "write_offset"):
                if k in data:
                    v = data[k]
                    state[k] = int(v, 16) if isinstance(v, str) else v
            await log(
                ws, "info",
                f"Config → Target: {hex(state['target_offset'])}, "
                f"Write: {hex(state['write_offset'])}",
            )
            await push(ws)
        except Exception as e:
            await log(ws, "error", f"Bad config: {e}")


# ── Main ───────────────────────────────────────────────────
async def main():
    os.system("cls" if os.name == "nt" else "clear")
    print()
    print("  ╔═══════════════════════════════════════╗")
    print("  ║            SCAT PANEL  v2.0           ║")
    print("  ╠═══════════════════════════════════════╣")
    print(f"  ║  ID:     {CLIENT_ID:<28s} ║")
    print(f"  ║  Server: {SERVER:<28s} ║")
    print("  ╚═══════════════════════════════════════╝")
    print()
    print(f"  Panel URL: {PANEL_URL}")
    print()

    threading.Timer(1.5, lambda: webbrowser.open(PANEL_URL)).start()

    while True:
        try:
            print("  Connecting to server...")
            async with websockets.connect(WS_URL) as ws:
                print("  ● Connected — keep this window open\n")
                await push(ws)
                await log(ws, "info", "Client connected and ready")
                async for msg in ws:
                    await handle(ws, json.loads(msg))
        except KeyboardInterrupt:
            print("\n  Shutting down.")
            break
        except Exception:
            print("  ○ Connection lost — retrying in 3 s...")
            await asyncio.sleep(3)


# ── Admin + entry ──────────────────────────────────────────
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


if __name__ == "__main__":
    if not is_admin():
        if getattr(sys, "frozen", False):
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, "", None, 1
            )
        else:
            script = os.path.abspath(__file__)
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}"', None, 1
            )
        sys.exit(0)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
