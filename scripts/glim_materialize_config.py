#!/usr/bin/env python3
"""Materializes configs/glim/hilti22.yaml's sections into GLIM's native config/*.json
directory, on top of upstream's own defaults (for files this repo doesn't override, e.g.
config_logging.json/config_viewer.json).

GLIM resolves each named config through config.json's "global" section (see
glim/src/glim_ros/glim_ros.cpp: `GlobalConfig::get_config_path("config_odometry")`, etc.),
which is why config.json exists at all -- it's the switch between, e.g., the GPU and CPU
odometry-estimation variants. `-p config_path:=<out dir>` (an absolute path) tells GLIM to use
this materialized directory instead of its installed default.

Usage: glim_materialize_config.py --base configs/glim/hilti22.yaml \
    --defaults /ws/src/glim/config --out /tmp/glim_config
"""
import argparse
import json
import shutil
from pathlib import Path

import yaml

BASE_CONFIG = Path(__file__).resolve().parent.parent / "configs/glim/hilti22.yaml"

# YAML section -> (output filename, JSON root key), matching GLIM's own config/*.json schema.
# Shared between backends; the odometry/sub_mapping/global_mapping sections differ per backend
# (SECTIONS_BY_BACKEND below) since GPU's schema is structurally different, not just a value
# swap (configs/glim/hilti22_gpu.yaml's header).
COMMON_SECTIONS = {
    "sensors": ("config_sensors.json", "sensors"),
    "preprocess": ("config_preprocess.json", "preprocess"),
    "ros": ("config_ros.json", "glim_ros"),
}
SECTIONS_BY_BACKEND = {
    "cpu": {
        "odometry_cpu": ("config_odometry_cpu.json", "odometry_estimation"),
        "sub_mapping_cpu": ("config_sub_mapping_cpu.json", "sub_mapping"),
        "global_mapping_cpu": ("config_global_mapping_cpu.json", "global_mapping"),
    },
    "gpu": {
        "odometry_gpu": ("config_odometry_gpu.json", "odometry_estimation"),
        "sub_mapping_gpu": ("config_sub_mapping_gpu.json", "sub_mapping"),
        "global_mapping_gpu": ("config_global_mapping_gpu.json", "global_mapping"),
    },
}


def materialize(config: dict, defaults_dir: Path, out_dir: Path) -> Path:
    backend = "gpu" if "odometry_gpu" in config else "cpu"
    sections = {**COMMON_SECTIONS, **SECTIONS_BY_BACKEND[backend]}

    out_dir.mkdir(parents=True, exist_ok=True)
    for src in defaults_dir.glob("*.json"):
        shutil.copy(src, out_dir / src.name)

    for section, (filename, root_key) in sections.items():
        (out_dir / filename).write_text(json.dumps({root_key: config[section]}, indent=2))

    odometry_file, sub_mapping_file, global_mapping_file = (
        f"config_odometry_{backend}.json",
        f"config_sub_mapping_{backend}.json",
        f"config_global_mapping_{backend}.json",
    )
    global_cfg = {
        "global": {
            "config_path": "",
            "config_ros": "config_ros.json",
            "config_logging": "config_logging.json",
            "config_viewer": "config_viewer.json",
            "config_sensors": "config_sensors.json",
            "config_preprocess": "config_preprocess.json",
            "config_odometry": odometry_file,
            "config_sub_mapping": sub_mapping_file,
            "config_global_mapping": global_mapping_file,
        }
    }
    (out_dir / "config.json").write_text(json.dumps(global_cfg, indent=2))
    return out_dir


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=BASE_CONFIG, type=Path)
    ap.add_argument("--defaults", required=True, type=Path,
                     help="upstream glim/config directory, for files we don't override")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--rate", type=float, default=None,
                     help="overrides ros.playback_speed (glim_rosbag's own real-time factor, "
                          "read from config_ros.json -- not a ROS param)")
    args = ap.parse_args()

    config = yaml.safe_load(args.base.read_text())
    if args.rate is not None:
        config["ros"]["playback_speed"] = args.rate
    out = materialize(config, args.defaults, args.out)
    print(out)


if __name__ == "__main__":
    main()
