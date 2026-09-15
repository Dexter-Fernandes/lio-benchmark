# lio-benchmark tools image: downloads, verification, bag conversion/inspection, evaluation
# and run logging. Pure Python (rosbags reads ROS 1 and ROS 2 bags without ROS installed).
#
# Build (from the repository root):
#   docker build -f docker/tools/Dockerfile -t lio-benchmark/tools:dev .
# Run a command with the right mounts: scripts/in-tools.sh lio-bench data status

# python:3.11-slim-bookworm, digest resolved 2026-09-15
FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84

# uv 0.12.12, digest resolved 2026-09-15
COPY --from=ghcr.io/astral-sh/uv:0.12.12@sha256:73d2665b478d8fa2de1cf105c6841f8e9cb6b09e568fc7700440c09f8fcd7ac4 /uv /uvx /usr/local/bin/

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git sudo \
    && rm -rf /var/lib/apt/lists/*

# Non-root user whose UID/GID match the host user, so files written to the data root and
# run directories keep the host owner.
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} --create-home --shell /bin/bash ${USERNAME} \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME}

# The environment lives outside the workspace so it never collides with a host .venv.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    LIO_DATA_ROOT=/data/hilti22 \
    LIO_RUNS_ROOT=/runs \
    MPLBACKEND=Agg \
    WANDB_MODE=offline

# Dependencies first (cached layer), then the project itself in editable mode.
WORKDIR /workspaces/lio-benchmark
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --extra wandb --group dev
COPY src ./src
RUN uv sync --frozen --extra wandb --group dev \
    && chown -R ${USER_UID}:${USER_GID} /opt/venv

USER ${USERNAME}
CMD ["bash"]
