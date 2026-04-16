"""Headless smoke-test: run the warehouse scenario to completion and print metrics."""
import json
import sys
from pathlib import Path

# allow `python test_sim.py` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.lane_graph import LaneGraph
from app.core.robot import Robot
from app.sim.simulation import Simulation

SCENARIO = Path(__file__).parent / "scenarios" / "warehouse.json"


def main():
    with open(SCENARIO) as f:
        sc = json.load(f)
    g = LaneGraph()
    for n in sc["nodes"]:
        g.add_node(n["id"], n["x"], n["y"])
    for ln in sc["lanes"]:
        g.add_lane(
            u=ln["u"], v=ln["v"],
            max_speed=ln.get("max_speed", 1.0),
            safety_level=ln.get("safety_level", "medium"),
            lane_type=ln.get("lane_type", "normal"),
            directed=ln.get("directed", False),
            critical=ln.get("critical", False),
        )
    robots = [Robot(id=r["id"], start=r["start"], goal=r["goal"]) for r in sc["robots"]]
    sim = Simulation(graph=g, robots=robots, dt=0.25)

    max_ticks = 1200
    for t in range(max_ticks):
        sim.step()
        if sim.all_done():
            break

    print(f"ticks             : {sim.metrics.tick}")
    print(f"finished          : {sim.metrics.finished}/{len(robots)}")
    print(f"failed            : {sim.metrics.failed}")
    print(f"total distance    : {sim.metrics.total_distance:.2f}")
    print(f"total wait ticks  : {sim.metrics.total_wait_ticks}")
    print(f"replans           : {sim.metrics.total_replans}")
    print(f"estop events      : {sim.metrics.estop_events}")
    print(f"deadlocks resolved: {sim.metrics.deadlocks_resolved}")
    print(f"avg throughput    : {sim.metrics.avg_throughput:.4f}")

    top = sorted(g.unique_lanes(), key=lambda l: l.usage_count, reverse=True)[:5]
    print("\ntop 5 lanes by usage:")
    for ln in top:
        print(f"  {ln.u}-{ln.v:<3}  usage={ln.usage_count:3d}  congestion={ln.congestion_score:.3f}  type={ln.lane_type}")

if __name__ == "__main__":
    main()
