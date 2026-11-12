# experiments/video

Video workload for Phase 1: a DASH playback simulator over one persistent HTTP/3 connection, plus QoE parsing and plots.
Pooja owns everything in this folder except the encoded content and `run_video.py` (Amrutha).

## Files
| File | Purpose | Owner |
|---|---|---|
| `video_core.py` | pure logic: MPD parser, harmonic-mean ABR, playback buffer, QoE formula, offline simulator | Pooja |
| `stream_client.py` | the client (aioquic HTTP/3, real time); writes per-segment CSV + `.meta.json` | Pooja |
| `parse_video_results.py` | per-segment logs -> one QoE summary row per run (Day 0 schema) | Pooja |
| `plot_qoe.py` | Plots 5, 6, 7 (summary) and 8 (timeline), each with CSV data and alt-text | Pooja |
| `test_video_core.py`, `test_data/manifest_20s.mpd` | 21 offline tests; the MPD is a real ffmpeg-written manifest | Pooja |
| `smoke_test.sh` | real client vs a real local aioquic server on loopback (no sudo, no namespaces) | Pooja |
| `make_video_content.sh`, `check_video_content.py`, `run_video.py`, `fake_video_results.csv`, `make_fake_video_results.py` | content build, acceptance checks, runner, Day 0 stub | Amrutha (already on main) |



## Quick start (nothing here depends on anyone)
```bash
python -m pytest experiments/video/test_video_core.py -q          # 21 tests, offline
python experiments/video/plot_qoe.py summary --results experiments/video/fake_video_results.csv --out experiments/video/plots   # Amrutha's stub
bash experiments/video/make_video_content.sh                       # once, about 40 s, needs ffmpeg
bash experiments/video/smoke_test.sh                         # real client vs a real local aioquic server
```
The smoke test needs the aioquic example dependencies (`pip install wsproto starlette jinja2 dnslib httpx`).
On loopback the link is fast, so expect no stalls, startup well under 3 s and a climb to the 5 Mbps rung.
Stalls and rung changes under impairment are covered by the offline tests and, later, by runs on the real topology.

## Contracts (agreed with Amrutha; change only by agreement)
**Client command line**
```
stream_client.py --url https://10.10.2.2:4433/manifest.mpd --ca-certs <cert> \
    --run-id <variant>__<profile>__<run> --segments-out <csv> --qlog-dir <dir>
```
`--run-id` must be `variant__profile__run` (for example `stock__moderate__3`, `k20__severe__1`): the parser takes variant,
profile and run from it. Optional: `--max-buffer-s 12` (default), `--abr-window 3`, `--safety 0.8`, `--max-segments N`, `--insecure`.

**Per-segment CSV** (`segments.csv`): the 7 agreed columns plus `stall_s`
`run_id, segment_index, timestamp, bitrate_mbps, download_time_s, buffer_level_s, stall, stall_s`
(`timestamp` = seconds from the start of the run to the end of that download; `buffer_level_s` = buffer after the segment is
added; `stall` = stall events since the previous row; `stall_s` = stall seconds since the previous row.)
Next to it the client writes `segments.csv.meta.json` (startup delay, totals, parameters, `completed: true/false`).
A run with `completed: false` is skipped by the parser with a warning.

**Summary CSV** (`parse_video_results.py` output): `variant, profile, run, startup_delay_s, stall_count, total_stall_s,
avg_bitrate_mbps, quality_switches, qoe_score`.

**Folder layout the parser expects** (any depth; it finds `segments*.csv` recursively):
`results/video/<variant>/<profile>/run_N/{segments.csv, segments.csv.meta.json, client-qlog/, server-qlog/}`

**Content**: ONE `manifest.mpd` at the server root with five video representations (250k, 500k, 1000k, 2500k, 5000k), keyframe-aligned,
constant bitrate, 4 s segments (the ffmpeg command in the Phase 1 document). Audio is ignored by the client.

## Definitions
* Startup delay: from before the QUIC connection is opened until playback starts (buffer holds one segment).
* Stall: buffer reaches 0 while the video is still downloading; playback resumes when one segment is buffered.
  Running dry after the last segment is the end of the video, not a stall.
* ABR: first segment on the lowest rung, then the highest rung with bandwidth <= 0.8 x harmonic mean of the last 3 downloads.
* QoE = avg_bitrate_mbps - 0.3 x stalls - 0.05 x stall_seconds - 0.1 x quality_switches.
  Note: the ladder starts at 0.25 Mbps, so on poor profiles a handful of switches outweighs the bitrate and the score goes
  negative (see the stub). The Day 0 contract says the weights are adjustable after the baseline; decide that before the matrix.

## What I need from Amrutha, and what it unlocks
| From Amrutha | What it unlocks for Pooja |
|---|---|
| 1. The encoded 2-minute video in the agreed layout (single `manifest.mpd`, 5 aligned representations) and a note of the real bitrate of each rung | baseline trace on the real server and topology |
| 2. The server inside `ns-server` serving that content (`STATIC_ROOT`), with the server qlog directory created and flushed (waits for the qlog) | any run on the real topology |
| 3. `run_video.py` calling `stream_client.py` with the contract above and `--run-id variant__profile__run` | real runs end to end |
| 4. First real outputs in the folder layout above (baseline, then mild) | parser and plots on real data (swap the stub) |
| 5. The stock and k20 video matrix (5 profiles x 5 runs each) | stock vs k20 analysis |
| 6. The same for `dynamic` after the Day 6 freeze | final comparison |
Shortcut: the content is deterministic (synthetic source), so Pooja can build it herself with the ffmpeg command and `-t 120`
if Amrutha's copy is late; only the server/runner pieces truly need her.

## What depends on others (beyond Amrutha)
| Needs | From | Used for |
|---|---|---|
| Rule-attribution table (declared losses per rule, spurious per rule) | Reethika, after Ruhin's rule patch (Day 1) | the attribution paragraph of `section_mechanism.md`, and the QoE-vs-loss-rule discussion in `section_video.md` |
| The `dynamic` variant, frozen | Ruhin (Day 5 to 6) | video results for `dynamic` |
| Final variant names accepted by the runners | Reethika | `--run-id` naming |
Everything else (client, parser, plots, tests, stub, mechanism numbers from the Phase 0 matrix) is independent.
