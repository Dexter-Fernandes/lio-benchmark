# FAST-LIO2 baseline image: ROS Noetic + hku-mars/FAST_LIO pinned at 7cc4175 (2024-07-23),
# its livox_ros_driver build dependency, and this repo's input/output adapters.
#
# Pinned base digest so re-builds don't silently drift (docs/methods.md: "every image pins
# its source revision and base-image digest").
FROM ros@sha256:72b8bc59035dc0a5b8e07aae28c16caa84192971d72d207c72ed734fb1d5e97d

ARG FAST_LIO_REF=7cc4175de6f8ba2edf34bab02a42195b141027e9
ARG LIVOX_DRIVER_REF=3d240d5666129e1a3052e78ee8487a04b08fdda3

RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential cmake \
        ros-noetic-pcl-ros ros-noetic-pcl-conversions ros-noetic-tf \
        ros-noetic-message-generation ros-noetic-rosbag ros-noetic-eigen-conversions \
        libeigen3-dev libpcl-dev python3-catkin-tools \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /catkin_ws/src
WORKDIR /catkin_ws/src

RUN git clone https://github.com/Livox-SDK/livox_ros_driver.git && \
    cd livox_ros_driver && git checkout ${LIVOX_DRIVER_REF}
RUN git clone https://github.com/hku-mars/FAST_LIO.git && \
    cd FAST_LIO && git checkout ${FAST_LIO_REF} && \
    git submodule update --init --recursive

WORKDIR /catkin_ws
RUN . /opt/ros/noetic/setup.sh && catkin_make

COPY adapters/fast_lio2/pointcloud_adapter.py adapters/fast_lio2/ros_node.py \
     adapters/fast_lio2/odom_to_tum.py /adapters/fast_lio2/
COPY configs/fast_lio2/hilti22.yaml /configs/fast_lio2/hilti22.yaml
COPY scripts/run_fast_lio2.sh /run_fast_lio2.sh
RUN chmod +x /run_fast_lio2.sh /adapters/fast_lio2/*.py

# No ENTRYPOINT: the devcontainer needs a plain shell. Run a baseline with, e.g.:
#   docker run --rm -v <data root>:/data/hilti22:ro -v $(pwd)/runs:/runs <image> \
#       /run_fast_lio2.sh /data/hilti22/rosbags/exp14.bag /runs/exp14/fast_lio2.tum
