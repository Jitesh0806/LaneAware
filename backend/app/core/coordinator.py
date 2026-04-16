"""
Coordinator
===========
Handles:
  * Reservations for critical lanes (one robot at a time)
  * Deadlock detection via cycle detection in the wait-for graph
  * Conflict resolution: tie-break by robot id, loser replans with offending
    lane blocked for one turn.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .lane_graph import Lane, LaneGraph, Node


class Coordinator:
    def __init__(self, graph: LaneGraph) -> None:
        self.graph = graph
        self.reservations: Dict[Tuple[Node, Node], str] = {}   # undirected lane -> robot id
        self.wait_for: Dict[str, str] = {}                     # robot -> robot it's waiting on
        self.deadlocks_resolved = 0
        self.reservation_events: List[dict] = []               # recent log

    # ---------- reservations ----------
    @staticmethod
    def _key(lane: Lane) -> Tuple[Node, Node]:
        return lane.undirected_key()

    def request_reservation(self, robot_id: str, lane: Lane) -> bool:
        if not lane.critical:
            return True
        key = self._key(lane)
        owner = self.reservations.get(key)
        if owner is None or owner == robot_id:
            self.reservations[key] = robot_id
            if owner != robot_id:
                self.reservation_events.append(
                    {"type": "granted", "robot": robot_id, "lane": f"{lane.u}-{lane.v}"}
                )
            return True
        return False

    def release_reservation(self, robot_id: str, lane: Lane) -> None:
        if not lane.critical:
            return
        key = self._key(lane)
        if self.reservations.get(key) == robot_id:
            del self.reservations[key]
            self.reservation_events.append(
                {"type": "released", "robot": robot_id, "lane": f"{lane.u}-{lane.v}"}
            )

    def release_all(self, robot_id: str) -> None:
        drop = [k for k, v in self.reservations.items() if v == robot_id]
        for k in drop:
            del self.reservations[k]

    # ---------- wait-for / deadlock ----------
    def note_waiting(self, robot_id: str, waiting_for: Optional[str]) -> None:
        if waiting_for is None:
            self.wait_for.pop(robot_id, None)
        else:
            self.wait_for[robot_id] = waiting_for

    def detect_deadlock(self) -> Optional[List[str]]:
        """Find a cycle in the wait-for graph. Returns cycle node list or None."""
        visited: Set[str] = set()
        stack_set: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            if node in stack_set:
                idx = path.index(node)
                return path[idx:]
            if node in visited:
                return None
            visited.add(node)
            stack_set.add(node)
            path.append(node)
            nxt = self.wait_for.get(node)
            if nxt is not None:
                cycle = dfs(nxt)
                if cycle:
                    return cycle
            stack_set.remove(node)
            path.pop()
            return None

        for start in list(self.wait_for.keys()):
            if start in visited:
                continue
            cycle = dfs(start)
            if cycle:
                return cycle
        return None

    def resolve_deadlock(self, cycle: List[str]) -> str:
        """Pick the victim (lowest-id robot in cycle). Returns its id."""
        victim = sorted(cycle)[0]
        self.deadlocks_resolved += 1
        self.wait_for.pop(victim, None)
        self.reservation_events.append(
            {"type": "deadlock_resolved", "cycle": cycle, "victim": victim}
        )
        return victim

    # ---------- capacity ----------
    def can_enter(self, robot_id: str, lane: Lane) -> bool:
        """Lane-type capacity: narrow/intersection/human_zone allow 1 occupant."""
        if lane.critical and self.reservations.get(self._key(lane)) not in (None, robot_id):
            return False
        cap = {"narrow": 1, "intersection": 1, "human_zone": 1, "normal": 3}.get(lane.lane_type, 3)
        occ = [o for o in lane.current_occupants if o != robot_id]
        return len(occ) < cap

    def snapshot(self) -> dict:
        return {
            "reservations": [
                {"lane": f"{u}-{v}", "owner": owner}
                for (u, v), owner in self.reservations.items()
            ],
            "wait_for": dict(self.wait_for),
            "deadlocks_resolved": self.deadlocks_resolved,
            "recent_events": self.reservation_events[-12:],
        }
