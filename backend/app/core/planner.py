"""
Lane-Aware A* Planner
=====================
Edge cost = length / max_speed                   # base travel time
          + safety_penalty + type_penalty        # prefer safer/simpler lanes
          + critical_penalty                     # avoid reservation-required lanes
          + CONGESTION_W * congestion_score      # avoid busy lanes dynamically

Heuristic: euclidean_distance / fastest_max_speed  (admissible).
"""
from __future__ import annotations

import heapq
import math
from typing import Dict, List, Optional, Set, Tuple

from .lane_graph import Lane, LaneGraph, Node

CONGESTION_W = 3.0
SAFETY_PENALTY = {"low": 0.0, "medium": 0.2, "high": 0.8, "critical": 1.5}
TYPE_PENALTY = {"normal": 0.0, "narrow": 0.4, "intersection": 0.3, "human_zone": 1.0}
CRITICAL_PENALTY = 0.5


def edge_cost(lane: Lane) -> float:
    base = lane.length / max(lane.max_speed, 1e-3)
    penalty = SAFETY_PENALTY.get(lane.safety_level, 0.3)
    penalty += TYPE_PENALTY.get(lane.lane_type, 0.0)
    penalty += CRITICAL_PENALTY if lane.critical else 0.0
    penalty += CONGESTION_W * lane.congestion_score
    return base + penalty


def _heuristic(graph: LaneGraph, node: Node, goal: Node, fastest: float) -> float:
    (x1, y1) = graph.position(node)
    (x2, y2) = graph.position(goal)
    return math.hypot(x2 - x1, y2 - y1) / max(fastest, 1e-3)


def plan_path(
    graph: LaneGraph,
    start: Node,
    goal: Node,
    blocked_lanes: Optional[Set[Tuple[Node, Node]]] = None,
) -> Optional[List[Node]]:
    """A* search. Returns list of node IDs from start to goal, or None."""
    if start == goal:
        return [start]
    blocked = blocked_lanes or set()
    fastest = max((ln.max_speed for ln in graph.lanes.values()), default=1.0)

    counter = 0
    open_heap: List[Tuple[float, int, Node]] = []
    g_score: Dict[Node, float] = {start: 0.0}
    came_from: Dict[Node, Node] = {}
    heapq.heappush(
        open_heap, (_heuristic(graph, start, goal, fastest), counter, start)
    )
    closed: Set[Node] = set()

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        if current in closed:
            continue
        closed.add(current)

        for nbr, lane in graph.neighbors(current):
            if (current, nbr) in blocked:
                continue
            tentative = g_score[current] + edge_cost(lane)
            if tentative < g_score.get(nbr, float("inf")):
                g_score[nbr] = tentative
                came_from[nbr] = current
                counter += 1
                f = tentative + _heuristic(graph, nbr, goal, fastest)
                heapq.heappush(open_heap, (f, counter, nbr))
    return None
