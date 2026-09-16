# lio-benchmark

Reproducible LiDAR-inertial odometry benchmarking on Hilti-Oxford 2022, with containerised
pipelines, W&B experiment tracking, and held-out trajectory evaluation.

> **Status:** two methods integrated.
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
> No cross-method comparison is published yet — that needs two methods with trustworthy
> held-out results.

## Scope

- **Dataset:** Hilti-Oxford 2022. Tune on **exp14**; hold out **exp16** and **exp18**. These
  are the three sequences with dense 6-DoF reference trajectories.
- **Methods:** FAST-LIO2 and LIO-SAM are integrated; original FAST-LIO, GLIM (CPU), DLIO,
  RTAB-Map ICP+IMU and LOAM (depending on the implementation) are planned. See
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
uv run pytest                      # 71 tests, no dataset needed

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

## Layout

| Path | Purpose |
|---|---|
| `manifests/hilti22.yaml` | pinned revision, files, sizes, hashes, split, licence and citation |
| `configs/dataset/` | topics and the LiDAR-IMU extrinsic shared by all methods |
| `configs/eval/` | frozen evaluation parameters |
| `src/lio_benchmark/` | download, convert, inspect, frames, evaluation, tracking, CLI |
| `tests/` | hashing, downloads (local HTTP server), manifest, frames, trajectories, evaluator, conversion, run records |
| `docker/`, `.devcontainer/` | tools, fast_lio2 and lio_sam images; one per method as they are integrated |
| `adapters/` | input/output conversion between the dataset and a method (`adapters/fast_lio2/`, `adapters/lio_sam/`) |
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
