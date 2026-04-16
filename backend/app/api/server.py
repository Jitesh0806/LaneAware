"""
FastAPI Server
==============
Endpoints:
  GET  /api/scenario                 -> scenario file contents
  GET  /api/health                   -> {"ok": true}
  WS   /ws/sim?speed=1.0             -> tick stream

Client WebSocket protocol:
  server -> client  {"type": "snapshot", "data": {...}}
  server -> client  {"type": "done",     "data": {...}}
  client -> server  {"cmd": "pause" | "resume" | "reset" | "speed", "value": float}
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..core.lane_graph import LaneGraph
from ..core.robot import Robot
from ..sim.simulation import Simulation

SCENARIO_PATH = Path(__file__).resolve().parent.parent.parent / "scenarios" / "warehouse.json"
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"

app = FastAPI(title="Lane-Aware Multi-Robot Traffic Control")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_scenario() -> dict:
    with open(SCENARIO_PATH) as f:
        return json.load(f)


def _build_sim(scenario: dict) -> Simulation:
    graph = LaneGraph()
    for n in scenario["nodes"]:
        graph.add_node(n["id"], n["x"], n["y"])
    for ln in scenario["lanes"]:
        graph.add_lane(
            u=ln["u"], v=ln["v"],
            max_speed=ln.get("max_speed", 1.0),
            safety_level=ln.get("safety_level", "medium"),
            lane_type=ln.get("lane_type", "normal"),
            directed=ln.get("directed", False),
            critical=ln.get("critical", False),
        )
    robots = [Robot(id=r["id"], start=r["start"], goal=r["goal"]) for r in scenario["robots"]]
    return Simulation(graph=graph, robots=robots, dt=0.25)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/scenario")
async def get_scenario():
    return JSONResponse(_load_scenario())


@app.websocket("/ws/sim")
async def sim_stream(ws: WebSocket):
    await ws.accept()
    scenario = _load_scenario()
    sim = _build_sim(scenario)
    speed_mult = 1.0
    paused = False
    base_period = 0.12  # seconds between ticks at 1x

    # send initial snapshot so UI can render immediately
    await ws.send_json({"type": "snapshot", "data": sim.snapshot()})

    async def receiver():
        nonlocal speed_mult, paused, sim
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    payload = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                cmd = payload.get("cmd")
                if cmd == "pause":
                    paused = True
                elif cmd == "resume":
                    paused = False
                elif cmd == "reset":
                    sim = _build_sim(scenario)
                    await ws.send_json({"type": "snapshot", "data": sim.snapshot()})
                elif cmd == "speed":
                    v = float(payload.get("value", 1.0))
                    speed_mult = max(0.1, min(5.0, v))
        except WebSocketDisconnect:
            return
        except Exception:
            return

    recv_task = asyncio.create_task(receiver())

    try:
        while True:
            if not paused and not sim.all_done():
                sim.step()
                await ws.send_json({"type": "snapshot", "data": sim.snapshot()})
            elif sim.all_done():
                await ws.send_json({"type": "done", "data": sim.snapshot()})
                # keep socket open; allow reset
            await asyncio.sleep(base_period / speed_mult)
    except WebSocketDisconnect:
        pass
    finally:
        recv_task.cancel()


# ---------- serve built frontend (if present) ----------
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/")
    async def _spa_root():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    async def _spa_catchall(full_path: str):
        # don't swallow api/ws routes
        if full_path.startswith(("api/", "ws/", "assets/")):
            return JSONResponse({"detail": "not found"}, status_code=404)
        target = FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
