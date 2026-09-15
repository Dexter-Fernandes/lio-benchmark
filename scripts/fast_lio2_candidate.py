#!/usr/bin/env python
"""Write a FAST-LIO2 candidate config: configs/fast_lio2/hilti22.yaml with dotted-key
overrides applied, for one manually reasoned tuning attempt (docs/protocol.md #6).

Usage: fast_lio2_candidate.py --set mapping.acc_cov=1.23e-4 --set mapping.gyr_cov=4.5e-5 \
    --out /tmp/candidate.yaml
"""
import argparse
from pathlib import Path

import yaml

BASE_CONFIG = Path(__file__).resolve().parent.parent / "configs/fast_lio2/hilti22.yaml"


def apply_overrides(config: dict, overrides: list[str]) -> dict:
    for item in overrides:
        key, _, value = item.partition("=")
        section, _, field = key.partition(".")
        config[section][field] = yaml.safe_load(value)
    return config


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default=BASE_CONFIG, type=Path)
    ap.add_argument("--set", dest="overrides", action="append", default=[],
                    metavar="section.field=value", help="repeatable, e.g. mapping.acc_cov=1e-4")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    config = apply_overrides(yaml.safe_load(args.base.read_text()), args.overrides)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(config, sort_keys=False))
    print(args.out)


if __name__ == "__main__":
    main()
