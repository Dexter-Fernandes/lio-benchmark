#!/usr/bin/env python
"""Write a GLIM candidate config: configs/glim/hilti22.yaml with dotted-key overrides
applied, for one manually reasoned tuning attempt (docs/protocol.md #6).

Usage: glim_candidate.py --set odometry_cpu.ivox_resolution=0.2 --out /tmp/candidate.yaml
"""
import argparse
from pathlib import Path

import yaml

from fast_lio2_candidate import apply_overrides

BASE_CONFIG = Path(__file__).resolve().parent.parent / "configs/glim/hilti22.yaml"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=BASE_CONFIG, type=Path)
    ap.add_argument("--set", dest="overrides", action="append", default=[],
                    metavar="section.field=value", help="repeatable, e.g. odometry_cpu.ivox_resolution=0.2")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    config = apply_overrides(yaml.safe_load(args.base.read_text()), args.overrides)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(config, sort_keys=False))
    print(args.out)


if __name__ == "__main__":
    main()
