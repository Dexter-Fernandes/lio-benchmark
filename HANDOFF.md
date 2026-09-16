# lio-benchmark — agent handoff

Prepared: 14 September 2026. Updated: 16 September 2026. Status: foundation done, **FAST-LIO2
fully integrated, tuned and evaluated held-out**, merged to `main`. **LIO-SAM runs end-to-end,
its rotation failure is root-caused and fixed**, merged to `main`. Merging was a separate
question from comparability: the code is correct, but the method still owes the phase-1 tuning
it skipped, a re-run sweep and a fresh held-out evaluation before its numbers mean anything.
See "LIO-SAM" below. **GLIM is now also merged to `main`** (`feat/glim-integration`, fast-forward,
commit `2401ad4`): CPU-backend phase-1, a phase-2 sweep, and held-out evaluation are all done,
but the frozen config **fails to generalize to both held-out sequences** (exp16, exp18) despite
being competitive with FAST-LIO2 on exp14. A GPU backend was also built
(`docker/glim_gpu/`, `configs/glim/hilti22_gpu.yaml`) but is **hardware-blocked and root-caused,
not fixable on this machine**: the only GPU (GeForce 940MX, compute capability 5.0) is one
generation below the compute capability 6.0 that `gtsam_points`' `cudaMallocAsync`/
`cudaFreeAsync` calls require -- confirmed at the source level (no compatibility shim is wired
in, no older release predates the async allocator, upstream's own `CMakeLists.txt` targets
Turing+ only). See "GLIM" below. Not a finished method yet on either backend.

**Next session, in order:** LIO-SAM's still-owed phase-1 tuning, led by `imuRPYWeight` 0.0 vs
0.01 (§ LIO-SAM, "Next action") -- now the single highest-value open item across all three
methods. GLIM's held-out failure root-cause (§ GLIM, "Next action") is still open but was
explicitly deprioritized this session in favour of merging what's already complete; pick it up
when there's appetite for another GLIM-specific investigation. The GLIM GPU backend needs
compute-capability-6.0+ hardware (a desktop RTX/GTX-10-series+ card, or a cloud GPU instance)
to go any further -- it cannot be progressed on this machine at all.

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

## Current state (16 September 2026)

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

Not done (working): DLIO, original FAST-LIO, RTAB-Map, LOAM. No cross-method comparison yet
(only FAST-LIO2 has trustworthy held-out results; LIO-SAM and GLIM both still owe tuning/
generalization work before their numbers are comparable).

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

One headless experiment at a time; one or two compile jobs. The 940MX is compute capability
5.0 -- confirmed too old for GLIM's GPU backend (`gtsam_points` needs 6.0+), so GLIM is
CPU-only here in practice, even though a GPU image exists. FAST-LIO2 ran
fine on this hardware at 1.0x real-time playback — a reasonable default to try for LIO-SAM too,
falling back to slower playback only if it overloads.

## LIO-SAM: rotation failure root-caused and fixed; phase-1 tuning still owed

Branch `feat/lio-sam-integration` (not merged -- confirm with the user before merging). Full
scaffolding follows the FAST-LIO2 pattern (`docker/lio_sam/`, `adapters/lio_sam/`,
`configs/lio_sam/`, `scripts/run_lio_sam.sh`); genuine upstream `TixiaoShan/LIO-SAM` plus a
Madgwick orientation adapter (required: `imuConverter()` shuts the node down on Hilti's
all-zero orientation quaternion). Full detail: `docs/methods.md` "LIO-SAM integration",
`docs/journal.md` (every run, newest last, plus the "LIO-SAM integration summary").

**What was wrong.** Every early run (baseline, 8 sweep trials, both held-out, four
diagnostics) had ATE rot RMSE 100-170 deg. Root cause: `mapOptmization::LMOptimization()`
zeroes any scan-to-map update direction whose J^T J eigenvalue is below a hardcoded 100,
an outdoor-Velodyne scale. On this ~1 m-range scene it flagged 91% of scans, discarded the
tilt/z updates, and the pose rode the IMU-preintegration guess -- visible as an identical,
deterministic tilt to -30 deg and 1.1 m sink during the 6 s the rig is provably static at
the start of exp14. Found by comparing estimates against GT in that static window and then
recording LIO-SAM's internals (`LIO_SAM_RECORD` in `scripts/run_lio_sam.sh`, analysed by
`scripts/lio_sam_diag.py`: per-scan degenerate flag, feature counts, guess vs output, IMU
delivery).

**What changed (all in `configs/lio_sam/hilti22.yaml`, each justified in its comment):**

1. `imuRPYWeight: 0.0` (run `20260915T222509Z`): the Madgwick roll/pitch slerp cost >10x in
   translation; rotation unchanged.
2. `degeneracyThreshold: 0.0` via `docker/lio_sam/degeneracy_threshold.patch` (new param,
   default 100 = upstream; also logs the six eigenvalues per scan). exp14 went from
   29.3 m / 129 deg to 1.07 m / 18.8 deg, RPE 1 s rot 26.6 -> 4.5 deg, resets 46 -> 0
   (runs `20260915T230256Z` diagnosis, `20260915T230642Z` fix). Measured eigenvalue floor
   while static is ~30; a measured 10 (`20260915T231202Z`) was not better, reverted.
3. `imuGravity: 9.663` (run `20260915T231502Z`): measured at-rest norm; the preintegration
   guess no longer sinks on a static rig. Kept on mechanism evidence.

**Upstream README data-prep requirements: verified.** Point `time` relative and in [0, 0.1] s,
`ring` present, dense cloud, IMU at 399.2 Hz (README wants >=200), and REP-105 after
`extrinsicRot` (measured at-rest specific force maps to z = +9.66) with gyro axes confirmed
against GT (per-axis correlation 0.9994/0.9997/1.0000, slope ~1.00). `extrinsicRPY` matches
the README's `q_lb` definition. Two deviations, both documented in `docs/methods.md`: the
sensor is 6-axis, not the required 9-axis, so a Madgwick adapter substitutes (tilt error vs
GT: 0.70 deg over the static init window, 1.60 deg mean overall); and `Horizon_SCAN` is
knowingly 1800 rather than the measured-correct 2000, see the phase-1 note below. The README's
manual "rotate the sensor suite and watch the printed IMU values" check is impossible on a
recorded bag and was replaced by the GT comparisons above.

**What the 9-axis deviation costs (measured).** Hilti's own GT orientation was fed to LIO-SAM
as a synthetic perfect 9-axis IMU in a 2x2 against `imuRPYWeight` (runs `20260916T0006*`;
**GT-fed, violates `docs/protocol.md` §3, never reportable** -- the node lives in a scratchpad,
not `adapters/`, and warns on every run). At the frozen `imuRPYWeight: 0.0` the orientation
source makes no measurable difference, so the deviation is moot as configured. With upstream's
`0.01` restored, a perfect orientation is worth about 0.19 m ATE translation, 3.8 deg ATE
rotation and 5.9 deg RPE 10 s rotation over our Madgwick output. The same experiment showed
`imuRPYWeight: 0.01` is **no longer harmful** post-degeneracy-fix (it was set to 0 on a
pre-fix diagnostic whose damage was entangled with the real bug), so **0.0 vs 0.01 is now an
open phase-1 item, not a settled decision** -- it is the single change most likely to improve
this method, and it is free.

**Cross-checked on upstream's own data.** LIO-SAM's `walking_dataset` (VLP-16, outdoor, real
9-axis Microstrain, upstream `params.yaml` verbatim) runs clean through this image: 3222 poses,
zero warnings, walking-pace trajectory over 808 m. Its smallest LM eigenvalue has a median of
564.6 against Hilti's 42.2, so upstream's hardcoded threshold of 100 trips on 2.5% of scans
there and 73% here. The root cause is a range assumption baked into upstream, not a fault in
this integration. Bag kept at `~/data/lio_sam_demo/walking_dataset.bag` (3.8 GB, delete if you
want the space); it is outside the benchmark manifest and has no ground truth, so it can
validate behaviour but never produce ATE/RPE.

**Current exp14 numbers (fixed config, single runs):** ATE trans 0.65-1.07 m, ATE rot
19-22 deg, RPE 1 s 0.16-0.19 m / 4.4-5.4 deg, RPE 10 s rot 6-27 deg. FAST-LIO2 on the same
sequence: 0.04 m / 0.8 deg. The spread is the fixed config's own run-to-run variance
(repeat `20260915T231728Z`), so no single-run comparison smaller than it means anything.

**Next action for whoever picks this up (in order):** merge first (§ Merge readiness) — the
correctness blocker that held this branch back is gone, and nothing below changes the code
that would merge. Then:

1. Phase-1 manual tuning (`docs/protocol.md` §6.1), which this method skipped: start with
   3 repeats of the frozen config, then the same at playback rate 0.5 (suspected variance
   source: rate-1.0 playback on a 2c/4t machine; LIO-SAM's mapping node has queue size 1 and
   drops scans it cannot process in time). Then single changes with repeats. Two are already
   tried once and reverted as not-shown-better, both genuinely unsettled against this spread:
   `degeneracyThreshold` 0 vs 10, and `Horizon_SCAN` 1800 vs 2000 -- note 2000 is the
   *physically correct* value (measured 0.18 deg azimuth step; 1800 discards 9.7% of in-range
   returns into occupied range-image cells vs 2.0%), kept at 1800 only because the single run
   scored worse, so settle it with repeats rather than inheriting the wrong value. Highest
   value of all: `imuRPYWeight` 0.0 vs 0.01, see the 9-axis paragraph above. Then leaf sizes
   (FAST-LIO2 needed 0.5 -> 0.2 m here).
2. Phase-2 sweep bounded by phase-1, then a fresh held-out evaluation on exp16/exp18. The
   old sweep (`udrqijbp`) and held-out runs describe the bug, not the method; never compare
   against them.
3. Only then are LIO-SAM's numbers usable for the cross-method comparison.

Launch pattern (the image bakes in the config and wrapper, so mount both over it):
```
docker run --rm -v $LIO_DATA_ROOT:/data/hilti22:ro -v $(pwd)/runs:/runs \
  -v $(pwd)/configs:/configs:ro -v $(pwd)/scripts/run_lio_sam.sh:/run_lio_sam.sh:ro \
  [-e LIO_SAM_CONFIG=/runs/_candidates/<x>.yaml] [-e LIO_SAM_RECORD=/runs/<id>/diag.bag] \
  lio-benchmark/lio_sam:dev /run_lio_sam.sh /data/hilti22/rosbags/<seq>.bag \
  /runs/<id>/raw_lio_sam.tum 600 1.0 2>&1 | tee runs/<id>/lio_sam.log
```
`lio-bench eval <seq> <tum> --frame lidar --run-dir <run>` (LIO-SAM publishes lidar-frame
poses). Rebuilding the image after a patch change recompiles only the LIO-SAM layer.

## GLIM: merged to `main`, CPU backend tuned but not held-out-comparable, GPU backend hardware-blocked

Merged from `feat/glim-integration` (fast-forward, `2401ad4`). Full detail: `docs/methods.md`
"GLIM integration" and "GLIM GPU backend", `docs/journal.md` "GLIM integration and phase-1
tuning summary" and "GLIM GPU backend attempt".

- **Image:** `docker/glim/Dockerfile` installs `ros-humble-glim-ros` 1.2.2-0jammy from
  koide3's own official PPA (no CUDA), not built from source. Building GTSAM +
  `gtsam_points` + `glim` + `glim_ros2` from source was tried first and abandoned: the
  `ppa:borglab/gtsam-release-4.0` package LIO-SAM uses does not actually publish `jammy`
  (checked directly, its Launchpad overview page is misleading) and `gtsam_points` has moved
  to GTSAM 4.3a1 regardless. The resulting image is ~550 MB vs. the ~6 GB from-source images.
- **No point-cloud or orientation adapter needed**, unlike FAST-LIO2/LIO-SAM -- verified
  against GLIM's own source: it auto-detects Hilti's exact per-point time/ring/intensity
  field names, and never reads IMU orientation. The "adapter" is config values only
  (`configs/glim/hilti22.yaml`).
- **Data:** exp14's rosbag2/MCAP conversion needed regenerating at metadata version 5
  (`lio-bench data convert exp14 --dst-version 5`) -- ROS 2 Humble can't parse the original
  version-9 metadata. exp16/exp18 still need the same treatment before GLIM can use them
  (not done; their held-out evaluation is a later phase).
- **Two real runtime bugs**, found only by running it: an empty `ros.image_topic` crashes the
  node outright (`rclcpp::exceptions::InvalidTopicNameError`); the config was first written
  against GLIM's GitHub `master` branch, which disagrees with the pinned stable package on
  real field names/enum values (`sensors.imu_bias_noise` split differently,
  `initialization_mode: "ROBUST"` doesn't exist on 1.2.2) -- fixed by dumping the actually
  installed `config/*.json` from inside the built image and reconciling against that.
- **Phase-1 tuning on exp14 (`docs/protocol.md` #6.1):** adapted baseline established (3
  repeats: ATE trans RMSE 0.51-1.69 m, rot RMSE 16.7-36.6 deg -- large run-to-run spread, same
  lesson as LIO-SAM). `odometry_cpu.ivox_resolution` 1.0 -> 0.2 m **kept** (3 repeats:
  0.088-0.106 m / 1.4-2.2 deg, competitive with FAST-LIO2's 0.04 m / 0.8 deg -- direct
  analogue of FAST-LIO2's `filter_size_surf`/`filter_size_map` finding). `ivox_resolution`
  0.1 m, `registration_type` VGICP (matched resolution), and `num_threads` 4 all tried and
  **reverted** (not shown better; VGICP clearly worse). All 12 runs logged to W&B.
- **Phase-2 Bayesian sweep on exp14 (`docs/protocol.md` #6.2, sweep `e76281yq`,
  `scripts/glim_sweep.py`):** 20 trials, deliberately wider-than-typical ranges (a documented
  deviation -- only `ivox_resolution` has a phase-1 finding, IMU noise units are unverified).
  ATE trans RMSE spanned 0.093-2.588 m; best trial (0.093 m / 1.67 deg) landed inside the kept
  baseline's own repeat spread, and the top 10 trials showed no consistent parameter pattern
  -- given the method's known run-to-run variance at a *fixed* config, this sweep (no repeats
  per point) can't separate real effects from noise. No config change; frozen baseline
  unchanged. Real lesson for next time: repeat candidate points before trusting a ranking.
- **Held-out evaluation on exp16/exp18 (`docs/protocol.md` #6, `docs/journal.md`).** The
  frozen config **fails on both** held-out sequences: exp16 ATE trans 4.61 m / rot 106.8 deg;
  exp18 ATE trans 3.24 m / rot 43.4 deg -- both far worse than exp14 (0.09-0.11 m / 1.4-2.2
  deg) and both far worse than FAST-LIO2's held-out numbers. Unlike FAST-LIO2 (exp16
  catastrophic + sequence-specific, exp18 a normal generalization gap), **GLIM fails on both**
  held-out sequences with the same shape: bounded trajectory (no runaway blow-up), full
  coverage, but badly wrong rotation and z drift far past each sequence's true z range. Two
  unconfirmed hypotheses (root cause not investigated): (1) `initialization_mode` is forced to
  `"LOOSE"` on this pinned package (`"ROBUST"` isn't recognized) -- GitHub `master` calls
  `LOOSE` deprecated, and exp14's clean 6 s static start may mask a weakness a less-static
  held-out start exposes; (2) GLIM estimates gravity as part of its factor-graph state rather
  than a fixed constant (unlike LIO-SAM's `imuGravity` bug), so that specific failure mode is
  probably ruled out, though unconfirmed against the pinned package. **GLIM is not currently
  comparable to FAST-LIO2 on generalization** -- only on the exp14 tune split.

**GPU backend: built, hardware-blocked on this machine, root-caused.**
`docker/glim_gpu/Dockerfile` (`FROM koide3/glim_ros2:humble_cuda12.2`, upstream's own prebuilt
image) and `configs/glim/hilti22_gpu.yaml` are complete, and `scripts/glim_materialize_config.py`
is backend-aware. Every attempted run on this host fails identically regardless of config:
`cudaErrorNotSupported` -> `GPU points/covs not allocated!!` -> NaN pose. Root cause, confirmed
at the source level (not just inferred): the only GPU here is a GeForce 940MX (Maxwell,
compute capability 5.0); `gtsam_points` calls `cudaMallocAsync`/`cudaFreeAsync` directly in
`cuda_memory.cu`/`cuda_buffer.cu`, which need compute capability 6.0+ (Pascal+) per NVIDIA's
own docs. Checked for a workaround and found none: the repo's one CUDA-version compatibility
shim (`cuda_malloc_async.hpp`, falls back to plain `cudaMalloc`/`cudaFree` below CUDA 11.0) is
never `#include`d anywhere (GitHub code search, zero hits) so it's dead code; the async
allocator has been there since the file's 2021 origin, so no older release predates it either;
and upstream's own `CMakeLists.txt` hardcodes Turing-and-newer (`sm_75+`) as its supported
architecture list, overriding CMake's own Maxwell default rather than accepting it. **This
cannot be progressed on this machine at all** -- it needs a compute-capability-6.0+ GPU
(desktop RTX/GTX-10-series+, or a cloud instance) to go any further. Also fixed along the way,
independent of the hardware wall, kept for both backends: `scripts/run_glim.sh` now passes the
`.mcap` file directly to `glim_rosbag` rather than its containing directory -- this image's
newer `glim_rosbag` build has a real bug where the directory path opens with
`storage_id="sqlite3"` instead of respecting `metadata.yaml`'s declared `mcap` format,
reproduced directly (`ros2 bag info` on the identical path reads it correctly, so the plugin
itself is fine -- the bug is specific to `glim_rosbag`'s own bag-opening code).

Launch pattern (rebuild the image after any config/script change -- unlike FAST-LIO2/LIO-SAM,
this image has no compiled layer to keep, just a fast apt install, so a full rebuild is cheap;
`GLIM_CONFIG` still overrides the baked-in config for candidates without rebuilding):
```
docker build -f docker/glim/Dockerfile -t lio-benchmark/glim:dev .
docker run --rm -v $LIO_DATA_ROOT:/data/hilti22:ro -v $(pwd)/runs:/runs \
  [-e GLIM_CONFIG=/runs/_candidates/<x>.yaml] \
  lio-benchmark/glim:dev /run_glim.sh /data/hilti22/rosbag2/<seq> \
  /runs/<id>/raw_glim.tum 300 1.0
```
`lio-bench eval <seq> <tum> --frame imu --run-dir <run>` (GLIM publishes IMU-frame poses on
`/glim_ros/odom`). exp14's bag is short (~75s), so a full run plus eval takes well under two
minutes -- repeats are cheap here, unlike FAST-LIO2/LIO-SAM.

**Next action for whoever picks this up:** deprioritized this session in favour of merging
(user's own call) -- root-causing the held-out failure is still the biggest open question for
this method, bigger than further exp14 tuning, since a config that doesn't generalize isn't
usable regardless of how good its exp14 number looks. Start with the two hypotheses above
(`initialization_mode` forced to `LOOSE`; check whether `"ROBUST"` exists under a different
name/param on 1.2.2, or whether a newer PPA package version supports it). Separately, IMU noise
covariance still needs its unit convention verified against source before reusing FAST-LIO2's
measured std values; once known, a *repeated* sweep (top candidates run >=2-3x, not the
single-trial-per-point approach used above) would give a trustworthy phase-2 result. Not yet a
frozen, comparable baseline. The GPU backend cannot be progressed further on this machine at
all (see above) -- any next attempt needs different hardware first.

## Merge history -- both feature branches now on `main`, kept for the record

`feat/lio-sam-integration` and `feat/glim-integration` are both merged (clean fast-forwards, no
merge commits, confirmed with the user before each push). `main`/`origin/main` are at `2401ad4`.
Not in either branch, deliberately: LIO-SAM's GT-fed orientation node from its 9-axis
experiment (violates `docs/protocol.md` §3, kept in a session scratchpad so it cannot be used
by accident) and the `walking_dataset` validation artifacts (outside the manifest, no ground
truth) -- both described in `docs/journal.md`, neither reproducible from the repo alone.

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
2. **LIO-SAM: phase-1 tuning, re-sweep, fresh held-out** — merged, rotation failure fixed, but
   not comparable until retuned and re-evaluated. Highest-value single open item across all
   three methods (`imuRPYWeight` 0.0 vs 0.01, § LIO-SAM "Next action").
3. **GLIM: root-cause the held-out generalization failure** (CPU backend) whenever there's
   appetite for another GLIM-specific investigation; **GPU backend needs different hardware**
   (compute capability 6.0+) before it can be tuned/swept/held-out-evaluated at all.
4. Add DLIO, original FAST-LIO, RTAB-Map ICP+IMU through the same interface. Resolve LOAM's
   implementation ambiguity or drop it with a stated reason (`docs/methods.md` "Exclusions"
   section — currently empty).
5. Once ≥2 methods have frozen configs and trustworthy held-out results: first cross-method
   comparison, `results/`, `lio-bench report`. FAST-LIO2 alone has that today.

Ask only for information that materially blocks the next action. Do not claim benchmark
rankings before ≥2 methods have real, trustworthy runs — LIO-SAM and GLIM are both post-fix/
post-tune-split but not comparable; their old sweep/held-out numbers (LIO-SAM: bug-era; GLIM:
fails both held-out sequences) don't represent usable configs yet.

## Suggested skills

- **mattpocock-skills:diagnosing-bugs**: for the next hard failure. It structured this
  session's root-cause work, and the open FAST-LIO2 exp16 divergence is the same shape.
- **handoff**: update this document after substantive progress (a method merged, a protocol
  change, a milestone).
- **mattpocock-skills:code-review**: before merging any future method branch, to check it
  against `docs/protocol.md` rather than only for correctness.
- **domain-modeling**: if defining CONTEXT.md, terminology or architecture decision records.

Read `docs/methods.md`, `docs/protocol.md` and `docs/journal.md` before acting — they carry
the actual decisions and measured facts; this file is a pointer and a punch list, not the
source of truth.
