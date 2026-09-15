import json
import sys

import pytest

from lio_benchmark.tracking import (canonical_hash, flatten, init_run, read_run, update_run,
                                    write_metrics)


def test_config_hash_ignores_key_order_but_not_values():
    a = {"preprocess": {"voxel": 0.5, "min_range": 1.0}, "imu": {"rate": 400}}
    b = {"imu": {"rate": 400}, "preprocess": {"min_range": 1.0, "voxel": 0.5}}
    assert canonical_hash(a) == canonical_hash(b)
    b["preprocess"]["voxel"] = 0.4
    assert canonical_hash(a) != canonical_hash(b)


def test_flatten_keeps_scalars_only():
    flat = flatten({"ate": {"trans_m": {"rmse": 0.1, "n": 5}}, "points": [1, 2], "status": "ok"})
    assert flat == {"ate.trans_m.rmse": 0.1, "ate.trans_m.n": 5, "status": "ok"}


def test_offline_run_record_without_wandb(tmp_path):
    sys.modules.pop("wandb", None)
    run_dir = init_run(tmp_path, "fast_lio2", "exp14", "tune", {"voxel": 0.5},
                       hypothesis="baseline", change="none", playback_rate=0.5,
                       dataset_hashes={"rosbags/exp14_basement_2.bag": "abc"})
    for name in ("run.json", "env.json", "config.resolved.yaml"):
        assert (run_dir / name).exists()
    write_metrics(run_dir, {"status": "ok", "ate": {"trans_m": {"rmse": 0.05}}})
    assert "ate.trans_m.rmse,0.05" in (run_dir / "metrics.csv").read_text()
    run = update_run(run_dir, status="ok", interpretation="fine", decision="keep")
    assert read_run(run_dir)["decision"] == "keep" and run["config_hash"] == canonical_hash({"voxel": 0.5})
    env = json.loads((run_dir / "env.json").read_text())
    assert env["dataset_hashes"] and "git" in env and env["cpu_count"]
    assert "wandb" not in sys.modules


def test_rejects_unknown_decision(tmp_path):
    run_dir = init_run(tmp_path, "m", "exp14", "tune", {}, hypothesis="h", change="c")
    with pytest.raises(ValueError):
        update_run(run_dir, decision="maybe")
