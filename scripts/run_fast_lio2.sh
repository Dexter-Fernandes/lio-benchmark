#!/usr/bin/env bash
# Runs FAST-LIO2 on one Hilti-Oxford ROS1 bag and exports the estimated IMU-frame trajectory
# to TUM. Meant to run inside docker/fast_lio2 (ENTRYPOINT). Launch, readiness, timeout and
# completion detection, as required by HANDOFF.md step 3.
set -euo pipefail

BAG=${1:?usage: run_fast_lio2.sh <bag> <out_tum> [timeout_s] [rate]}
OUT_TUM=${2:?usage: run_fast_lio2.sh <bag> <out_tum> [timeout_s] [rate]}
TIMEOUT_S=${3:-1800}
RATE=${4:-0.5}

source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash

mkdir -p "$(dirname "$OUT_TUM")"

roscore &
ROSCORE_PID=$!
trap 'kill $ROSCORE_PID ${ADAPTER_PID:-} ${EXPORT_PID:-} ${MAPPING_PID:-} 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do rostopic list >/dev/null 2>&1 && break; sleep 1; done
rostopic list >/dev/null 2>&1 || { echo "roscore did not come up" >&2; exit 1; }

rosparam load "${FAST_LIO2_CONFIG:-/configs/fast_lio2/hilti22.yaml}"
# mapping_velodyne.launch's top-level params: FAST-LIO2 reads these via nh.param("name", ...),
# not nested under mapping/, so the yaml's `launch:` section (loaded to /launch/* above) is
# copied to the top level the node actually reads. Single source of truth: FAST_LIO2_CONFIG.
for name in feature_extract_enable point_filter_num max_iteration filter_size_surf \
            filter_size_map cube_side_length runtime_pos_log_enable; do
  rosparam set "$name" "$(rosparam get "/launch/$name")"
done
rosparam set /use_sim_time true

python3 /adapters/fast_lio2/ros_node.py _in_topic:=/hesai/pandar _out_topic:=/hesai/pandar/fast_lio2 &
ADAPTER_PID=$!
python3 /adapters/fast_lio2/odom_to_tum.py _out_path:="$OUT_TUM" _topic:=/Odometry &
EXPORT_PID=$!
rosrun fast_lio fastlio_mapping &
MAPPING_PID=$!

echo "waiting for laserMapping to subscribe to the adapted cloud..."
for _ in $(seq 1 60); do
  rostopic info /hesai/pandar/fast_lio2 2>/dev/null | grep -q laserMapping && break
  sleep 1
done

echo "playing $BAG at rate $RATE (timeout ${TIMEOUT_S}s)"
set +e
timeout "$TIMEOUT_S" rosbag play --clock -r "$RATE" "$BAG"
PLAY_STATUS=$?
set -e
if [ "$PLAY_STATUS" -eq 124 ]; then
  echo "rosbag play timed out after ${TIMEOUT_S}s" >&2
fi

sleep 5   # let the last messages flush through the adapter and estimator
kill "$ADAPTER_PID" "$EXPORT_PID" "$MAPPING_PID" 2>/dev/null || true
wait "$EXPORT_PID" 2>/dev/null || true

test -s "$OUT_TUM" || { echo "no trajectory written to $OUT_TUM" >&2; exit 1; }
echo "wrote $(wc -l < "$OUT_TUM") poses to $OUT_TUM"
