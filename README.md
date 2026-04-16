# Lane-Aware Multi-Robot Traffic Control

A fullstack simulation & control console for coordinating multiple robots in
a structured environment (warehouse / factory) under lane-based traffic rules,
congestion awareness, reservations, and deadlock handling.

- **Backend:** Python · FastAPI · async WebSocket
- **Frontend:** React 18 · Vite · Canvas · (no component library — custom industrial UI)
- **Transport:** `WebSocket /ws/sim` streams simulation snapshots in real time

---

## Quick start

Two scripts, two terminals, two minutes.

```bash
# 1. backend
cd backend
pip install -r requirements.txt
bash run.sh            # http://localhost:8000
```

```bash
# 2. frontend — dev mode (hot reload, vite proxy -> backend)
cd frontend
npm install
npm run dev            # http://localhost:5173
```

Or, for a **single-port deploy**, build the frontend and let FastAPI serve it:

```bash
cd frontend && npm install && npm run build
cd ../backend && bash run.sh
# open http://localhost:8000 — UI + API + WS all on one port
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  React Console                                          │
│    MapCanvas · TelemetryPanel · FleetPanel · EventLog   │
│                          │                              │
│                    WebSocket /ws/sim                    │
└──────────────────────────┼──────────────────────────────┘
                           │ snapshot {tick, robots,
                           │           graph, coord, metrics}
┌──────────────────────────┼──────────────────────────────┐
│  FastAPI Server          ▼                              │
│    ┌─────────────────────────────────────────────┐      │
│    │  Simulation (0.25 s/tick async loop)        │      │
│    │    ├─ plan_path()     ← lane-aware A*       │      │
│    │    ├─ Coordinator     ← reservations,       │      │
│    │    │                    wait-for graph,     │      │
│    │    │                    deadlock detect     │      │
│    │    └─ LaneGraph       ← directed/undirected │      │
│    │                         lanes + metadata    │      │
│    └─────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

### Backend modules

| File | Role |
| --- | --- |
| `app/core/lane_graph.py` | Graph model. Nodes as waypoints, edges as lanes. Lane carries `max_speed`, `safety_level`, `lane_type`, `directed`, `critical`, congestion EMA, usage counter, live occupants. Undirected lanes indexed both ways but share one Lane object. |
| `app/core/planner.py` | Lane-aware A*. Edge cost = `length/max_speed + safety_penalty + type_penalty + critical_penalty + CONGESTION_W × congestion_score`. Heuristic is admissible (euclidean / fastest speed). Accepts a blocked-lanes set for replanning. |
| `app/core/robot.py` | Robot dataclass + state machine: `idle · waiting · moving · estop · done · failed`. Tracks path, lane progress, replans, distance, wait ticks. |
| `app/core/coordinator.py` | Critical-lane reservations, capacity checks per lane type, wait-for graph, DFS cycle detection for deadlocks, victim selection & event log. |
| `app/sim/simulation.py` | Tick orchestration: intent → reservation → capacity → oncoming-traffic check → commit → advance (with congestion slowdown and safe-following) → deadlock detect → replan victim (forced back-off). |
| `app/api/server.py` | FastAPI app: `GET /api/health`, `GET /api/scenario`, `WS /ws/sim`; also serves built frontend. |
| `scenarios/warehouse.json` | 16-node 14×10 warehouse, 24 lanes (directed corridors, narrow passes, intersections, human zones, 2 critical reservation-gated lanes), 10 robots with head-on conflicting routes. |

### Frontend modules

| File | Role |
| --- | --- |
| `src/App.jsx` | Grid shell: header · left telemetry · map · right fleet · event-log footer. |
| `src/hooks/useSimSocket.js` | WebSocket client with auto-reconnect; emits latest snapshot. |
| `src/components/MapCanvas.jsx` | Canvas renderer. Lanes as type-coloured hairlines with heatmap or congestion overlays, directed chevrons, dashed critical-lane overlay, goal crosshairs, robot trails, state rings (moving / waiting / e-stop / done). |
| `src/components/TelemetryPanel.jsx` | Live metrics, overlay mode, play · pause · reset, speed slider (0.25× – 4×). |
| `src/components/FleetPanel.jsx` | Robot roster with wait-for arrows, active reservations, top-6 lane usage. |
| `src/components/EventLog.jsx` | Scrolling coordinator event stream. |
| `src/lib/colors.js` | Per-robot palette, lane colour by type, 3-stop heatmap interpolator. |
| `src/styles.css` | Industrial terminal aesthetic: charcoal + amber/lime, JetBrains Mono / IBM Plex Mono, hairline rules, zero rounded corners, zero gradients. |

---

## How each brief requirement is covered

| Requirement | Implementation |
| --- | --- |
| **Graph-based lane model** | `LaneGraph` with `Node` waypoints and `Lane` edges; adjacency list for O(1) neighbour lookups. |
| **Directed and undirected lanes** | `Lane.directed` flag. Undirected lanes registered under both `(u,v)` and `(v,u)` pointing to one shared object. `Lane.allows(frm, to)` enforces direction. |
| **Each lane includes metadata** | `Lane` dataclass fields: `max_speed`, `safety_level`, `lane_type`, `critical`, `length`, `congestion_score`, `usage_count`. |
| **Maximum speed / safety / lane type / congestion / historical usage** | All five live on `Lane`. Usage incremented on `record_entry`; congestion is an EMA over occupancy normalised by lane-type capacity. |
| **Lane-based speed control (adapts dynamically)** | `Simulation._advance`: `target = lane.max_speed · (1 − CONGESTION_SLOW · max(0, congestion−0.5)) · follow_scale`. |
| **Collision avoidance** | Per-tick intent resolution + capacity gate prevents same-tick collisions; oncoming-traffic detection on undirected lanes blocks head-on entries. |
| **Safe following distance** | `SAFE_FOLLOW = 0.25` (fractional). Target speed scales linearly to zero between `SAFE_FOLLOW` and `EMERGENCY_GAP = 0.08`. |
| **Emergency stop** | Below `EMERGENCY_GAP`, robot transitions to `estop`, speed zeroed, metric `estop_events` incremented. |
| **Lane-specific safety constraints** | `SAFETY_PENALTY` + `TYPE_PENALTY` bias the planner away from high-risk / narrow / intersection / human-zone lanes; capacity caps also type-specific. |
| **Track lane usage frequency** | `Lane.usage_count` counter, surfaced in `snapshot()` and the UI's top-6 panel. |
| **Track real-time occupancy** | `Lane.current_occupants` maintained by `record_entry` / `record_exit`; drives EMA. |
| **Identify congestion hotspots** | `congestion_score` EMA per lane; visualised as lane-stroke heat overlay in the UI. |
| **Use heatmap for routing decisions** | Planner weight `CONGESTION_W` multiplies `congestion_score` into edge cost; replans automatically pick around hot lanes. |
| **Minimum 8 robots** | Default scenario ships with **10** robots on conflicting routes. |
| **Shared environment** | Single `LaneGraph` + single `Coordinator` shared by all robots. |
| **Conflict avoidance and resolution** | Reservations (critical), capacity gates (narrow/intersection/human), oncoming-traffic detection, cycle-based deadlock resolution. |
| **Lane reservation** | `Coordinator.request_reservation` grants one owner per critical lane. Holders auto-release on exit. |
| **Deadlock handling** | Wait-for graph built each tick from blocked robots. `detect_deadlock` finds a cycle via DFS; `resolve_deadlock` picks victim (lowest id), `_force_back_off` retreats victim off its lane and replans with it blocked. Event logged. |
| **Dynamic replanning** | `_replan()` re-runs A* from `current_node` to `goal` with any offending lanes blocked; tracked via `replans` per robot and `total_replans` metric. |
| **Inputs: map, start/goal, lane config** | `scenarios/warehouse.json` — editable. |
| **Outputs: robot trajectories** | Live snapshot + on-canvas trail (last 24 positions per robot). |
| **Outputs: lane heatmap visualization** | Toggle in left panel: `Congestion` (live EMA) or `Heatmap` (cumulative usage). |
| **Outputs: performance metrics (delay, throughput)** | `SimMetrics`: `tick`, `finished`, `failed`, `total_distance`, `total_wait_ticks`, `total_replans`, `estop_events`, `deadlocks_resolved`, `avg_throughput`. |
| **Deadlock handling effectiveness** | `deadlocks_resolved` counter + event log. |
| **Traffic efficiency** | `avg_throughput`, `total_wait_ticks`. |
| **Safety correctness** | `estop_events`, safety penalties in cost function, capacity gates for human/narrow lanes. |
| **Lane-aware intelligence** | Cost function uses every lane property; replans around congestion automatically. |
| **Scalability** | Tick loop is O(R + L) per step; scenario config drives robot & lane count. |

---

## WebSocket protocol

**Server → client:**
```json
{
  "type": "snapshot",
  "data": {
    "tick": 42,
    "done": false,
    "robots":  [ { "id": "R01", "x": 5.2, "y": 4.0, "state": "moving", "speed": 2.1,
                   "at": "A2", "next": "B2", "progress": 0.32, "goal": "D4",
                   "replans": 0, "wait": 0 }, ... ],
    "graph":   { "nodes": [...], "lanes": [...] },
    "coord":   { "reservations": [...], "wait_for": {...},
                 "deadlocks_resolved": 1, "recent_events": [...] },
    "metrics": { ... }
  }
}
```

**Client → server:** `{"cmd": "pause" | "resume" | "reset"}` or `{"cmd": "speed", "value": 2.0}`.

---

## Reproducing a sample run

```bash
cd backend
python test_sim.py
```

Example output:
```
ticks             : 66
finished          : 10/10
failed            : 0
total distance    : 161.96
total wait ticks  : 5
replans           : 1
estop events      : 0
deadlocks resolved: 1
avg throughput    : 0.1515
```

---

## Project layout

```
lane_traffic/
├── backend/
│   ├── app/
│   │   ├── core/      (lane_graph, planner, robot, coordinator)
│   │   ├── sim/       (simulation)
│   │   └── api/       (server)
│   ├── scenarios/warehouse.json
│   ├── requirements.txt
│   ├── run.sh
│   ├── test_sim.py              # headless scenario smoke test
│   └── test_integration.py      # in-process HTTP + WebSocket test
└── frontend/
    ├── src/
    │   ├── components/          (MapCanvas, TelemetryPanel, FleetPanel, EventLog)
    │   ├── hooks/useSimSocket.js
    │   ├── lib/colors.js
    │   ├── App.jsx · main.jsx · styles.css
    ├── index.html
    ├── vite.config.js
    └── package.json
```
