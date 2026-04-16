"""
Simulation Engine
=================
Orchestrates the tick loop:
  1. For each active robot, determine next move intent.
  2. Request reservations for critical lanes.
  3. Check capacity; if blocked, note wait-for edge.
  4. Detect deadlock; if found, pick victim and replan with offending lane blocked.
  5. Advance robot along its current lane; apply speed modulation (congestion,
     safe-following, emergency stop).
  6. Update lane congestion EMA, occupancy, heatmap counters.
  7. Collect metrics (throughput, delays, e-stops, replans).

State is exposed via snapshot() for the WebSocket stream.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..core.coordinator import Coordinator
from ..core.lane_graph import Lane, LaneGraph, Node
from ..core.planner import plan_path
from ..core.robot import CONGESTION_SLOW, EMERGENCY_GAP, Robot, RobotState, SAFE_FOLLOW


@dataclass
class SimMetrics:
    tick: int = 0
    finished: int = 0
    failed: int = 0
    total_distance: float = 0.0
    total_wait_ticks: int = 0
    total_replans: int = 0
    estop_events: int = 0
    deadlocks_resolved: int = 0
    avg_throughput: float = 0.0

    def as_dict(self) -> dict:
        return {
            "tick": self.tick,
            "finished": self.finished,
            "failed": self.failed,
            "total_distance": round(self.total_distance, 2),
            "total_wait_ticks": self.total_wait_ticks,
            "total_replans": self.total_replans,
            "estop_events": self.estop_events,
            "deadlocks_resolved": self.deadlocks_resolved,
            "avg_throughput": round(self.avg_throughput, 3),
        }


class Simulation:
    def __init__(
        self,
        graph: LaneGraph,
        robots: List[Robot],
        dt: float = 0.2,
        seed: int = 42,
    ) -> None:
        self.graph = graph
        self.robots: Dict[str, Robot] = {r.id: r for r in robots}
        self.coord = Coordinator(graph)
        self.dt = dt
        self.rng = random.Random(seed)
        self.metrics = SimMetrics()
        self.running = False
        self._init_robots()

    # ---------- setup ----------
    def _init_robots(self) -> None:
        for r in self.robots.values():
            r.current_node = r.start
            r.state = RobotState.IDLE
            path = plan_path(self.graph, r.start, r.goal)
            if path is None or len(path) < 2:
                r.state = RobotState.FAILED
                continue
            r.path = path
            r.path_index = 0
            r.state = RobotState.MOVING

    # ---------- tick ----------
    def step(self) -> None:
        self.metrics.tick += 1

        # pass 1: determine next-node intents & request reservations / capacity
        intents: Dict[str, Tuple[Node, Lane]] = {}
        for r in self.robots.values():
            if r.state in (RobotState.DONE, RobotState.FAILED):
                continue
            r.ticks_active += 1

            # already traversing a lane: keep going
            if r.current_lane is not None:
                continue

            # at a node, need next hop
            if r.path_index + 1 >= len(r.path):
                # arrived
                r.state = RobotState.DONE
                r.finish_tick = self.metrics.tick
                self.metrics.finished += 1
                self.coord.release_all(r.id)
                self.coord.note_waiting(r.id, None)
                continue

            frm = r.path[r.path_index]
            to = r.path[r.path_index + 1]
            lane = self.graph.get_lane(frm, to)
            if lane is None or not lane.allows(frm, to):
                if self._replan(r, blocked={(frm, to)} if lane else set()):
                    continue
                r.state = RobotState.FAILED
                self.metrics.failed += 1
                continue

            # reservation
            if not self.coord.request_reservation(r.id, lane):
                r.state = RobotState.WAITING
                r.wait_ticks += 1
                self.metrics.total_wait_ticks += 1
                owner = self.coord.reservations.get(lane.undirected_key())
                self.coord.note_waiting(r.id, owner)
                continue

            # capacity
            if not self.coord.can_enter(r.id, lane):
                r.state = RobotState.WAITING
                r.wait_ticks += 1
                self.metrics.total_wait_ticks += 1
                other = next((o for o in lane.current_occupants if o != r.id), None)
                self.coord.note_waiting(r.id, other)
                continue

            # check oncoming traffic on undirected lane before committing
            oncoming = self._oncoming_blocker(r, lane, to)
            if oncoming is not None:
                r.state = RobotState.WAITING
                r.wait_ticks += 1
                self.metrics.total_wait_ticks += 1
                self.coord.note_waiting(r.id, oncoming)
                continue

            intents[r.id] = (to, lane)
            self.coord.note_waiting(r.id, None)

        # pass 2: commit entries for granted intents
        for rid, (to, lane) in intents.items():
            r = self.robots[rid]
            r.current_lane = lane
            r.next_node = to
            r.lane_progress = 0.0
            r.state = RobotState.MOVING
            lane.record_entry(r.id)

        # pass 3: advance moving robots (this also updates wait_for via _gap_ahead)
        for r in self.robots.values():
            if r.state != RobotState.MOVING or r.current_lane is None:
                continue
            self._advance(r)

        # pass 4: deadlock detection AFTER we know current blocking state
        cycle = self.coord.detect_deadlock()
        if cycle:
            victim_id = self.coord.resolve_deadlock(cycle)
            victim = self.robots.get(victim_id)
            if victim is not None:
                self._force_back_off(victim)

        # pass 5: update lane congestion EMA
        self.graph.update_all_congestion()

        if self.metrics.tick > 0:
            self.metrics.avg_throughput = self.metrics.finished / self.metrics.tick
        self.metrics.deadlocks_resolved = self.coord.deadlocks_resolved

    def _oncoming_blocker(self, r: Robot, lane: Lane, to: Node) -> Optional[str]:
        """If lane is undirected and someone is on it going the other way, return their id."""
        if lane.directed:
            return None
        for other in self.robots.values():
            if other.id == r.id or other.current_lane is not lane:
                continue
            if other.next_node == r.current_node and other.current_node == to:
                return other.id
        return None

    def _force_back_off(self, victim: Robot) -> None:
        """Evict the victim from its current lane and replan with that lane blocked."""
        blocked: Set[Tuple[Node, Node]] = set()
        if victim.current_lane is not None:
            lane = victim.current_lane
            # retreat to current_node (the side we entered from)
            lane.record_exit(victim.id)
            self.coord.release_reservation(victim.id, lane)
            victim.current_lane = None
            victim.next_node = None
            victim.lane_progress = 0.0
            blocked.add((lane.u, lane.v))
            if not lane.directed:
                blocked.add((lane.v, lane.u))
        elif victim.path_index + 1 < len(victim.path):
            frm = victim.path[victim.path_index]
            to_node = victim.path[victim.path_index + 1]
            blocked.add((frm, to_node))
        self._replan(victim, blocked=blocked)

    # ---------- movement ----------
    def _advance(self, r: Robot) -> None:
        lane = r.current_lane
        if lane is None:
            return
        # gap to nearest robot ahead on same lane in same direction
        gap = self._gap_ahead(r)
        target = lane.max_speed
        # congestion slowdown
        if lane.congestion_score > 0.5:
            target *= max(0.2, 1 - CONGESTION_SLOW * (lane.congestion_score - 0.5))
        # safe following
        if gap is not None:
            if gap < EMERGENCY_GAP:
                r.state = RobotState.ESTOP
                r.speed = 0.0
                self.metrics.estop_events += 1
                return
            if gap < SAFE_FOLLOW:
                scale = (gap - EMERGENCY_GAP) / (SAFE_FOLLOW - EMERGENCY_GAP)
                target *= max(0.0, scale)
        r.speed = target
        # advance progress
        step = (target * self.dt) / max(lane.length, 1e-3)
        r.lane_progress += step
        r.distance_travelled += target * self.dt
        self.metrics.total_distance += target * self.dt

        if r.lane_progress >= 1.0:
            # arrived at next node
            r.lane_progress = 0.0
            lane.record_exit(r.id)
            self.coord.release_reservation(r.id, lane)
            assert r.next_node is not None
            r.current_node = r.next_node
            r.current_lane = None
            r.next_node = None
            r.path_index += 1
            r.state = RobotState.MOVING

    def _gap_ahead(self, r: Robot) -> Optional[float]:
        """Returns fractional gap to nearest blocker ahead on same lane, or None.
        Also records a wait-for edge on the coordinator so deadlock detection
        catches head-on oncoming-traffic deadlocks on undirected lanes.
        """
        lane = r.current_lane
        if lane is None:
            return None
        best: Optional[float] = None
        blocker: Optional[str] = None
        for other in self.robots.values():
            if other.id == r.id or other.current_lane is not lane:
                continue
            same_direction = (
                other.current_node == r.current_node
                and other.next_node == r.next_node
            )
            if same_direction:
                diff = other.lane_progress - r.lane_progress
                if diff > 0 and (best is None or diff < best):
                    best = diff
                    blocker = other.id
            else:
                # opposing traffic on the same undirected lane -> blockage
                # regardless of lane type; the two are physically on the same lane.
                diff = max(0.0, 1.0 - r.lane_progress - other.lane_progress)
                if best is None or diff < best:
                    best = diff
                    blocker = other.id
        # tell coordinator who we're waiting for (if anyone blocks us closely)
        if blocker is not None and best is not None and best < SAFE_FOLLOW:
            self.coord.note_waiting(r.id, blocker)
        else:
            self.coord.note_waiting(r.id, None)
        return best

    # ---------- replan ----------
    def _replan(self, r: Robot, blocked: Optional[Set[Tuple[Node, Node]]] = None) -> bool:
        new_path = plan_path(self.graph, r.current_node, r.goal, blocked_lanes=blocked)
        if new_path is None or len(new_path) < 2:
            return False
        r.path = new_path
        r.path_index = 0
        r.replans += 1
        self.metrics.total_replans += 1
        r.state = RobotState.MOVING
        return True

    # ---------- I/O ----------
    def all_done(self) -> bool:
        return all(r.state in (RobotState.DONE, RobotState.FAILED) for r in self.robots.values())

    def snapshot(self) -> dict:
        return {
            "tick": self.metrics.tick,
            "metrics": self.metrics.as_dict(),
            "robots": [r.serialize(self.graph) for r in self.robots.values()],
            "graph": self.graph.snapshot(),
            "coord": self.coord.snapshot(),
            "done": self.all_done(),
        }
