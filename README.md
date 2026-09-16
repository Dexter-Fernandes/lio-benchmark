# lio-benchmark

Reproducible LiDAR-inertial odometry benchmarking on Hilti-Oxford 2022, with containerised
pipelines, W&B experiment tracking, and held-out trajectory evaluation.

> **Status:** three methods integrated.
>
> **FAST-LIO2** is tuned (measured IMU noise covariance + a measured registration voxel size;
> a 15-trial Bayesian sweep found nothing better) and evaluated held-out on exp16/exp18.
> exp18 shows a normal generalization gap; exp16 diverges reproducibly partway through and is
> an open failure-analysis case (`docs/journal.md`).
>
> **LIO-SAM** runs end-to-end and a systematic rotation failure in it has been root-caused and
> fixed: upstream hardcodes a scan-matching degeneracy cutoff calibrated for outdoor lidar
> ranges, which discarded 91% of the tilt and height corrections in this close-range basement
> (`docs/methods.md`). exp14 went from 29.3 m / 129° to 1.07 m / 18.8°. It is **not yet
> comparable**: it still owes the manual tuning phase it skipped, a re-run sweep and a fresh
> held-out evaluation, and its earlier sweep and held-out numbers describe the bug rather than
> the method.
>
> **GLIM** (CPU backend) is tuned on exp14 (measured registration voxel size, competitive with
> FAST-LIO2: 0.09–0.11 m / 1.4–2.2°) but **fails to generalize to both held-out sequences**
> (exp16: 4.61 m / 106.8°; exp18: 3.24 m / 43.4°), unlike FAST-LIO2, which only diverges on
> exp16 — an open root-cause question, not yet comparable. A GPU backend was also built and is
> feature-complete, but is hardware-blocked on the reference machine: its only GPU (compute
> capability 5.0) is one generation below what `gtsam_points`' GPU code requires, confirmed at
> the source level (`docs/methods.md` "GLIM GPU backend").
>
> No cross-method comparison is published yet — that needs two methods with trustworthy
> held-out results.

## Scope

- **Dataset:** Hilti-Oxford 2022. Tune on **exp14**; hold out **exp16** and **exp18**. These
  are the three sequences with dense 6-DoF reference trajectories.
- **Methods:** FAST-LIO2, LIO-SAM and GLIM (CPU and GPU backends) are integrated; original
  FAST-LIO, DLIO, RTAB-Map ICP+IMU and LOAM (depending on the implementation) are planned. See
  [docs/methods.md](docs/methods.md) for the variant distinctions and dataset-specific
  integration issues.
- **Comparison:** online odometry with loop closure, GPS and prior maps disabled; ATE/RPE
  with SE(3) alignment and no scale; coverage, reliability and compute. See
  [docs/protocol.md](docs/protocol.md).
- **Tuning:** manually guided and hypothesis-driven, recorded run by run, with
  configurations frozen before held-out evaluation. See [docs/journal.md](docs/journal.md).

## Quick start

Requirements: Docker, [uv](https://docs.astral.sh/uv/), curl, and about 45 GB free for the
three sequences, their MCAP conversions and the IMU noise recording.

```bash
cp .env.example .env               # set LIO_DATA_ROOT to a directory on a large partition
uv sync                            # host environment (Python 3.11)
uv run pytest                      # 72 tests, no dataset needed

uv run lio-bench data status       # what is present / partial / verified / missing
uv run lio-bench data download     # default groups: ground truth, calibration, IMU noise, 3 bags
uv run lio-bench data verify       # sizes + hashes against manifests/hilti22.yaml
uv run lio-bench data convert exp14    # ROS 1 -> MCAP (LiDAR + IMU) with equivalence check
uv run lio-bench inspect exp14     # measured topics, point layout, timing, IMU, GT coverage
uv run lio-bench gt check          # validate dense and sparse ground truth
uv run lio-bench eval exp14 my_traj.tum --frame imu    # or --frame lidar
```

The same commands run in the tools container, which mounts the data read-only except for
data-writing commands:

```bash
docker build -f docker/tools/Dockerfile -t lio-benchmark/tools:dev .
scripts/in-tools.sh pytest -q
scripts/in-tools.sh lio-bench data status
```

For VS Code, open the folder in the `.devcontainer/tools` configuration, with `LIO_DATA_ROOT`
exported in the launching shell.

Downloads are pinned to one Hugging Face revision, resumable (`.part` files), checked for
disk space first, and verified against the manifest hashes before they are moved into
place. Verified files are recorded under `<data root>/_provenance/`, together with the
conversion and inspection reports.

## Experiment tracking

Each run is a directory under `runs/` (configurable with `LIO_RUNS_ROOT`) holding:
- the resolved configuration and its hash;
- the environment and dataset hashes;
- the hypothesis, change, metrics, trajectory and plots;
- for methods that save a map (FAST-LIO2: `pcd_save.pcd_save_en`; LIO-SAM: `savePCD`), the map
  itself (`map.pcd`) and a rendered top-down view (`map.png`, `lio-bench eval` calls
  `plots.plot_pcd_map`);
- the decision.

`lio-bench log <run_dir>` mirrors a run to Weights & Biases; `WANDB_MODE` defaults to
`online`, so every run lands on the dashboard. Run `scripts/wandb_setup.sh` once to install,
log in and configure `.env` (or set `WANDB_MODE=offline` there yourself to develop without
credentials and sync later with `wandb sync`). The W&B entity and project are set in `.env`.
`lio-bench report` builds/updates a saved W&B Report comparing ATE/RPE across every run in
the project.

## Running experiments

Every experiment follows the same shape (`docs/protocol.md` §6, entry template in
`docs/journal.md`), whichever method you're running:

```bash
run=$(uv run lio-bench run init --method <method> --sequence exp14 --config <resolved.yaml> \
        --hypothesis "..." --change "..." --parent <run_id or omit for a baseline> \
        --playback-rate <rate>)
# ... run the method (per-method command below), producing a TUM trajectory ...
uv run lio-bench eval exp14 <trajectory.tum> --frame <imu|lidar> --run-dir "$run"
uv run lio-bench run close "$run" --interpretation "..." --decision keep|revert|investigate
uv run lio-bench log "$run"
```

Each subsection below is just the method-specific piece that plugs into the "run the method"
step: the image, the exact `docker run` invocation, the eval frame, and the script that
generates a tuning candidate's config override. Status lines say whether a method's numbers
are trustworthy yet — check `docs/journal.md` and `docs/methods.md` for the full history
behind any of them.

### FAST-LIO2

*Reference integration: tuned and held-out evaluated (`docs/journal.md`).* Input is the raw
ROS 1 `.bag`, not the rosbag2 conversion.

```bash
docker build -f docker/fast_lio2/Dockerfile -t lio-benchmark/fast_lio2:dev .
docker run --rm -v $LIO_DATA_ROOT:/data/hilti22:ro -v $(pwd)/runs:/runs \
  [-e FAST_LIO2_CONFIG=/runs/_candidates/<x>.yaml] \
  lio-benchmark/fast_lio2:dev /run_fast_lio2.sh /data/hilti22/rosbags/<seq>.bag \
  /runs/<id>/raw.tum 600 1.0
```

`--frame imu`. Generate a tuning candidate with `scripts/fast_lio2_candidate.py --set
mapping.acc_cov=1.23e-4 --out /tmp/candidate.yaml` (repeatable `--set section.field=value`);
`scripts/fast_lio2_sweep.py` runs a phase-2 Bayesian sweep over a bounded region.

### LIO-SAM

*Merged, correctness bug fixed, still owes phase-1 tuning — not yet comparable
(`HANDOFF.md` § LIO-SAM).* Input is the raw ROS 1 `.bag`. The image bakes in its config and
run wrapper, so a candidate run bind-mounts both over them:

```bash
docker build -f docker/lio_sam/Dockerfile -t lio-benchmark/lio_sam:dev .
docker run --rm -v $LIO_DATA_ROOT:/data/hilti22:ro -v $(pwd)/runs:/runs \
  -v $(pwd)/configs:/configs:ro -v $(pwd)/scripts/run_lio_sam.sh:/run_lio_sam.sh:ro \
  [-e LIO_SAM_CONFIG=/runs/_candidates/<x>.yaml] [-e LIO_SAM_RECORD=/runs/<id>/diag.bag] \
  lio-benchmark/lio_sam:dev /run_lio_sam.sh /data/hilti22/rosbags/<seq>.bag \
  /runs/<id>/raw_lio_sam.tum 600 1.0
```

`--frame lidar` (LIO-SAM publishes lidar-frame poses, unlike the other three).
`scripts/lio_sam_candidate.py` / `scripts/lio_sam_sweep.py` mirror FAST-LIO2's. `LIO_SAM_RECORD`
records method internals to a bag for `scripts/lio_sam_diag.py` to inspect (used for the
degeneracy root-cause, not needed for an ordinary run).

### GLIM — CPU backend

*Tuned on exp14, fails to generalize to held-out exp16/exp18 — not yet comparable
(`docs/methods.md` "GLIM integration").* Input is the **rosbag2/MCAP** conversion, not the raw
bag (`uv run lio-bench data convert <seq> --dst-version 5` first, if not already converted —
ROS 2 Humble can't read the default metadata version).

```bash
docker build -f docker/glim/Dockerfile -t lio-benchmark/glim:dev .
docker run --rm -v $LIO_DATA_ROOT:/data/hilti22:ro -v $(pwd)/runs:/runs \
  [-e GLIM_CONFIG=/runs/_candidates/<x>.yaml] \
  lio-benchmark/glim:dev /run_glim.sh /data/hilti22/rosbag2/<seq> \
  /runs/<id>/raw_glim.tum 300 1.0
```

`--frame imu`. `scripts/glim_candidate.py` / `scripts/glim_sweep.py` mirror FAST-LIO2's, with
section names like `odometry_cpu.ivox_resolution`. exp14's bag is short (~75 s), so repeats are
cheap here.

### GLIM — GPU backend

*Feature-complete but **hardware-blocked on the reference machine** — needs a GPU of compute
capability 6.0 or newer (Pascal+); confirmed unrunnable on a compute-capability-5.0 card
(`docs/methods.md` "GLIM GPU backend"). Don't rebuild this expecting it to work on the same
hardware — it won't; the failure is architectural (`gtsam_points`' `cudaMallocAsync` requires
6.0+), not a config or driver issue.* Same rosbag2/MCAP input and run wrapper as the CPU
backend, plus `--gpus all`:

```bash
docker build -f docker/glim_gpu/Dockerfile -t lio-benchmark/glim-gpu:dev .
docker run --rm --gpus all -v $LIO_DATA_ROOT:/data/hilti22:ro -v $(pwd)/runs:/runs \
  -e GLIM_CONFIG=/configs/glim/hilti22_gpu.yaml \
  lio-benchmark/glim-gpu:dev /run_glim.sh /data/hilti22/rosbag2/<seq> \
  /runs/<id>/raw_glim_gpu.tum 300 1.0
```

`--frame imu`. `scripts/glim_candidate.py --base configs/glim/hilti22_gpu.yaml` generates GPU
candidates (section names like `odometry_gpu.voxel_resolution`); no separate GPU sweep script
exists yet since no successful run has been produced on this hardware to bound one.

## Layout

| Path | Purpose |
|---|---|
| `manifests/hilti22.yaml` | pinned revision, files, sizes, hashes, split, licence and citation |
| `configs/dataset/` | topics and the LiDAR-IMU extrinsic shared by all methods |
| `configs/eval/` | frozen evaluation parameters |
| `src/lio_benchmark/` | download, convert, inspect, frames, evaluation, tracking, CLI |
| `tests/` | hashing, downloads (local HTTP server), manifest, frames, trajectories, evaluator, conversion, run records |
| `docker/`, `.devcontainer/` | tools, fast_lio2, lio_sam, glim and glim_gpu images; one per method/backend as they are integrated |
| `adapters/` | input/output conversion between the dataset and a method (`adapters/fast_lio2/`, `adapters/lio_sam/`, `adapters/glim/`) |
| `docs/` | protocol, dataset, methods, journal |
| `results/` | curated, publishable tables and plots (none yet) |

## Dataset licence and citation

Hilti-Oxford 2022 is released under
[CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/): non-commercial use,
attribution required, adaptations under the same licence. No dataset files or derived data
are committed here. Please cite:

> L. Zhang, M. Helmberger, L. F. T. Fu, D. Wisth, M. Camurri, D. Scaramuzza and M. Fallon,
> "Hilti-Oxford Dataset: A Millimeter-Accurate Benchmark for Simultaneous Localization and
> Mapping," *IEEE Robotics and Automation Letters*, 8(1):408–415, 2023.
> doi:10.1109/LRA.2022.3226077

The code in this repository is MIT-licensed ([LICENSE](LICENSE)).

## Limitations

- Three sequences from one sensor rig in one building. The held-out split tests within-dataset
  generalisation only.
- The accuracy of the dense 6-DoF references is not documented at the level of the surveyed
  sparse control points. Both are reported (see [docs/dataset.md](docs/dataset.md)).
- The target hardware is a 2-core laptop, so slow-replay accuracy runs and real-time runs
  are reported separately.
