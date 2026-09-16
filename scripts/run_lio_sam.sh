#!/usr/bin/env bash
# Runs LIO-SAM on one Hilti-Oxford ROS1 bag and exports the estimated LiDAR-frame trajectory
# to TUM, plus the saved map (GlobalMap.pcd) when mapOptmization's savePCD config is set.
# Meant to run inside docker/lio_sam. Launch, readiness, timeout and completion detection,
# mirroring run_fast_lio2.sh's shape with LIO-SAM's own verified gotchas. Default rate 1.0
# (real-time playback).
set -euo pipefail

BAG=${1:?usage: run_lio_sam.sh <bag> <out_tum> [timeout_s] [rate]}
OUT_TUM=${2:?usage: run_lio_sam.sh <bag> <out_tum> [timeout_s] [rate]}
TIMEOUT_S=${3:-1800}
RATE=${4:-1.0}
# mapOptmization::saveMapService resolves an empty req.destination to $HOME + savePCDDirectory
# (src/mapOptmization.cpp) -- NOT the literal savePCDDirectory path -- and deletes/recreates
# that directory on every save, so treat it as ephemeral scratch, never anything else.
PCD_SAVE_DIR="${HOME}/pcd_out"
GLOBAL_MAP_PATH="$PCD_SAVE_DIR/GlobalMap.pcd"

source /opt/ros/noetic/setup.bash
source /catkin_ws/devel/setup.bash

mkdir -p "$(dirname "$OUT_TUM")"
rm -rf "$PCD_SAVE_DIR"

roscore &
ROSCORE_PID=$!
trap 'kill $ROSCORE_PID ${ORIENT_PID:-} ${ADAPTER_PID:-} ${EXPORT_PID:-} ${IMG_PID:-} ${FEAT_PID:-} ${IMU_PID:-} ${MAP_PID:-} ${REC_PID:-} 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do rostopic list >/dev/null 2>&1 && break; sleep 1; done
rostopic list >/dev/null 2>&1 || { echo "roscore did not come up" >&2; exit 1; }

rosparam load "${LIO_SAM_CONFIG:-/configs/lio_sam/hilti22.yaml}"
# No --clock / use_sim_time: same reasoning as run_fast_lio2.sh. LIO-SAM's mapOptmization
# saves its map from visualizeGlobalMapThread()'s `while (ros::ok()) rate.sleep();` loop
# (src/mapOptmization.cpp) -- once that loop exits (on SIGINT) it falls through to
# saveMapService(). Sim time would stop advancing the instant bag playback ends and this loop
# would never see ros::ok() go false in a timely way; every node here keys off header.stamp,
# never ros::Time::now(), so wall-clock time costs nothing.

python3 /adapters/lio_sam/imu_orientation_node.py _in_topic:=/alphasense/imu _out_topic:=/alphasense/imu/oriented &
ORIENT_PID=$!
python3 /adapters/lio_sam/ros_node.py _in_topic:=/hesai/pandar _out_topic:=/hesai/pandar/lio_sam &
ADAPTER_PID=$!
python3 /adapters/lio_sam/odom_to_tum.py _out_path:="$OUT_TUM" _topic:=/lio_sam/mapping/odometry &
EXPORT_PID=$!

# imageProjection, featureExtraction and mapOptmization all call ros::init(argc, argv,
# "lio_sam") in source (same literal name; imuPreintegration uses "roboat_loam") -- upstream's
# own launch/run.launch relies on roslaunch's automatic per-<node> name remapping to make this
# work. Plain `rosrun` has no such remapping, so without an explicit __name:= each new process
# evicts the previous one from the ROS master ("new node registered with same name",
# confirmed by hitting this directly) -- give each an explicit, distinct name.
rosrun lio_sam lio_sam_imageProjection __name:=lio_sam_imageProjection &
IMG_PID=$!
rosrun lio_sam lio_sam_featureExtraction __name:=lio_sam_featureExtraction &
FEAT_PID=$!
rosrun lio_sam lio_sam_imuPreintegration __name:=lio_sam_imuPreintegration &
IMU_PID=$!
rosrun lio_sam lio_sam_mapOptmization __name:=lio_sam_mapOptmization &
MAP_PID=$!

echo "waiting for lio_sam_imageProjection to subscribe to the adapted cloud..."
for _ in $(seq 1 60); do
  rostopic info /hesai/pandar/lio_sam 2>/dev/null | grep -q lio_sam_imageProjection && break
  sleep 1
done

# Diagnostic recording (scripts/lio_sam_diag.py reads it): the per-scan degeneracy flag
# (odometry_incremental covariance[0]), feature clouds (counts), the preintegration guess and
# the IMU stream LIO-SAM actually received. Off unless LIO_SAM_RECORD names an output bag.
if [ -n "${LIO_SAM_RECORD:-}" ]; then
  rosbag record -O "$LIO_SAM_RECORD" /lio_sam/mapping/odometry_incremental /odometry/imu_incremental \
    /lio_sam/feature/cloud_corner /lio_sam/feature/cloud_surface /alphasense/imu/oriented &
  REC_PID=$!
fi

echo "playing $BAG at rate $RATE (timeout ${TIMEOUT_S}s)"
set +e
timeout "$TIMEOUT_S" rosbag play -r "$RATE" "$BAG"
PLAY_STATUS=$?
set -e
if [ "$PLAY_STATUS" -eq 124 ]; then
  echo "rosbag play timed out after ${TIMEOUT_S}s" >&2
fi

sleep 5   # let the last messages flush through the adapters and estimator

# mapOptmization only saves GlobalMap.pcd once its visualizeGlobalMapThread's `while
# (ros::ok())` loop notices shutdown -- send SIGINT (not SIGTERM/SIGKILL, which skip past it)
# and wait for the file, polling longer than FAST-LIO2's (that loop sleeps 5s per iteration
# before rechecking ros::ok(), and then downsamples/writes the full accumulated map).
kill -INT "$MAP_PID" 2>/dev/null || true
for _ in $(seq 1 90); do
  [ -f "$GLOBAL_MAP_PATH" ] && break
  kill -0 "$MAP_PID" 2>/dev/null || break
  sleep 1
done

if [ -n "${REC_PID:-}" ]; then
  kill -INT "$REC_PID" 2>/dev/null || true   # SIGINT lets rosbag record close the bag cleanly
  wait "$REC_PID" 2>/dev/null || true
fi
kill "$ORIENT_PID" "$ADAPTER_PID" "$EXPORT_PID" "$IMG_PID" "$FEAT_PID" "$IMU_PID" "$MAP_PID" 2>/dev/null || true
wait "$EXPORT_PID" 2>/dev/null || true

test -s "$OUT_TUM" || { echo "no trajectory written to $OUT_TUM" >&2; exit 1; }
echo "wrote $(wc -l < "$OUT_TUM") poses to $OUT_TUM"

if [ -f "$GLOBAL_MAP_PATH" ]; then
  cp "$GLOBAL_MAP_PATH" "$(dirname "$OUT_TUM")/map.pcd"
  echo "wrote $(dirname "$OUT_TUM")/map.pcd ($(du -h "$GLOBAL_MAP_PATH" | cut -f1))"
else
  echo "no map.pcd (savePCD not set, or mapOptmization didn't exit cleanly)" >&2
fi
