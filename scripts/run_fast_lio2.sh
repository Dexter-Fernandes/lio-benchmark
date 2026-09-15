#!/usr/bin/env bash
# Runs FAST-LIO2 on one Hilti-Oxford ROS1 bag and exports the estimated IMU-frame trajectory
# to TUM, plus the saved map (PCD) when pcd_save.pcd_save_en is set in the loaded config.
# Meant to run inside docker/fast_lio2 (ENTRYPOINT). Launch, readiness, timeout and completion
# detection, as required by HANDOFF.md step 3. Default rate 1.0 (real-time playback).
set -euo pipefail

BAG=${1:?usage: run_fast_lio2.sh <bag> <out_tum> [timeout_s] [rate]}
OUT_TUM=${2:?usage: run_fast_lio2.sh <bag> <out_tum> [timeout_s] [rate]}
TIMEOUT_S=${3:-1800}
RATE=${4:-1.0}
PCD_PATH=/catkin_ws/src/FAST_LIO/PCD/scans.pcd

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
# No --clock / use_sim_time: FAST-LIO2's estimation and our adapters key off each message's
# own header.stamp (bag time), not ros::Time::now(), so wall-clock ROS time costs nothing --
# and sim time actively breaks shutdown: ros::Rate::sleep() blocks on /clock when
# use_sim_time is set, and rosbag play stops publishing /clock the moment playback ends, so
# FAST-LIO2's main loop (which only checks the SIGINT flag between rate.sleep() calls) would
# never wake up to see it and save the map.

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
timeout "$TIMEOUT_S" rosbag play -r "$RATE" "$BAG"
PLAY_STATUS=$?
set -e
if [ "$PLAY_STATUS" -eq 124 ]; then
  echo "rosbag play timed out after ${TIMEOUT_S}s" >&2
fi

sleep 5   # let the last messages flush through the adapter and estimator

# fastlio_mapping only writes its PCD map on SIGINT (its registered signal handler; a plain
# kill/SIGTERM skips straight past the save-on-exit code path), so send that first and wait
# for the file before tearing the rest down.
kill -INT "$MAPPING_PID" 2>/dev/null || true
for _ in $(seq 1 30); do
  [ -f "$PCD_PATH" ] && break
  kill -0 "$MAPPING_PID" 2>/dev/null || break
  sleep 1
done

kill "$ADAPTER_PID" "$EXPORT_PID" "$MAPPING_PID" 2>/dev/null || true
wait "$EXPORT_PID" 2>/dev/null || true

test -s "$OUT_TUM" || { echo "no trajectory written to $OUT_TUM" >&2; exit 1; }
echo "wrote $(wc -l < "$OUT_TUM") poses to $OUT_TUM"

if [ -f "$PCD_PATH" ]; then
  cp "$PCD_PATH" "$(dirname "$OUT_TUM")/map.pcd"
  echo "wrote $(dirname "$OUT_TUM")/map.pcd ($(du -h "$PCD_PATH" | cut -f1))"
else
  echo "no map.pcd (pcd_save.pcd_save_en not set, or the mapping node didn't exit cleanly)" >&2
fi
