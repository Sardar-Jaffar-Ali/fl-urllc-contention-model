"""
FL-URLLC resource-contention model.

Runs the abstract discrete-time simulation used in the case study and writes:
    results/raw_results.csv        one row per (traffic, load, seed, policy)
    results/summary_with_95CI.csv  mean, std and 95% CI across seeds

This is an abstract resource model. It is NOT a 3GPP-compliant or
system-level 5G simulator, and its units are not calibrated to real
radio resources.

Usage:
    python simulate.py                 # full experiment (30 seeds)
    python simulate.py --seeds 3       # quick check
"""

import argparse
import math
import os
from collections import deque

import numpy as np
import pandas as pd

# ------------------------------------------------------------------
# Model parameters (as reported in the paper, Section IV-A)
# ------------------------------------------------------------------
CAPACITY = 100              # resource units per 1-ms slot
URLLC_DEADLINE_MS = 10      # a URLLC packet is dropped if still queued 10 ms after arrival
FL_WORK = 2000              # resource units per FL round (aggregate job)
FL_DEADLINE_MS = 1000       # completion deadline of each FL round
FL_PERIOD_MS = 1000         # a new FL round is released every 1000 ms
FIRST_FL_RELEASE_MS = 100   # first FL round is released at t = 100 ms

SIM_MS = 10_000                                 # arrival period
DRAIN_MS = FL_DEADLINE_MS + URLLC_DEADLINE_MS   # extra slots with no new arrivals

FIXED_FL_SHARE = 20         # FL reservation under the fixed policy (20% of capacity)

# Bursty traffic: two-state Markov-modulated Poisson process (MMPP)
P_LOW_TO_HIGH = 0.02        # per-slot switching probability
P_HIGH_TO_LOW = 0.08        # per-slot switching probability
LOW_RATE_FACTOR = 0.5       # arrival rate in the low state  = 0.5 x load
HIGH_RATE_FACTOR = 3.0      # arrival rate in the high state = 3.0 x load
# Stationary high-state probability = 0.02 / (0.02 + 0.08) = 0.2,
# so the long-run mean rate is 0.8*0.5*load + 0.2*3.0*load = 1.0 x load.

LOADS = [20, 40, 60, 70, 75, 80, 85, 90, 95, 100, 105, 110, 120]  # packets/ms
TRAFFIC_TYPES = ["steady", "bursty"]
POLICIES = ["strict_priority", "fixed_fl_reservation"]


# ------------------------------------------------------------------
# Traffic generation
# ------------------------------------------------------------------
def generate_arrivals(load, traffic_type, seed, total_ms):
    """Return the number of URLLC packet arrivals in each 1-ms slot."""
    rng = np.random.default_rng(seed)
    arrivals = np.zeros(total_ms, dtype=np.int32)

    if traffic_type == "steady":
        arrivals[:] = rng.poisson(load, size=total_ms)
        return arrivals

    high = False
    for t in range(total_ms):
        if high:
            if rng.random() < P_HIGH_TO_LOW:
                high = False
        else:
            if rng.random() < P_LOW_TO_HIGH:
                high = True
        rate = (HIGH_RATE_FACTOR if high else LOW_RATE_FACTOR) * load
        arrivals[t] = rng.poisson(rate)

    return arrivals


# ------------------------------------------------------------------
# One simulation run
# ------------------------------------------------------------------
def simulate_one(load, traffic_type, seed, policy):
    if policy not in POLICIES:
        raise ValueError(f"Unknown policy: {policy}")

    total_ms = SIM_MS + DRAIN_MS
    arrivals = generate_arrivals(load, traffic_type, seed, total_ms)
    arrivals[SIM_MS:] = 0  # no new traffic during the drain period

    urllc_queue = deque()  # each item is the packet's arrival slot

    urllc_arrived = urllc_delivered = urllc_expired = 0
    fl_released = fl_completed = fl_missed = 0
    fl_completion_times = []

    active_fl = None
    next_release = FIRST_FL_RELEASE_MS

    for t in range(total_ms):
        # 1. Drop URLLC packets that have waited URLLC_DEADLINE_MS.
        while urllc_queue and t - urllc_queue[0] >= URLLC_DEADLINE_MS:
            urllc_queue.popleft()
            urllc_expired += 1

        # 2. A round still unfinished at its deadline is counted as missed.
        if active_fl is not None and t >= active_fl["release"] + FL_DEADLINE_MS:
            fl_missed += 1
            active_fl = None

        # 3. Release a new FL round. Because FL_PERIOD_MS == FL_DEADLINE_MS,
        #    the previous round has always been completed or marked missed
        #    by the time the next one is released.
        if t < SIM_MS and t >= next_release:
            fl_released += 1
            active_fl = {"release": t, "remaining": float(FL_WORK)}
            next_release += FL_PERIOD_MS

        # 4. New URLLC arrivals join the queue.
        n = int(arrivals[t])
        urllc_arrived += n
        urllc_queue.extend([t] * n)

        # 5. Serve URLLC within its budget.
        urllc_budget = CAPACITY if policy == "strict_priority" else CAPACITY - FIXED_FL_SHARE
        served = min(len(urllc_queue), urllc_budget)
        for _ in range(served):
            urllc_queue.popleft()
        urllc_delivered += served

        # 6. Serve FL.
        if policy == "strict_priority":
            # FL may use only capacity left after the URLLC queue is emptied.
            fl_budget = CAPACITY - served if len(urllc_queue) == 0 else 0
        else:
            # Fixed reservation: FL always gets its share; unused capacity
            # in either share is not reassigned.
            fl_budget = FIXED_FL_SHARE

        if active_fl is not None and fl_budget > 0:
            active_fl["remaining"] -= min(fl_budget, active_fl["remaining"])

        # 7. Record a completed round at the end of the slot.
        if active_fl is not None and active_fl["remaining"] <= 1e-9:
            elapsed = (t + 1) - active_fl["release"]
            if elapsed <= FL_DEADLINE_MS:
                fl_completed += 1
                fl_completion_times.append(elapsed)
            else:
                fl_missed += 1
            active_fl = None

    if active_fl is not None:
        fl_missed += 1

    assert fl_completed + fl_missed == fl_released, "FL round accounting mismatch"

    return {
        "traffic": traffic_type,
        "load_packets_per_ms": load,
        "seed": seed,
        "policy": policy,
        "urllc_arrived": urllc_arrived,
        "urllc_delivered": urllc_delivered,
        "urllc_expired": urllc_expired,
        "urllc_deadline_violation_pct": 100.0 * urllc_expired / urllc_arrived if urllc_arrived else 0.0,
        "fl_rounds_released": fl_released,
        "fl_rounds_completed": fl_completed,
        "fl_rounds_missed": fl_missed,
        "fl_mean_completion_ms": float(np.mean(fl_completion_times)) if fl_completion_times else np.nan,
    }


# ------------------------------------------------------------------
# Summary statistics
# ------------------------------------------------------------------
SUMMARY_METRICS = [
    "urllc_deadline_violation_pct",
    "fl_rounds_completed",
    "fl_rounds_missed",
    "fl_mean_completion_ms",
]


def summarize(raw):
    rows = []
    for (traffic, load, policy), g in raw.groupby(["traffic", "load_packets_per_ms", "policy"]):
        row = {"traffic": traffic, "load_packets_per_ms": load, "policy": policy, "n_seeds": len(g)}
        for m in SUMMARY_METRICS:
            v = g[m].dropna().to_numpy(dtype=float)
            if len(v) == 0:
                mean = std = lo = hi = np.nan
            else:
                mean = float(np.mean(v))
                std = float(np.std(v, ddof=1)) if len(v) > 1 else 0.0
                half = 1.96 * std / math.sqrt(len(v))
                lo, hi = mean - half, mean + half
            row[f"{m}_mean"] = mean
            row[f"{m}_std"] = std
            row[f"{m}_ci95_low"] = lo
            row[f"{m}_ci95_high"] = hi
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", type=int, default=30, help="number of random seeds (default: 30)")
    parser.add_argument("--outdir", default="results", help="output folder (default: results)")
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    seeds = list(range(args.seeds))
    total = len(TRAFFIC_TYPES) * len(LOADS) * len(seeds) * len(POLICIES)

    results, done = [], 0
    for traffic in TRAFFIC_TYPES:
        for load in LOADS:
            for seed in seeds:
                for policy in POLICIES:
                    results.append(simulate_one(load, traffic, seed, policy))
                    done += 1
                    if done % 100 == 0 or done == total:
                        print(f"Completed {done}/{total} runs")

    raw = pd.DataFrame(results)
    summary = summarize(raw)
    raw.to_csv(os.path.join(args.outdir, "raw_results.csv"), index=False)
    summary.to_csv(os.path.join(args.outdir, "summary_with_95CI.csv"), index=False)

    cols = ["traffic", "load_packets_per_ms", "policy",
            "urllc_deadline_violation_pct_mean", "fl_rounds_completed_mean"]
    print("\n" + summary[cols].round(2).to_string(index=False))
    print(f"\nResults written to {args.outdir}/")


if __name__ == "__main__":
    main()
