# Headless CellProfiler 5 (main) for a live code-mode session. Build needs network; runs do not.
FROM docker.io/library/ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852
ENV DEBIAN_FRONTEND=noninteractive PIXI_CACHE_DIR=/opt/pixi-cache PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg HOME=/opt/home OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git build-essential pkg-config \
      libgl1 libglu1-mesa libsm6 libxext6 libxrender1 libgomp1 libgtk-3-0t64 libnotify4 libsdl2-2.0-0 libpcre2-32-0
RUN curl -fL --retry 3 https://github.com/prefix-dev/pixi/releases/download/v0.81.0/pixi-x86_64-unknown-linux-musl.tar.gz -o /tmp/pixi.tar.gz \
    && printf '%s  %s\n' 7aa3ec39aecceff9062fa2ed4d42cbaa0bdc25ddea727d048e061cf188d434f6 /tmp/pixi.tar.gz | sha256sum -c - \
    && tar -xzf /tmp/pixi.tar.gz -C /usr/local/bin pixi
# Full history with tags: setuptools-scm derives the version from them, and cellprofiler_core
# refuses Version 5 pipeline files if the version comes out as 0.x.
ARG CP_COMMIT=49987452e98d559821ca04156a91366de99f51bb
WORKDIR /opt/cp
RUN git init -q && git remote add origin https://github.com/CellProfiler/CellProfiler.git \
    && git fetch -q --tags origin $CP_COMMIT && git checkout -q --detach FETCH_HEAD \
    && git describe --tags --long --first-parent --match 'v[0-9]*'
RUN pixi install --locked -e dev
# CellProfiler 5 downloads a JDK and Bio-Formats from Maven when Java first starts. Do it now, with
# network, into HOME, and check we got the expected Bio-Formats jar so later builds cannot drift.
ARG FORMATS_GPL=9.0.0-rc2
ARG FORMATS_GPL_SHA256=897e59e669962311b18925ecf7673ccd71c369abb95374f2c291343c82e149cc
RUN mkdir -p $HOME \
    && pixi run --locked -e dev python -c "import cellprofiler; print('CellProfiler', cellprofiler.__version__); \
from cellprofiler_core.utilities.java import start_java; start_java()" \
    && jar=$HOME/.m2/repository/ome/formats-gpl/$FORMATS_GPL/formats-gpl-$FORMATS_GPL.jar \
    && ls $HOME/.m2/repository/ome/formats-gpl/ \
    && printf '%s  %s\n' $FORMATS_GPL_SHA256 $jar | sha256sum -c - \
    && chmod -R a+rwX $HOME
WORKDIR /work
