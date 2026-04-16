"""
Robot Model
===========
Each robot follows a planned path (list of node IDs).
At any time it is either AT a node or TRAVERSING a lane with progress in [0, 1].

Speed control per tick:
  target = lane.max_speed
         * (1 - CONGESTION_SLOW * max(0, congestion - 0.5))
         * (1.0 if gap_ahead > SAFE_FOLLOW else max(0, (gap_ahead - EMERGENCY) / (SAFE_FOLLOW - EMERGENCY)))
  If gap_ahead < EMERGENCY -> EMERGENCY_STOP.

Waits for reservation grants on critical lanes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .lane_graph import Lane, LaneGraph, Node

SAFE_FOLLOW = 0.25
EMERGENCY_GAP = 0.08
CONGESTION_SLOW = 0.7


class RobotState(str, Enum):
    IDLE = "idle"
    WAITING = "waiting"
    MOVING = "moving"
    ESTOP = "estop"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Robot:
    id: str
    start: Node
    goal: Node
    # runtime
    current_node: Node = ""
    next_node: Optional[Node] = None
    current_lane: Optional[Lane] = None
    lane_progress: float = 0.0
    speed: float = 0.0
    path: List[Node] = field(default_factory=list)
    path_index: int = 0
    state: RobotState = RobotState.IDLE
    wait_ticks: int = 0
    replans: int = 0
    distance_travelled: float = 0.0
    ticks_active: int = 0
    spawn_tick: int = 0
    finish_tick: Optional[int] = None

    def position(self, graph: LaneGraph) -> tuple[float, float]:
        if self.current_lane is None:
            return graph.position(self.current_node)
        (x1, y1) = graph.position(self.current_lane.u if self.current_lane.u == self.current_node else self.current_lane.v)
        # derive direction based on which node we left
        u, v = self.current_lane.u, self.current_lane.v
        if self.current_node == u and self.next_node == v:
            (sx, sy), (tx, ty) = graph.position(u), graph.position(v)
        else:
            (sx, sy), (tx, ty) = graph.position(v), graph.position(u)
        p = self.lane_progress
        return (sx + (tx - sx) * p, sy + (ty - sy) * p)

    def serialize(self, graph: LaneGraph) -> dict:
        x, y = self.position(graph)
        return {
            "id": self.id,
            "x": round(x, 3),
            "y": round(y, 3),
            "state": self.state.value,
            "speed": round(self.speed, 3),
            "at": self.current_node,
            "next": self.next_node,
            "progress": round(self.lane_progress, 3),
            "goal": self.goal,
            "replans": self.replans,
            "wait": self.wait_ticks,
        }
