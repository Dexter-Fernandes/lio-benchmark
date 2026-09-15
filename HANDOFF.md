# lio-benchmark — agent handoff

Prepared: 14 September 2026. Updated: 15 September 2026. Status: foundation scaffolded and all selected data downloaded, verified, converted and inspected. **No odometry method is integrated and there are no benchmark results.**

## Goal and confirmed decisions

Build an interview portfolio project comparing LiDAR-inertial odometry methods on Hilti–Oxford 2022. Demonstrate reproducible integration, manually guided tuning, held-out evaluation, computational profiling and failure analysis.

- Create/use a **new repository named `lio-benchmark`**, not the existing `ranger-lio` project. Remote: `https://github.com/Dexter-Fernandes/lio-benchmark.git` (origin). Work is on the local branch `scaffold/foundation`, which has **not been pushed**.
- Tune on **exp14** and evaluate on other sequences with 6-DoF reference trajectories.
- Use **devcontainers** for execution and **Weights & Biases** for experiment tracking.
- Experiments are **manually guided**, not automated hyperparameter sweeps.
- Create scripts to download all necessary selected data, calibration and reference trajectories.
- User requested LOAM, LIO-SAM, GLIM, FAST-LIO, FAST-LIO2, RTAB-Map and additional applicable methods. Explain exclusions and distinguish variants accurately.
- User delegated metric recommendations to the assistant.
- A four-week target was mentioned earlier but is **not confirmed** for this project.

Suggested repository description: Reproducible LiDAR-inertial odometry benchmarking on Hilti–Oxford, with containerised pipelines, W&B experiment tracking, and held-out trajectory evaluation.

## Current state (15 September 2026)

Done on branch `scaffold/foundation` (see README.md for commands):

- **Python project** (`uv`, Python 3.11) with the `lio-bench` CLI, and the **tools image** `docker/tools/Dockerfile` (base and uv pinned by digest) with its devcontainer `.devcontainer/tools/`. `scripts/in-tools.sh` runs commands in the image and mounts data read-only except for data-writing commands. 60 tests pass on the host and in the container.
- **Manifest** `manifests/hilti22.yaml`: HF revision `e62017f9…`, sizes and published hashes (LFS SHA-256 or git blob SHA-1, taken from the HF API, none invented), licence, citation, groups and split. The Sheldonian reference scan and CAD files are opt-in groups and have not been downloaded.
- **Data** at `LIO_DATA_ROOT=/home/dexter/data/hilti22`, the same layout ranger-lio uses:
  - exp14, exp16 and exp18 ROS 1 bags, `imu_noise_calibration.bag`, ground truth and calibration files, all hash-verified (`_provenance/verified.json`).
  - exp14's MCAP was pre-existing (made by ranger-lio). exp16 and exp18 MCAPs were produced by `lio-bench data convert`. All three passed the equivalence check (`_provenance/conversions/`).
- **Inspection reports** for all three sequences (`_provenance/inspect/`), summarised in `docs/dataset.md`.
- **Evaluator** (`src/lio_benchmark/evaluation.py`): gap-aware association, SE(3) Umeyama with no scale, ATE, RPE at 1 s and 10 s, control-point errors, coverage and status. It cross-checks against evo and was exercised end to end on real exp14 ground truth, including the LiDAR-to-IMU frame conversion.
- **Run records and W&B** (`tracking.py`; `lio-bench run init|close`, `eval --run-dir`, `log`): local-first, W&B offline by default. Tested offline without credentials.
- **Docs:** `docs/protocol.md` (normative), `docs/dataset.md`, `docs/methods.md`, `docs/journal.md` (template, no entries).

Facts settled by measurement (details in docs/dataset.md):
- **GT quaternions** are (x, y, z, w) in a z-up world. The gravity check gives 0.65–4.7° for that reading versus 60–120° for (w, x, y, z). The 4.7° on exp18 is unexplained; see docs/dataset.md.
- **IMU orientation is all zeros, with `orientation_covariance[0] = 0`** (not flagged as absent). LIO-SAM needs a documented sensor-only orientation adapter or a named 6-axis derivative.
- **LiDAR per-point `timestamp`** is float64 absolute epoch seconds; the first point equals the header stamp and each scan spans 0.1 s. `ring` is u16 in 0–31 and point_step is 48.
- **Log time equals header stamp** in the bags, so the recording carries no receive-time or latency information.
- **Dense GT has gaps** (up to 1.3 s on exp18). exp18's dense GT ends 22.6 s before the sensors stop, and one exp18 control point lies outside the dense span.
- **Difficulty:** the official page rates exp14 Medium and exp16/exp18 Hard.

Not done: no method images, no adapters, no runs, no W&B entity or project, nothing pushed. Do not infer that the next agent's filesystem is the user's laptop.

## Hardware and execution constraints

User-reported machine:

| Component | Specification |
|---|---|
| Laptop | Acer Aspire F5-573G |
| OS | Kubuntu 26.04.1 LTS, x86_64 |
| Kernel | Linux 7.0.0-31-generic |
| CPU | Intel Core i7-7500U, 2 cores / 4 threads |
| GPUs | NVIDIA GeForce 940MX and Intel HD Graphics 620 |
| RAM | 11.55 GiB total; 7.14 GiB in use in supplied snapshot |
| Swap | 16.12 GiB |
| Root partition | 76.35 GiB total; approximately 54 GiB free |
| Home partition | 209.91 GiB total; approximately 111 GiB free |
| Desktop | KDE Plasma / Wayland; Bash shell |

Recommended defaults: one headless experiment at a time; CPU-only GLIM initially; one or two compilation jobs. Keep data/results on a configurable path under the home partition. Monitor container build cache on root separately. Do not assume the 940MX supports the selected CUDA environment or that any method runs in real time. Record thread limits and resource use.

## Dataset plan

Use **Hilti–Oxford 2022**, not another Hilti challenge edition.

| Sequence | Proposed purpose | Environment | Full bag size, approximate |
|---|---|---|---|
| exp14 | Development and manual tuning | Basement 2 | 6 GB |
| exp16 | Held-out evaluation | Attic to Upper Gallery 2 | 15 GB |
| exp18 | Held-out evaluation | Corridor Lower Gallery 2 | 8 GB |

The official page lists 6-DoF reference trajectories for these three sequences. exp16/exp18 are assistant recommendations consistent with the user's requested split. Many other sequences have sparse position-only ground truth and cannot support rotational error evaluation.

- Sensor platform includes Hesai PandarXT-32, cameras and IMU. Point clouds are PointCloud2 with individual point timing information.
- Ground truth is expressed in the **IMU frame**. Transform estimator outputs into that physical frame before evaluation.
- Download calibration and IMU noise resources separately.
- Inspect actual topics, point field types, timing units, ring information, IMU orientation validity, quaternion conventions and reference coverage before integration. **Done for all three sequences** (`lio-bench inspect`; see docs/dataset.md).
- Do not assume dense 6-DoF reference trajectories have the same provenance or accuracy as surveyed sparse position references. Document the distinction.
- Select explicit files with resumable downloads and verified integrity. Record source revisions, file sizes and hashes; never invent checksums.
- Three full bags total approximately 29 GB. Allow extra space for conversions and outputs. Keep data out of Git and preserve dataset attribution/licensing.
- Freeze configurations after exp14 tuning. Do not select parameters using exp16/exp18 results. These are held-out sequences within one dataset, not cross-sensor generalisation evidence.

Sources: [official dataset](https://hilti-challenge.com/dataset-2022), [official hosting](https://huggingface.co/datasets/Hilti-Research/hilti-slam-challenge-2022).

## Methods and unresolved compatibility

| Method | Proposed treatment |
|---|---|
| FAST-LIO2 | Core tightly coupled LIO; recommended first integration |
| FAST-LIO | Separate verified original implementation, pinned to its own revision |
| LIO-SAM | Core LIO; disable GPS and loop closure for the primary comparison. Bag orientation is **all zero** (measured), so an adapter or a 6-axis derivative is required |
| GLIM | CPU LiDAR-inertial odometry configuration; global mapping evaluated separately |
| DLIO | Recommended addition, not explicitly confirmed by user; upstream supports Hesai and 6-axis IMUs |
| RTAB-Map ICP + IMU | Explicitly labelled IMU-assisted ICP baseline; document actual IMU use |
| LOAM | Conditional on selected implementation and actual IMU integration |

Important distinctions:

- FAST-LIO2 with feature extraction enabled is **not original FAST-LIO**. Version differences include map management and other implementation changes.
- LOAM is ambiguous: original-style implementations can use IMU assistance; some derivatives are LiDAR-only. Pin and identify the actual algorithm.
- RTAB-Map is a framework supporting several odometry engines. Its LIO-SAM wrapper is not an independent estimator. Its own ICP + IMU configuration is the intended additional baseline; do not call it tightly coupled LIO without evidence.
- LIO-SAM upstream documents orientation estimates / a 9-axis IMU expectation. Inspect bag fields. If necessary, use a documented sensor-only orientation adapter or explicitly named 6-axis-compatible derivative such as LIORF. Do not silently label a derivative as upstream LIO-SAM.
- Never feed ground truth into initialisation, orientation estimation, deskewing or the estimator.
- Verify per-point time conversion and extrinsic transform direction; do not hide integration errors by tuning noise or registration settings.

References: [FAST-LIO](https://github.com/hku-mars/FAST_LIO), [FAST-LIO2 paper](https://arxiv.org/abs/2107.06829), [LIO-SAM](https://github.com/TixiaoShan/LIO-SAM), [GLIM](https://github.com/koide3/glim), [DLIO](https://github.com/vectr-ucla/direct_lidar_inertial_odometry), [RTAB-Map odometry](https://github.com/introlab/rtabmap/blob/master/corelib/src/Odometry.cpp), [LOAM candidate](https://github.com/laboshinl/loam_velodyne).

## Proposed container environments

These are **design targets, not validated image tags or builds**. Recheck upstream requirements and pin working revisions/digests.

| Image role | Proposed base environment |
|---|---|
| FAST-LIO2 | Ubuntu 20.04 / ROS Noetic |
| Original FAST-LIO | Supported environment of selected original implementation |
| LIO-SAM | Ubuntu 20.04 / ROS Noetic; separately pinned GTSAM |
| DLIO | Ubuntu 20.04 / ROS Noetic |
| GLIM CPU | Ubuntu 22.04 / ROS 2 Humble; no CUDA |
| RTAB-Map | Ubuntu 22.04 / ROS 2 Humble |
| Evaluation/downloader | Python 3.11 slim |
| LOAM | Determined by chosen implementation |

Share suitable base layers but isolate conflicting dependencies. Support devcontainer development and unattended runs. Mount data read-only and results separately. Make GUI forwarding optional. Use original ROS1 bags for ROS1 methods and verified converted inputs for ROS2 methods; preserve timing/point fields and verify message counts. No live ROS bridge is assumed necessary.

GLIM documents CPU installation on 22.04/Humble; DLIO documents 20.04/Noetic. LIO-SAM's bundled Docker instructions describe older Kinetic, so a Noetic build needs validation. [GLIM installation](https://koide3.github.io/glim/installation.html).

## Benchmark protocol

Primary comparison: **online odometry**, with loop closure, GPS, prior maps and offline refinement disabled. Retain each method's local estimation/mapping machinery. Save online poses as emitted; do not replace them with retrospectively optimised poses. Full-SLAM/global-refinement results may be a separate secondary comparison.

Compare a correctly dataset-adapted baseline against manually tuned configurations. Topics, units and supplied calibration must already be correct in both.

| Measure | Recommended reporting |
|---|---|
| Position accuracy | ATE RMSE, median and p95 in metres; SE(3) alignment, no scale correction |
| Local drift | Translational and rotational RPE; initially 1 s and 10 s intervals |
| Reliability | Initialisation time, coverage, failures, resets, missing outputs |
| Compute | Median/p95 processing time, total wall runtime, peak RAM |
| Real-time behaviour | Backlog, dropped measurements and pose latency at 1x replay |
| Map quality | Selected visual comparisons first; optional reference-map evaluation later |

Specify timestamp association, evaluation frame, alignment, pose-pair selection and valid intervals. Never interpolate across large gaps. Report coverage with accuracy so failed partial trajectories cannot appear to win. Do not average incompatible metric definitions.

For accuracy runs, use sufficiently slow playback to avoid overload while preserving original sensor timestamps. Verify complete processing and record playback rate. Separately test 1x real-time behaviour. Slow replay is not evidence of real-time capability. Measure latency with compatible clocks, not historical bag timestamps subtracted directly from current wall time. Document whether timing includes preprocessing, queues, registration and mapping.

Reference: [evo metrics](https://github.com/MichaelGrupp/evo/wiki/Metrics).

## Manually guided W&B workflow

For each experiment record hypothesis, parent run, exact change, results, interpretation and keep/revert/investigate decision. Establish a complete baseline first; change one parameter family at a time. Repeat shortlisted configurations enough to identify meaningful variability. Record all attempts and tuning effort; equal effort has not been agreed and should not be claimed.

Log method/source commit/patches; full resolved config and hash; container and dependency identities; dataset/calibration hashes; preprocessing; time range; hardware/thread settings; playback rate; seed if relevant; metrics; coverage/failure status; trajectory; plots/logs; selected map outputs. Preserve local JSON/CSV and offline logging so W&B credentials are not a prerequisite for development. W&B entity/project and credentials remain unspecified. Never commit secrets.

## Deliverables and suggested structure

| Path | Purpose |
|---|---|
| README.md | Scope, setup, quick start, results and limitations |
| HANDOFF.md | Continuation state |
| .devcontainer/ | Per-method development configurations |
| docker/ | Images and dependency pins |
| manifests/ | Download files, hashes, revisions and dataset split |
| configs/ | Baseline, experimental and frozen configurations |
| adapters/ | Input conversion and method integration |
| scripts/ | Download, inspect, run, evaluate, log and report |
| src/lio_benchmark/ | Shared code if useful |
| tests/ | Timing, transforms, conversion and evaluator correctness |
| docs/ | Protocol, method notes, experiment journal and analysis |
| results/ | Small curated publishable tables and plots |

Required scripts/capabilities: selective resumable downloads with disk-space/integrity checks; sensor/calibration inspection; input preparation; isolated launch/readiness/timeout/shutdown; fresh estimator state; completion detection; common trajectory export; gap-aware evaluation; W&B/local logging; repeatable report generation.

Meaningful tests: known rigid transforms, timestamp conversion, identity trajectory error, known perturbations, missing sections and incomplete-run detection. Avoid treating placeholder tests as evidence that a method works on real data.

## .gitignore guidance already given

Applied: the repository `.gitignore` now contains the entries below plus the standard Python template entries (caches, virtualenvs, build outputs).

```gitignore
# ROS / C++ build outputs
build/
devel/
install/
log/
logs/
CMakeFiles/
CMakeCache.txt
compile_commands.json

# Data and generated maps
data/
datasets/
*.bag
*.bag.active
*.db3
*.mcap
*.pcd
*.ply
*.e57

# Local experiment outputs
runs/
outputs/
wandb/

# Credentials and local settings
.env
.env.*
!.env.example
```

Keep devcontainer files, Dockerfiles, configs, manifests and curated results tracked. If small test fixtures need an ignored extension, add explicit exceptions rather than committing large datasets. Retain the Python template's standard cache/virtualenv exclusions.

## Next steps

1. ~~Inspect the workspace~~, ~~scaffold the repository, manifest and protocol~~, ~~download and inspect the data~~. All done on 15 September 2026.
2. Review the `scaffold/foundation` branch with the user, then push it or merge it to `main` (ask first).
3. **FAST-LIO2 baseline on exp14:**
   - Build a pinned Noetic image in `docker/fast_lio2/` and `.devcontainer/fast_lio2/`.
   - Write an input adapter in `adapters/` that converts the absolute per-point `timestamp` into the relative time field FAST-LIO2 expects, with unit tests on real scans.
   - Take the extrinsic from `configs/dataset/hilti22.yaml`, with a known-answer check of FAST-LIO2's convention.
   - Set minimum range and blind zone from the measured ranges.
   - Wrap the run with launch, readiness, timeout and completion detection at slow playback.
   - Export the trajectory to TUM, then `lio-bench run init` → `eval --frame imu|lidar --run-dir` → `run close` → `log`.
4. Add DLIO, LIO-SAM (resolve the orientation adapter versus LIORF and name it explicitly) and GLIM through the same interface. Humble images may need `data convert --dst-version`. Resolve original FAST-LIO, RTAB-Map ICP+IMU and LOAM without silently dropping scope.
5. Run the exp14 experiments, freeze configurations, evaluate exp16 and exp18, and publish reproducible results with limitations.

The first milestone is one verified end-to-end baseline, not several partially working integrations. Ask only for unresolved information that materially blocks the next action. Remote URL/visibility, deadline, W&B identity and exact variants remain open; settled decisions do not need reconfirmation. Do not claim benchmark rankings before runs exist.

## Suggested skills

- **handoff**: update this continuation document after substantive progress.
- **domain-modeling**: if defining CONTEXT.md, terminology or architecture decision records.
- **personal-context**: only if missing prior context materially affects work; the current plan is captured here.
- **openai-library:library**: if delivering standalone files through ChatGPT; Git-backed project files should stay in the repository workflow.
- **documents/pdf**: only if a formatted report is requested later.

Read applicable repository AGENTS.md and skill instructions before acting. No multi-agent implementation has been requested; this handoff is for a fresh agent to continue.
