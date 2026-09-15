# lio-benchmark

Reproducible LiDAR-inertial odometry benchmarking on Hilti-Oxford 2022, with containerised
pipelines, W&B experiment tracking, and held-out trajectory evaluation.

> **Status:** first milestone reached. The data pipeline, bag inspection, gap-aware
> evaluator, run records and protocol are in place and tested, and FAST-LIO2 has one
> verified end-to-end baseline run on exp14 (untuned, `docs/journal.md`). No other method
> is integrated, and exp16/exp18 are still held out.

## Scope

- **Dataset:** Hilti-Oxford 2022. Tune on **exp14**; hold out **exp16** and **exp18**. These
  are the three sequences with dense 6-DoF reference trajectories.
- **Methods (planned):** FAST-LIO2, original FAST-LIO, LIO-SAM, GLIM (CPU), DLIO, RTAB-Map
  ICP+IMU, and LOAM depending on the implementation. See [docs/methods.md](docs/methods.md)
  for the variant distinctions and dataset-specific integration issues.
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
uv run pytest                      # 60 tests, no dataset needed

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
- the decision.

`lio-bench log <run_dir>` mirrors a run to Weights & Biases. `WANDB_MODE` defaults to
`offline`, so no credentials are needed; sync later with `wandb sync`. The W&B entity and
project are set in `.env`.

## Layout

| Path | Purpose |
|---|---|
| `manifests/hilti22.yaml` | pinned revision, files, sizes, hashes, split, licence and citation |
| `configs/dataset/` | topics and the LiDAR-IMU extrinsic shared by all methods |
| `configs/eval/` | frozen evaluation parameters |
| `src/lio_benchmark/` | download, convert, inspect, frames, evaluation, tracking, CLI |
| `tests/` | hashing, downloads (local HTTP server), manifest, frames, trajectories, evaluator, conversion, run records |
| `docker/`, `.devcontainer/` | tools image, fast_lio2 image; one per method as they are integrated |
| `adapters/` | input/output conversion between the dataset and a method (e.g. `adapters/fast_lio2/`) |
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
