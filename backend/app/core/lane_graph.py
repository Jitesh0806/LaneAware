"""
Lane Graph
==========
Graph-based representation of a structured environment (warehouse / factory).

Nodes are waypoints with (x, y) positions.
Edges are lanes with metadata:
    max_speed        (units/sec)
    safety_level     'low' | 'medium' | 'high' | 'critical'
    lane_type        'normal' | 'narrow' | 'intersection' | 'human_zone'
    directed         bool  -> one-way u -> v if True
    critical         bool  -> requires reservation before entry
    length           float (auto, euclidean)
    congestion_score float 0..1 (EMA of occupancy)
    usage_count      int   (historical traversals, powers the heatmap)

Undirected lanes are stored once but indexed under both (u,v) and (v,u) so
usage/congestion updates propagate regardless of traversal direction.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

Node = str


@dataclass
class Lane:
    u: Node
    v: Node
    max_speed: float = 1.0
    safety_level: str = "medium"
    lane_type: str = "normal"
    directed: bool = False
    critical: bool = False
    length: float = 1.0
    # dynamic
    congestion_score: float = 0.0
    usage_count: int = 0
    current_occupants: List[str] = field(default_factory=list)

    def undirected_key(self) -> Tuple[Node, Node]:
        return tuple(sorted((self.u, self.v)))  # type: ignore[return-value]

    def allows(self, frm: Node, to: Node) -> bool:
        if self.directed:
            return frm == self.u and to == self.v
        return {frm, to} == {self.u, self.v}

    def record_entry(self, robot_id: str) -> None:
        if robot_id not in self.current_occupants:
            self.current_occupants.append(robot_id)
        self.usage_count += 1

    def record_exit(self, robot_id: str) -> None:
        if robot_id in self.current_occupants:
            self.current_occupants.remove(robot_id)

    def update_congestion(self, alpha: float = 0.3) -> None:
        cap = {"narrow": 1, "intersection": 1, "human_zone": 1, "normal": 3}.get(
            self.lane_type, 3
        )
        instant = min(1.0, len(self.current_occupants) / cap)
        self.congestion_score = (1 - alpha) * self.congestion_score + alpha * instant


@dataclass
class LaneGraph:
    nodes: Dict[Node, Tuple[float, float]] = field(default_factory=dict)
    lanes: Dict[Tuple[Node, Node], Lane] = field(default_factory=dict)
    _adj: Dict[Node, List[Tuple[Node, Lane]]] = field(default_factory=dict)

    # ---------- construction ----------
    def add_node(self, node_id: Node, x: float, y: float) -> None:
        self.nodes[node_id] = (x, y)
        self._adj.setdefault(node_id, [])

    def add_lane(
        self,
        u: Node,
        v: Node,
        max_speed: float = 1.0,
        safety_level: str = "medium",
        lane_type: str = "normal",
        directed: bool = False,
        critical: bool = False,
    ) -> Lane:
        if u not in self.nodes or v not in self.nodes:
            raise ValueError(f"unknown nodes for lane {u}->{v}")
        length = self._distance(u, v)
        lane = Lane(
            u=u, v=v,
            max_speed=max_speed,
            safety_level=safety_level,
            lane_type=lane_type,
            directed=directed,
            critical=critical,
            length=length,
        )
        self.lanes[(u, v)] = lane
        self._adj[u].append((v, lane))
        if not directed:
            self.lanes[(v, u)] = lane
            self._adj[v].append((u, lane))
        return lane

    def _distance(self, u: Node, v: Node) -> float:
        (x1, y1), (x2, y2) = self.nodes[u], self.nodes[v]
        return math.hypot(x2 - x1, y2 - y1)

    # ---------- queries ----------
    def neighbors(self, node: Node) -> Iterable[Tuple[Node, Lane]]:
        return self._adj.get(node, [])

    def get_lane(self, u: Node, v: Node) -> Optional[Lane]:
        return self.lanes.get((u, v))

    def position(self, node: Node) -> Tuple[float, float]:
        return self.nodes[node]

    def update_all_congestion(self) -> None:
        seen = set()
        for lane in self.lanes.values():
            k = lane.undirected_key()
            if k in seen:
                continue
            seen.add(k)
            lane.update_congestion()

    def unique_lanes(self) -> List[Lane]:
        seen, out = set(), []
        for lane in self.lanes.values():
            k = lane.undirected_key()
            if k in seen:
                continue
            seen.add(k)
            out.append(lane)
        return out

    # ---------- I/O ----------
    @classmethod
    def from_json(cls, path: str) -> "LaneGraph":
        with open(path) as f:
            data = json.load(f)
        g = cls()
        for n in data["nodes"]:
            g.add_node(n["id"], n["x"], n["y"])
        for ln in data["lanes"]:
            g.add_lane(
                u=ln["u"], v=ln["v"],
                max_speed=ln.get("max_speed", 1.0),
                safety_level=ln.get("safety_level", "medium"),
                lane_type=ln.get("lane_type", "normal"),
                directed=ln.get("directed", False),
                critical=ln.get("critical", False),
            )
        return g

    def snapshot(self) -> Dict:
        return {
            "nodes": [
                {"id": nid, "x": x, "y": y}
                for nid, (x, y) in self.nodes.items()
            ],
            "lanes": [
                {
                    "u": ln.u, "v": ln.v,
                    "max_speed": ln.max_speed,
                    "safety_level": ln.safety_level,
                    "lane_type": ln.lane_type,
                    "directed": ln.directed,
                    "critical": ln.critical,
                    "length": ln.length,
                    "congestion": round(ln.congestion_score, 3),
                    "usage": ln.usage_count,
                    "occupants": list(ln.current_occupants),
                }
                for ln in self.unique_lanes()
            ],
        }
