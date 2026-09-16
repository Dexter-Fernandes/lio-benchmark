#!/usr/bin/env bash
# Runs GLIM on one Hilti-Oxford rosbag2 (MCAP) directory and exports the estimated online
# IMU-frame odometry to TUM. Meant to run inside docker/glim.
#
# Unlike run_fast_lio2.sh/run_lio_sam.sh, this needs no roscore, no separate bag player, no
# readiness poll and no sim-time hazard: GLIM's own `glim_rosbag` binary reads the rosbag2
# directory directly, throttled by its own `playback_speed` config value (config_ros.json,
# NOT a ROS param -- read directly in glim_rosbag.cpp before rclpy::spin), and everything is
# driven off in-process message timestamps, never a live /clock topic (verified against
# source, docs/methods.md "GLIM integration").
#
# The odometry topic is published by rviz_viewer's extension module
# (glim_ros2/src/glim_ros/rviz_viewer.cpp) as "<node>/odom", a private topic under the node's
# name -- confirmed by a real run to resolve to /glim_ros/odom, but discovered here via
# `ros2 topic list` rather than hardcoded, in case a future GLIM version changes the node name.
#
# glim_rosbag is passed the .mcap file directly, not the containing directory, even though its
# own source (glim_rosbag.cpp) accepts either. Passing the directory hits a real bug in the
# glim_ros2:humble_cuda12.2 image's glim_rosbag build: its is_directory() branch is meant to
# read metadata.yaml and set storage_id from storage_identifier, but in practice it ends up
# opening the bag with storage_id "sqlite3" anyway ("file is not a database") -- reproduced
# directly, not assumed. The file-path branch (bag_filename ends in ".mcap") hardcodes
# storage_id="mcap" and sidesteps this entirely; confirmed working on both backends.
set -eo pipefail

ROSBAG2_DIR=${1:?usage: run_glim.sh <rosbag2 dir> <out_tum> [timeout_s] [rate]}
OUT_TUM=${2:?usage: run_glim.sh <rosbag2 dir> <out_tum> [timeout_s] [rate]}
TIMEOUT_S=${3:-1800}
RATE=${4:-1.0}
CONFIG_DIR=$(mktemp -d)
DUMP_DIR="$(dirname "$OUT_TUM")/glim_dump"

# No `set -u`: ROS 2 Humble's own setup.bash references unset variables
# (e.g. AMENT_TRACE_SETUP_FILES) internally -- confirmed by hitting this directly, not
# something FAST-LIO2/LIO-SAM's Noetic setup.bash triggers.
source /opt/ros/humble/setup.bash

mkdir -p "$(dirname "$OUT_TUM")"

# Upstream's own default config/ (config_logging.json, config_viewer.json, etc. -- the files
# this repo doesn't override) ships in the glim core package's ament share directory.
GLIM_DEFAULTS="$(ros2 pkg prefix glim)/share/glim/config"

python3 /scripts/glim_materialize_config.py \
    --base "${GLIM_CONFIG:-/configs/glim/hilti22.yaml}" \
    --defaults "$GLIM_DEFAULTS" --out "$CONFIG_DIR" --rate "$RATE"

ROSBAG2_FILE=$(ls "$ROSBAG2_DIR"/*.mcap)

trap 'kill ${GLIM_PID:-} ${EXPORT_PID:-} 2>/dev/null || true' EXIT

timeout "$TIMEOUT_S" ros2 run glim_ros glim_rosbag "$ROSBAG2_FILE" --ros-args \
    -p config_path:="$CONFIG_DIR" -p auto_quit:=true -p dump_path:="$DUMP_DIR" &
GLIM_PID=$!

echo "waiting for GLIM's odometry topic to appear..."
ODOM_TOPIC=""
for _ in $(seq 1 60); do
  ODOM_TOPIC=$(ros2 topic list 2>/dev/null | grep -E '/odom$' | head -1 || true)
  [ -n "$ODOM_TOPIC" ] && break
  kill -0 "$GLIM_PID" 2>/dev/null || break   # died before advertising anything
  sleep 1
done
[ -n "$ODOM_TOPIC" ] || { echo "GLIM never advertised an odometry topic" >&2; exit 1; }
echo "exporting $ODOM_TOPIC"

python3 /adapters/glim/odom_to_tum.py --topic "$ODOM_TOPIC" --out "$OUT_TUM" &
EXPORT_PID=$!

set +e
wait "$GLIM_PID"
GLIM_STATUS=$?
set -e
if [ "$GLIM_STATUS" -eq 124 ]; then
  echo "glim_rosbag timed out after ${TIMEOUT_S}s" >&2
fi

sleep 2   # let the last messages flush through the exporter
kill "$EXPORT_PID" 2>/dev/null || true
wait "$EXPORT_PID" 2>/dev/null || true

test -s "$OUT_TUM" || { echo "no trajectory written to $OUT_TUM" >&2; exit 1; }
echo "wrote $(wc -l < "$OUT_TUM") poses to $OUT_TUM"
[ -d "$DUMP_DIR" ] && echo "wrote GLIM dump to $DUMP_DIR (secondary artifact, docs/protocol.md #1)"
