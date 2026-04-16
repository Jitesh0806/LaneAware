"""Spins up uvicorn in-process and tests HTTP + WebSocket end-to-end."""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import app


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


async def run_tests():
    # wait for server
    async with httpx.AsyncClient(timeout=3.0) as client:
        for _ in range(20):
            try:
                r = await client.get("http://127.0.0.1:8765/api/health")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)

        r = await client.get("http://127.0.0.1:8765/api/health")
        print(f"health  : {r.status_code}  {r.text}")

        r = await client.get("http://127.0.0.1:8765/")
        print(f"root    : {r.status_code}  {len(r.text)} bytes  starts='{r.text[:40]!r}'")

        r = await client.get("http://127.0.0.1:8765/api/scenario")
        d = r.json()
        print(f"scenario: nodes={len(d['nodes'])} lanes={len(d['lanes'])} robots={len(d['robots'])}")

        # fetch the actual JS asset
        dist = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "assets"
        js = next(dist.glob("*.js"))
        css = next(dist.glob("*.css"))
        r = await client.get(f"http://127.0.0.1:8765/assets/{js.name}")
        print(f"js asset: {r.status_code}  {len(r.content)} bytes")
        r = await client.get(f"http://127.0.0.1:8765/assets/{css.name}")
        print(f"css asset: {r.status_code}  {len(r.content)} bytes")

    # websocket: collect a handful of ticks
    async with websockets.connect("ws://127.0.0.1:8765/ws/sim") as ws:
        ticks = []
        states = set()
        for _ in range(30):
            msg = json.loads(await ws.recv())
            ticks.append(msg["data"]["tick"])
            for r in msg["data"]["robots"]:
                states.add(r["state"])
        print(f"ws ticks : {ticks[:6]} ... {ticks[-3:]}")
        print(f"ws states seen: {sorted(states)}")
        # smoke test: reset command
        await ws.send(json.dumps({"cmd": "reset"}))
        msg = json.loads(await ws.recv())
        print(f"after reset: tick={msg['data']['tick']}")


def main():
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(0.3)
    try:
        asyncio.run(run_tests())
    finally:
        # uvicorn doesn't expose clean shutdown from here; daemon thread will die on exit
        pass
    print("OK")


if __name__ == "__main__":
    main()
