# GLIM GPU-backend image: koide3's own official prebuilt ROS 2 Humble + CUDA 12.2 image
# (docker.io/koide3/glim_ros2:humble_cuda12.2), the GPU sibling of docker/glim/Dockerfile's
# PPA-based CPU image. No apt/source build at all: unlike the CPU image (which installs
# ros-humble-glim-ros from koide3's PPA on top of a plain ROS base), this base image already
# has glim_ros (incl. glim_rosbag) built with CUDA support -- confirmed by dumping its
# installed config/*.json (libodometry_estimation_gpu.so, config_odometry_gpu.json etc. all
# present), which is also what configs/glim/hilti22_gpu.yaml's header verification is based on.
#
# CUDA 12.2 is pinned deliberately, not just inherited from the tag name: this host's GPU
# (GeForce 940MX, Maxwell, compute capability 5.0) loses CUDA support entirely in CUDA 13.0
# (Turing becomes the floor) -- checked directly against NVIDIA's Maxwell compatibility notes,
# not assumed. Requires the host's Docker daemon to have nvidia-container-toolkit configured
# and `docker run --gpus all` working; this image cannot help with that, it's a host-level
# prerequisite (see docs/methods.md "GLIM integration" GPU backend section).
FROM koide3/glim_ros2@sha256:fef67fa47529ba9279400fc41a914df030a1c8ec9a466512be76c9dfe06bc70a

# PyYAML and rclpy are already present in this base image (checked directly), but the MCAP
# rosbag2 storage plugin isn't (our rosbag2/<seq> conversions are MCAP) -- same package
# docker/glim/Dockerfile installs for the CPU image.
RUN apt-get update && apt-get install -y --no-install-recommends ros-humble-rosbag2-storage-mcap \
    && rm -rf /var/lib/apt/lists/*

COPY adapters/glim/odom_to_tum.py /adapters/glim/odom_to_tum.py
COPY configs/glim/hilti22_gpu.yaml /configs/glim/hilti22_gpu.yaml
COPY scripts/run_glim.sh /run_glim.sh
COPY scripts/glim_materialize_config.py /scripts/glim_materialize_config.py
RUN chmod +x /run_glim.sh /adapters/glim/*.py /scripts/*.py

# No ENTRYPOINT, same reasoning as docker/glim/Dockerfile. Run a baseline with, e.g.:
#   docker run --rm --gpus all -v <data root>:/data/hilti22:ro -v $(pwd)/runs:/runs \
#       -e GLIM_CONFIG=/configs/glim/hilti22_gpu.yaml <image> \
#       /run_glim.sh /data/hilti22/rosbag2/exp14_basement_2 /runs/exp14/glim_gpu.tum
