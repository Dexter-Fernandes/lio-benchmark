# LIO-SAM baseline image: ROS Noetic + TixiaoShan/LIO-SAM pinned at 0be1fbe (2023-04-17,
# latest master at integration time) + this repo's input/output/orientation adapters.
#
# LIO-SAM's own bundled instructions target Kinetic; master has never merged a Noetic port
# (PRs #393 "ported to noetic" and #408 "patch to work with noetic" both still open/closed
# unmerged). The fix that upstream's own maintainer (TixiaoShan) summarized and endorsed in
# github.com/TixiaoShan/LIO-SAM/issues/206 is applied here as source patches, not improvised:
#   1. GTSAM 4.0.3 from the official PPA (README.md's own instructions), not built from
#      source -- building GTSAM 4.0.2 from source with -DGTSAM_BUILD_WITH_MARCH_NATIVE=OFF
#      was the original failure mode reported in #206.
#   2. include/utility.h: `#include <opencv/cv.h>` -> `#include <opencv2/opencv.hpp>`, and
#      moved to after the PCL headers -- otherwise FLANN's `unordered_map::serialize` clashes
#      with OpenCV's `USE_UNORDERED_MAP` macro leaking from an earlier include (issue #206,
#      confirmed independently by two reporters; see flann-lib/flann#214).
#   3. CMakeLists.txt: `-std=c++11` -> `-std=c++14`.
# No GPU/CUDA dependency (package.xml only lists roscpp/rospy/tf/cv_bridge/pcl_conversions/
# message_generation/GTSAM/OpenMP/PCL/OpenCV/Boost -- verified, not assumed).
#
# Pinned base digest so re-builds don't silently drift (docs/methods.md: "every image pins
# its source revision and base-image digest"); same digest already vetted for fast_lio2.
FROM ros@sha256:72b8bc59035dc0a5b8e07aae28c16caa84192971d72d207c72ed734fb1d5e97d

ARG LIO_SAM_REF=0be1fbe6275fb8366d5b800af4fc8c76a885c869

RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential cmake software-properties-common gnupg \
        ros-noetic-pcl-ros ros-noetic-pcl-conversions ros-noetic-tf \
        ros-noetic-message-generation ros-noetic-rosbag ros-noetic-eigen-conversions \
        ros-noetic-cv-bridge \
        libeigen3-dev libpcl-dev libopencv-dev \
    && add-apt-repository -y ppa:borglab/gtsam-release-4.0 \
    && apt-get update && apt-get install -y --no-install-recommends \
        libgtsam-dev libgtsam-unstable-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /catkin_ws/src
WORKDIR /catkin_ws/src

RUN git clone https://github.com/TixiaoShan/LIO-SAM.git lio_sam && \
    cd lio_sam && git checkout ${LIO_SAM_REF} && \
    sed -i 's/#include <opencv\/cv.h>//' include/utility.h && \
    sed -i '/#include <pcl_conversions\/pcl_conversions.h>/a #include <opencv2\/opencv.hpp>' include/utility.h && \
    sed -i 's/set(CMAKE_CXX_FLAGS "-std=c++11")/set(CMAKE_CXX_FLAGS "-std=c++14")/' CMakeLists.txt

WORKDIR /catkin_ws
RUN . /opt/ros/noetic/setup.sh && catkin_make

COPY adapters/lio_sam/pointcloud_adapter.py adapters/lio_sam/ros_node.py \
     adapters/lio_sam/odom_to_tum.py adapters/lio_sam/orientation_filter.py \
     adapters/lio_sam/imu_orientation_node.py /adapters/lio_sam/
COPY configs/lio_sam/hilti22.yaml /configs/lio_sam/hilti22.yaml
COPY scripts/run_lio_sam.sh /run_lio_sam.sh
RUN chmod +x /run_lio_sam.sh /adapters/lio_sam/*.py

# No ENTRYPOINT: the devcontainer needs a plain shell. Run a baseline with, e.g.:
#   docker run --rm -v <data root>:/data/hilti22:ro -v $(pwd)/runs:/runs <image> \
#       /run_lio_sam.sh /data/hilti22/rosbags/exp14.bag /runs/exp14/lio_sam.tum
