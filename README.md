# cellprofiler-codemode-kit

A live, headless CellProfiler 5 session that a coding agent drives by running Python inside it.
It loads the JUMP Cell Painting analysis pipeline on one public field and keeps the images, objects and measurements in memory.
You can then try IdentifyPrimaryObjects settings through `cellprofiler_library`, measure and view the result in under a second, and commit, undo, save and run the saved pipeline headlessly.

The scope is narrow: IdentifyPrimaryObjects only, one field (JUMP plate BR00117035, well A01, site 1), and CellProfiler `main` at commit `49987452` (version `5.0.0.dev792`, a pre-release).

## Requirements

- Linux x86_64 with rootless Podman (`--userns=keep-id` support), git, and Python 3.8 or newer on the host.
  The `cps` client uses only the standard library.
- Network access during setup only.
  After setup, every container runs with `--network=none`.
- Disk: about 4 GB for the image (more while it builds) and 60 MB for the data.
- Each container gets 4 CPUs and an 8 GB memory limit (`cprun.sh`).

## Quickstart

```bash
git clone <this repo> cellprofiler-codemode-kit && cd cellprofiler-codemode-kit
```

```bash
podman build -t localhost/cellprofiler-codemode-kit:49987452 -f container/Dockerfile container
```

```bash
./scripts/fetch_data.py
```

```bash
./cps start
```

```bash
echo "cand = try_ipo(threshold_correction_factor=1.1); print(cand['count'])" | ./cps exec
```

```bash
./cps measure cand
```

```bash
./cps view cand --ref committed --crop 740 870 720 850
```

The last three commands are one try, measure and view cycle.
- `try_ipo` reruns IdentifyPrimaryObjects through the library with one setting changed, without touching the pipeline.
  On this field it finds 74 nuclei instead of 73.
- `measure` reports CellProfiler's own size, shape and intensity features and finds the one split, at (804,783).
- `view` writes a PNG and prints its path.
  Outlines only in the committed state are red, only in the candidate green, and in both yellow.

`./cps stop` ends the session.
`./cps --help` lists every command.

Expected times with the 4-CPU limit, as measured on two hosts:

| Step | Time |
|---|---|
| Image build from scratch | 3-15 min, mostly the pixi install; depends on network speed |
| Data fetch | under a minute |
| First container start after a build (Podman copies the image for `keep-id`) | about 2.5 min, once |
| `./cps start` | 15-50 s |
| `./cps start --full` (also runs every measurement module) | 95-115 s |
| `headless_run` of a saved pipeline | 2-2.5 min |
| One try, measure and view cycle | about 0.5 s warm; about 1 s for the first |
| Container tests | 35-60 s |

A build that finishes in seconds and prints `Using cache` for every step reused layers from an earlier build; add `--no-cache` to build from scratch.
The session itself uses about 0.7 GB of memory.

## How it works

- `container/Dockerfile` builds CellProfiler with its locked pixi `dev` environment (Python 3.9).
  It also downloads the JDK and Bio-Formats that CellProfiler 5 fetches on first Java start, and checks that the Bio-Formats jar is `formats-gpl` 9.0.0-rc2 by sha256.
- `cprun.sh` runs any command in that image with no network.
- `cps start` launches `codemode/session.py` as a daemon in a detached container named `cps-codemode`.
  The daemon listens on the unix socket `.cps/cps.sock`.
- Each `cps` call is a short-lived client, so session state survives between calls.
- The session is CellProfiler's Test Mode without the GUI.
  It uses the same `cellprofiler_core` calls the GUI uses to load one image set and run modules one at a time.
- `.cps/` (gitignored) holds the socket, views, output, and a record of every code block executed.

`AGENTS.md` describes the namespace and the working method for a coding agent.

## Tests

```bash
./cprun.sh python -m pytest -q /work/tests/test_session.py -p no:cacheprovider -p no:warnings
```

```bash
python3 tests/test_cps_cli.py
```

The first runs 15 tests in the container on the pipeline trimmed to its first 11 modules, in about a minute.
The second checks, on the host, that the client reports a missing session cleanly.
Run it while no session is running.

## Known limits

- CellProfiler `main` is a pre-release, and it re-serializes pipelines on save (see `fixture/SOURCE.md`).
- Bio-Formats is pinned by checking the jar after download.
  If Maven's `RELEASE` for `ome:formats-gpl` moves past 9.0.0-rc2, the image build fails at that check instead of silently using a different version.
- The daemon serves one request at a time, so a long `exec` (for example `headless_run`) blocks other clients.
- Agent code runs with the session's privileges inside the container.
  `SystemExit` and `KeyboardInterrupt` are caught, but `os._exit()` ends the daemon.
- Logs contain two kinds of error lines that are harmless here: - Bio-Formats prints `"loci.formats.in.<Name>Reader" is not valid.` for a few optional readers it cannot load.
  They are not used for these TIFFs. - A headless run logs one `Unable to decode object measurement` error from `hdf5_dict` during export.
  The CSVs are complete.
- `cps stop` exits the daemon without the JVM's own teardown.
  A JPype crash in that teardown once left an `hs_err_pid*.log` in the repo root; it was not reproduced in 6 later stops.
  Any JVM crash log now goes to `.cps/` (`-XX:ErrorFile` in `cprun.sh`), and `hs_err_pid*.log` is gitignored.
- The code in this repo is under the BSD 3-Clause License (`LICENSE`), the same license as CellProfiler.
  The fixture's sources and terms are separate and listed in `fixture/SOURCE.md`.
