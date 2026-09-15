# lio-benchmark — agent handoff

Prepared: 14 September 2026. Updated: 15 September 2026. Status: foundation done, **FAST-LIO2
fully integrated, tuned and evaluated held-out**, merged to `main`. LIO-SAM is next.

## Goal and confirmed decisions

Build an interview portfolio project comparing LiDAR-inertial odometry methods on Hilti–Oxford 2022. Demonstrate reproducible integration, tuning (manual, then automated search once a manual phase bounds the search region), held-out evaluation, and failure analysis.

- Repo: `https://github.com/Dexter-Fernandes/lio-benchmark.git` (origin). Work happens on
  `feat/<method>-integration` branches, fast-forward merged into `main` when done (confirm with
  the user before merging/pushing).
- Tune on **exp14**; hold out **exp16, exp18** (see [docs/protocol.md](docs/protocol.md) §2).
- Devcontainers for execution, Weights & Biases for tracking (**online by default** now — see
  below, this changed from the original "offline first" plan).
- Tuning is two-phase (`docs/protocol.md` §6): manual/hypothesis-driven first, then an
  automated (Bayesian) search once phase 1 has bounded a sensible region. Not a blind sweep
  from upstream defaults.
- Methods requested: LOAM, LIO-SAM, GLIM, FAST-LIO, FAST-LIO2, RTAB-Map and other applicable
  methods. Explain exclusions and distinguish variants accurately (`docs/methods.md`).
- User delegated metric recommendations to the assistant.

## Current state (15 September 2026)

**Foundation** (from the original `scaffold/foundation` branch, now in `main`): `lio-bench` CLI,
tools image + devcontainer, manifest, verified/converted/inspected Hilti-Oxford data for
exp14/exp16/exp18, the evaluator, run-record system. See README.md for commands; unchanged in
substance since the last handoff, so not repeated here in full — read `docs/dataset.md` for the
measured sensor facts (GT quaternion order, IMU orientation validity, per-point timestamp
format, extrinsics) that **every** method integration needs.

**FAST-LIO2: done, merged to `main`.** This is the reference integration for every method after
it — read `docs/methods.md`'s "FAST-LIO2 integration" section and `scripts/run_fast_lio2.sh`
before starting LIO-SAM; the pattern (adapter, config, run wrapper, tuning, held-out eval, map
artifacts) repeats with method-specific changes only. Summary:

- `docker/fast_lio2/Dockerfile` + `.devcontainer/fast_lio2/`: ROS Noetic, `hku-mars/FAST_LIO`
  pinned at `7cc4175`, base image pinned by digest.
- `adapters/fast_lio2/`: point-time adapter (absolute epoch `timestamp` → FAST-LIO2's relative
  `time` field), unit-tested in `tests/test_adapters.py`; a `/Odometry` → TUM exporter.
- `configs/fast_lio2/hilti22.yaml`: frozen, tuned config (measured IMU noise covariance,
  measured registration voxel size). `scripts/fast_lio2_candidate.py` generates dotted-override
  candidates for tuning attempts; reusable as-is for any method's config.
- `scripts/run_fast_lio2.sh`: launch/readiness/timeout/shutdown wrapper, exports
  trajectory.tum + map.pcd. **Read this before writing a LIO-SAM equivalent** — it has two
  non-obvious fixes worth not re-discovering: (1) `filter_size_surf`/`filter_size_map` are
  flat top-level rosparams, not nested — check each method's actual `nh.param()` calls rather
  than assuming config nesting from a launch file's XML structure; (2) never use
  `rosbag play --clock`/`use_sim_time` with a node whose shutdown-save logic runs inside
  `ros::Rate::sleep()` — sim time stops advancing the instant bag playback ends, and the node
  hangs forever waiting on `/clock`. Use wall-clock ROS time; every method here keys off
  message `header.stamp`, never `ros::Time::now()`, so this costs nothing.
- Tuned on exp14 (`docs/journal.md`): measured IMU noise covariance (kept), measured
  registration voxel size 0.2 m (kept), a 15-trial Bayesian sweep over the phase-1-bounded
  region (no improvement, negative result — config unchanged).
- Held out on exp16 (catastrophic divergence starting ~t=170-180s, open failure-analysis case,
  root cause not yet investigated) and exp18 (normal generalization gap).
- Map artifacts (`map.pcd`/`map.png`) generated per run; `lio-bench view <run_id>` / `--traj`
  visualizes them (GLFW/Wayland interactive viewer is broken on this user's desktop — `--png`
  is the reliable fallback, always available).

**W&B**: entity is the user's default (`retro.aspect520@gmail.com`'s account), project
`lio-benchmark`. `WANDB_MODE` defaults to **online** now (not offline as originally planned) —
every run lands on the dashboard automatically. `scripts/wandb_setup.sh` does one-time login.
`lio-bench report` builds/updates a saved W&B Report comparing every logged run.

Not done: LIO-SAM, GLIM, DLIO, original FAST-LIO, RTAB-Map, LOAM. No cross-method comparison
yet (only one method has results).

## Hardware and execution constraints

User-reported machine (unchanged):

| Component | Specification |
|---|---|
| Laptop | Acer Aspire F5-573G |
| OS | Kubuntu 26.04.1 LTS, x86_64 |
| Kernel | Linux 7.0.0-31-generic |
| CPU | Intel Core i7-7500U, 2 cores / 4 threads |
| GPUs | NVIDIA GeForce 940MX and Intel HD Graphics 620 |
| RAM | 11.55 GiB total |
| Swap | 16.12 GiB |
| Root partition | ~54 GiB free (build cache) |
| Home partition | ~111 GiB free (data, out of Git) |
| Desktop | KDE Plasma / Wayland |

One headless experiment at a time; CPU-only for GLIM; one or two compile jobs. FAST-LIO2 ran
fine on this hardware at 1.0x real-time playback — a reasonable default to try for LIO-SAM too,
falling back to slower playback only if it overloads.

## LIO-SAM: next milestone

Follow the exact FAST-LIO2 pattern (`docker/fast_lio2/`, `adapters/fast_lio2/`,
`configs/fast_lio2/`, `scripts/run_fast_lio2.sh`, `docs/methods.md`'s FAST-LIO2 section) with a
new `docker/lio_sam/`, `adapters/lio_sam/`, `configs/lio_sam/`, `scripts/run_lio_sam.sh`. Start
a new branch `feat/lio-sam-integration`.

Method-specific work, in order:

1. **Resolve the orientation problem before anything else** (`docs/methods.md` point 1,
   `docs/dataset.md`). Hilti's `/alphasense/imu` has an all-zero orientation quaternion with
   `orientation_covariance[0] = 0` — not flagged absent, so LIO-SAM would silently consume a
   garbage quaternion if it reads `msg.orientation`. Check upstream (`TixiaoShan/LIO-SAM`)
   source for exactly where/whether it reads `orientation` (IMU preintegration and the
   `imuHandler` in particular). Two options, per HANDOFF's original plan:
   - a documented, sensor-only orientation adapter (complementary or Madgwick filter on the
     same 6-axis IMU, parameters recorded, never touching ground truth), or
   - an explicitly named 6-axis-compatible derivative (e.g. LIORF) — never silently relabel
     a derivative as upstream LIO-SAM.
   This decision gates the rest of the integration; don't start the Dockerfile before it's made.
2. **Pin the source and base image.** LIO-SAM's bundled Docker instructions target Kinetic; a
   Noetic build needs its own validation (build GTSAM, PCL, etc. against Noetic — check
   upstream issues/forks for a known-working Noetic combination before improvising one).
3. **Point-cloud adapter.** LIO-SAM's `imageProjection.cpp` reads a per-point relative time
   field (check its exact name/type/units against Hilti's absolute `timestamp`, same shape of
   problem as `adapters/fast_lio2/pointcloud_adapter.py` — reuse the same unit-testing pattern
   against real scans in `tests/test_adapters.py`).
4. **Extrinsics.** `configs/dataset/hilti22.yaml`'s `T_I_L` is the shared source of truth; check
   LIO-SAM's own extrinsic convention (it typically wants `extrinsicRot`/`extrinsicTrans` as
   `T_I_L` or `T_L_I` — verify against source, don't assume) with a known-answer test like
   `frames.check_lidar_extrinsics`.
5. **Config.** `configs/lio_sam/hilti22.yaml`, dataset-adapted baseline only (topics, units,
   extrinsics, blind zone/min range from measured ranges — `docs/dataset.md`) — no tuning yet.
   Disable GPS factor and loop closure for the primary online-odometry comparison
   (`docs/protocol.md` §1).
6. **Run wrapper** (`scripts/run_lio_sam.sh`): same shape as `run_fast_lio2.sh` — roscore,
   adapter(s), an odometry→TUM exporter, the LIO-SAM node, readiness wait, timeout, SIGINT
   shutdown if it saves anything on exit, trajectory + map export. Check whether LIO-SAM's
   output topic publishes IMU or LiDAR body poses before choosing `lio-bench eval --frame`.
7. **Baseline run** on exp14: `lio-bench run init` → run → `eval --frame ... --run-dir` →
   `run close` → `log`. This is the first checkpoint — a working, dataset-adapted baseline,
   not a tuned one. Journal it (`docs/journal.md`) same as the FAST-LIO2 baseline entry.
8. Only after a verified baseline: phase-1 manual tuning (`docs/protocol.md` §6.1), then
   phase-2 automated search only if phase 1 finds a sensible region (§6.2,
   `scripts/fast_lio2_sweep.py` is a template — swap in LIO-SAM's config path and image).
9. Freeze the config, evaluate exp16/exp18 held out, journal the results (don't tune on them).

## Benchmark protocol

Normative document: [docs/protocol.md](docs/protocol.md) — read it, don't re-derive it here.
Covers: online-odometry scope, data split, frames/inputs, gap-aware metrics (ATE/RPE
definitions, association, alignment, coverage), reliability/compute reporting, and the
two-phase tuning process. `configs/eval/default.yaml` holds the frozen evaluation parameters;
`src/lio_benchmark/evaluation.py` is the implementation.

## Deliverables and structure

| Path | Purpose |
|---|---|
| README.md | Scope, setup, quick start, status |
| HANDOFF.md | This file — continuation state |
| .devcontainer/, docker/ | Per-method dev environments and images, one per method |
| manifests/ | Dataset files, hashes, revisions, split |
| configs/ | Per-method baseline/frozen configs; `configs/eval/` shared evaluation params |
| adapters/ | Per-method input/output conversion, each with real unit tests |
| scripts/ | Download, inspect, run, tune, evaluate, log, report — reuse across methods |
| src/lio_benchmark/ | Shared library: manifest, download, evaluation, tracking, CLI |
| tests/ | Hashing, download, manifest, frames, trajectory, evaluator, adapters, tracking |
| docs/ | protocol (normative), dataset (measured facts), methods (per-method notes and
integration decisions), journal (chronological experiment log) |
| results/ | Curated publishable tables/plots (none yet — needs ≥2 methods) |

## Next steps

1. ~~Foundation~~, ~~FAST-LIO2 baseline/tuning/held-out eval~~ — done, see above.
2. **LIO-SAM integration** — see the milestone plan above. Start with the orientation decision.
3. Add GLIM, DLIO, original FAST-LIO, RTAB-Map ICP+IMU through the same interface. Resolve
   LOAM's implementation ambiguity or drop it with a stated reason (`docs/methods.md`
   "Exclusions" section — currently empty).
4. Once ≥2 methods have frozen configs and held-out results: first cross-method comparison,
   `results/`, `lio-bench report`.

Ask only for information that materially blocks the next action (LIO-SAM orientation adapter
choice is the one live decision above). Do not claim benchmark rankings before ≥2 methods have
real runs.

## Suggested skills

- **handoff**: update this document after substantive progress (a method fully integrated and
  merged, a protocol change, a milestone).
- **domain-modeling**: if defining CONTEXT.md, terminology or architecture decision records.

Read `docs/methods.md`, `docs/protocol.md` and `docs/journal.md` before acting — they carry
the actual decisions and measured facts; this file is a pointer and a punch list, not the
source of truth.
