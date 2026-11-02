#!/usr/bin/env bash
# Run a command in the CellProfiler 5 container with no network. The repo is mounted at /work and
# data/ read-only at /fixture/assets. The image sets thread counts to 1: without that, BLAS/OpenMP
# start one thread per host core under --cpus, which made MeasureTexture about 60x slower.
# CPRUN_PODMAN_ARGS adds podman flags (cps uses it for -d --name). CP_IMAGE overrides the image.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
exec podman run --rm -i ${CPRUN_PODMAN_ARGS:-} --network=none --userns=keep-id --cpus 4 --memory 8g \
  -v "$here":/work:Z -v "$here/data":/fixture/assets:ro,Z -e PYTHONPATH=/work \
  -e JAVA_TOOL_OPTIONS=-XX:ErrorFile=/work/.cps/hs_err_pid%p.log \
  "${CP_IMAGE:-localhost/cellprofiler-codemode-kit:49987452}" \
  pixi run --manifest-path /opt/cp/pixi.toml --locked -e dev "$@"
