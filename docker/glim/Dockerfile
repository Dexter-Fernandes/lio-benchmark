# GLIM baseline image: ROS 2 Humble + koide3/glim_ros (CPU-only) via koide3's own official
# binary PPA (https://koide3.github.io/ppa/, "GLIM(1.2.0)" changelog entry).
#
# GLIM needs no Python point-cloud or orientation adapter, unlike FAST-LIO2/LIO-SAM -- verified
# against the pinned source (docs/methods.md "GLIM integration"), so this image copies in only
# configs/glim/hilti22.yaml, scripts/run_glim.sh, scripts/glim_materialize_config.py and the
# TUM exporter node.
#
# Building GTSAM 4.3a1 + gtsam_points + glim + glim_ros2 from source was tried first and
# abandoned: the borglab GTSAM 4.0 PPA (the package LIO-SAM uses on Noetic/focal) does not
# actually publish jammy packages despite appearing to on its Launchpad overview page (its
# `dists/` only lists bionic/devel/focal/xenial -- checked directly, not assumed) -- and
# gtsam_points has since moved to GTSAM 4.3a1 regardless, unrelated to LIO-SAM's 4.0.3. Rather
# than build four C++ projects from source on this machine's 2c/4t CPU, koide3's own PPA ships
# a maintained, versioned, no-CUDA binary (`ros-humble-glim-ros`, confirmed to depend on
# `ros-humble-glim` -> `libgtsam-points-dev` -> `libgtsam-notbb-dev`, i.e. GTSAM 4.3.0 built
# with GTSAM_WITH_TBB=OFF, per the PPA's own build notes) -- this is upstream's own documented,
# recommended install path (gtsam_points' README "Install from PPA" section), not a shortcut
# around it.
#
# Pinned base digest so re-builds don't silently drift (docs/methods.md: "every image pins
# its source revision and base-image digest"); pulled and inspected fresh for this image
# (ROS 2 Humble has no shared digest with the Noetic images fast_lio2/lio_sam use). The GLIM
# packages are pinned to a specific PPA version instead of a git ref, the closest equivalent
# for a binary dependency.
FROM ros@sha256:1813d3c85d7f96ff7d3012d865204583255740182db5d0065f8f8cd029a83138

ARG GLIM_ROS_VERSION=1.2.2-0jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates \
        ros-humble-rosbag2-storage-mcap python3-yaml \
    && curl -s --compressed "https://koide3.github.io/ppa/ubuntu2204/KEY.gpg" \
         | gpg --dearmor | tee /etc/apt/trusted.gpg.d/koide3_ppa.gpg >/dev/null \
    && echo "deb [signed-by=/etc/apt/trusted.gpg.d/koide3_ppa.gpg] https://koide3.github.io/ppa/ubuntu2204 ./" \
         | tee /etc/apt/sources.list.d/koide3_ppa.list \
    && apt-get update && apt-get install -y --no-install-recommends \
        ros-humble-glim-ros=${GLIM_ROS_VERSION} \
    && rm -rf /var/lib/apt/lists/*

COPY adapters/glim/odom_to_tum.py /adapters/glim/odom_to_tum.py
COPY configs/glim/hilti22.yaml /configs/glim/hilti22.yaml
COPY scripts/run_glim.sh /run_glim.sh
COPY scripts/glim_materialize_config.py /scripts/glim_materialize_config.py
RUN chmod +x /run_glim.sh /adapters/glim/*.py /scripts/*.py

# No ENTRYPOINT: the devcontainer needs a plain shell. Run a baseline with, e.g.:
#   docker run --rm -v <data root>:/data/hilti22:ro -v $(pwd)/runs:/runs <image> \
#       /run_glim.sh /data/hilti22/rosbag2/exp14_basement_2 /runs/exp14/glim.tum
