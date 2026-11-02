# FL–URLLC Resource-Contention Model

This repository contains the simulation code and results for the FL–URLLC coexistence case study (Section IV) of the article *"The Unpriced Cost of Collaborative Intelligence in 5G-Advanced: A 3GPP Release 18 and 19 Perspective."*

The model compares two static scheduling policies for a cell shared by:
- latency-critical URLLC traffic, and
- a periodic federated learning (FL) training round with a completion deadline.

It reproduces Figs. 3 and 4 of the article.

> **Important:** This is an **abstract discrete-time resource-contention model**. It is **not** a 3GPP-compliant or system-level 5G simulator. Its resource units are not calibrated to real radio resources, and FL is modeled as one aggregate job rather than a cohort of individual UEs. The results show the URLLC–FL trade-off under the stated assumptions. They do not predict performance in a deployed 5G network.

## Repository contents

| File | Purpose |
|---|---|
| `simulate.py` | Runs the simulation and writes the results CSV files |
| `plot_figures.py` | Plots Figs. 3 and 4 from the summary CSV |
| `results/raw_results.csv` | Precomputed results, one row per run (1,560 runs) |
| `results/summary_with_95CI.csv` | Mean, standard deviation and 95% confidence interval across seeds |
| `figures/` | Figs. 3 and 4 as PNG and PDF |
| `requirements.txt` | Python dependencies |

## Quick start

Requires Python 3.9 or later.

```bash
pip install -r requirements.txt
python simulate.py        # about 1-2 minutes; writes results/
python plot_figures.py    # writes figures/
```

For a quick check with fewer seeds:

```bash
python simulate.py --seeds 3 --outdir results_quick
```

The repository already includes the full results, so `plot_figures.py` works without running the simulation first.

## Model

### Time and capacity
- Time advances in **1-ms slots**.
- Each slot has a capacity of **100 resource units**.

### URLLC traffic
- Each URLLC packet needs **1 resource unit** and waits in a single first-in, first-out queue.
- A packet still queued **10 ms** after arrival is dropped. This matches the 10 ms packet delay budget of 5QIs 82 and 83 (Discrete Automation) in 3GPP TS 23.501, Table 5.7.4-1.
- **Deadline-violation rate** = dropped packets / arrived packets × 100.
- **Steady traffic:** Poisson arrivals with mean equal to the offered load.
- **Bursty traffic:** a two-state Markov-modulated Poisson process.
  - Per-slot switching probability: 0.02 (low → high) and 0.08 (high → low).
  - Arrival rate: 0.5 × load in the low state and 3 × load in the high state.
  - The high state is occupied 20% of the time on average, so the long-run mean equals the offered load.
- **Offered loads:** 20, 40, 60, 70, 75, 80, 85, 90, 95, 100, 105, 110 and 120 packets/ms.

### FL traffic
- Each FL round is one **aggregate job of 2,000 resource units**, which is 2 units per slot on average over the round.
- A round is released every **1,000 ms**, starting at t = 100 ms, so each run has **10 rounds**.
- Each round has a **1,000-ms completion deadline**. A round not finished by its deadline is counted as **missed**.
- Because the release period equals the deadline, at most one round is active at a time.

### Scheduling policies

| Policy | URLLC | FL |
|---|---|---|
| **Strict priority** | Served first, up to the full 100 units | Uses only capacity left over **after the URLLC queue is fully served**; gets nothing in a slot where URLLC packets remain queued |
| **Fixed FL reservation** | Capped at 80 units per slot | Always receives 20 units per slot. Unused capacity in either share is **not** reassigned |

### Order of events in each slot
1. Drop URLLC packets that have waited 10 ms.
2. Mark the active FL round as missed if its deadline has passed.
3. Release a new FL round if one is due.
4. Add new URLLC arrivals to the queue.
5. Serve URLLC within its budget.
6. Serve the active FL round within its budget.
7. Record the FL round as completed if its work is done.

### Experiment settings
- Each run lasts **10,000 ms** of arrivals plus a **1,010-ms drain period** with no new arrivals.
- Each combination of traffic type, load and policy is run with **30 random seeds** (seeds 0–29).
- In total: 2 traffic types × 13 loads × 30 seeds × 2 policies = **1,560 runs**.
- 95% confidence intervals are computed as mean ± 1.96 × standard deviation / √30.
- For a given seed and traffic type, both policies see **identical URLLC arrivals**, so they are compared on the same traffic.

## Key results

These values come from `results/summary_with_95CI.csv` and match the article.

| Traffic | Load (packets/ms) | Policy | URLLC violations (%) | FL rounds completed (of 10) |
|---|---|---|---|---|
| Steady | 95 | Strict priority | 0.00 | 10.0 |
| Steady | 95 | Fixed FL reservation | 15.72 | 10.0 |
| Steady | 100 | Strict priority | 0.03 | 1.0 |
| Steady | 100 | Fixed FL reservation | 19.93 | 10.0 |
| Bursty | 120 | Strict priority | 34.16 | 10.0 |
| Bursty | 120 | Fixed FL reservation | 39.96 | 10.0 |

How to read these results:
- **Fixed reservation** caps URLLC at 80 units, so violations approach (λ − 80)/λ once the load λ exceeds 80, even though FL needs only about 2 units per slot.
- **Strict priority** protects URLLC, but FL rounds fail once steady URLLC load approaches capacity (100 packets/ms and above).
- **Under bursty traffic**, low-load periods leave spare capacity for FL even under strict priority, while high-load periods exceed capacity under either policy.
- **Neither static policy protects both traffic types.**

## Output columns

`raw_results.csv`:

| Column | Meaning |
|---|---|
| `traffic`, `load_packets_per_ms`, `seed`, `policy` | Run identifiers |
| `urllc_arrived`, `urllc_delivered`, `urllc_expired` | URLLC packet counts |
| `urllc_deadline_violation_pct` | Dropped / arrived × 100 |
| `fl_rounds_released`, `fl_rounds_completed`, `fl_rounds_missed` | FL round counts (completed + missed = released) |
| `fl_mean_completion_ms` | Mean completion time of completed rounds (empty if none) |

`summary_with_95CI.csv` gives, for each metric, `_mean`, `_std`, `_ci95_low` and `_ci95_high` across seeds.

## Changing the model

All parameters are constants at the top of `simulate.py` (capacity, deadlines, FL work, reservation share, MMPP settings, loads). Edit them and rerun. If you set `FL_PERIOD_MS` shorter than `FL_DEADLINE_MS`, rounds can overlap, and the code will need a rule for handling a new round while another is still active.

## Author

**Sardar Jaffar Ali**
School of Computer Science, Kyungpook National University, Daegu, South Korea

## Citation

If you use this code, please cite the article:

```bibtex
@misc{ali2026unpriced,
  title  = {The Unpriced Cost of Collaborative Intelligence in 5G-Advanced: A 3GPP Release 18 and 19 Perspective},
  author = {Ali, Sardar Jaffar and Ali, Sardar Kazim and Raza, Syed Muhammad and Kim, Jeonggeun and Tak, Byungchul},
  year   = {2026},
  note   = {Manuscript under review}
}
```

## License

Copyright (c) 2026 Sardar Jaffar Ali. Released under the MIT License. See `LICENSE`.
