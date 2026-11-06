#!/usr/bin/env python3
"""run_video.py - run ONE video-streaming session under a netem profile and record the result (Amrutha, Day 2).

    python experiments/video/run_video.py --variant stock --profile mild --run 1 \
        --output-dir results/video_sanity/

Same interface as experiments/run_experiment.py: --variant, --profile, --run (a single run number), --output-dir.

What one call does
  1. checks the content folder, certificate and netem scripts exist
  2. applies the netem profile with experiments/netem/setup.sh (NOT reimplemented here)
  3. starts the aioquic HTTP/3 server in ns-server, serving experiments/video/content/
     (AIOQUIC_PACKET_THRESHOLD is set INSIDE the namespace: stock = unset, k20 = 20, dynamic = "dynamic" ...)
  4. runs stream_client.py in ns-client (Pooja's client), which writes the per-segment CSV
  5. waits for the server qlog (wait_for_server_qlog from experiments/transfer/run_transfer.py), stops the server
  6. removes the netem profile (experiments/netem/teardown.sh) - always, even after a failure
  7. appends ONE summary row to <output-dir>/video_results.csv in the agreed video schema

Everything for a run goes in  <output-dir>/<variant>/<profile>/run_N/ :
    segments.csv (+ .meta.json), client-qlog/, server-qlog/, server.log, run_info.json
Default --output-dir is experiments/video/results, which gives experiments/video/results/<variant>/<profile>/run_N/.

Profile "none" skips netem completely (only for Pooja's Day 2 baseline trace). Variants: stock, k5, k10, k20,
k100, dynamic, dynamic_undo (until Ruhin's dynamic code exists, dynamic / dynamic_undo behave like stock K=3).
Use --dry-run to print every command without running anything.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "experiments" / "transfer"))
import video_core as vc                                            # noqa: E402
from run_transfer import stop_server, wait_for_server_qlog         # noqa: E402  (reused, not rewritten)

NETEM = ROOT / "experiments" / "netem"
TRANSFER_DIR = ROOT / "experiments" / "transfer"
CONTENT = HERE / "content"
SERVER_IP, SERVER_PORT = "10.10.2.2", 4433
PROFILES = ["baseline", "mild", "moderate", "severe", "handover"]
VARIANTS = ["stock", "k5", "k10", "k20", "k100", "dynamic", "dynamic_undo"]
THRESHOLD_ENV = "AIOQUIC_PACKET_THRESHOLD"
RESULT_COLUMNS = ["variant", "profile", "run", "startup_delay_s", "stall_count", "total_stall_s",
                  "avg_bitrate_mbps", "quality_switches", "qoe_score"]      # = fake_video_results.csv header


def threshold_value(variant):
    """Value of AIOQUIC_PACKET_THRESHOLD for a variant; None means 'leave it unset' (stock K=3)."""
    if variant == "stock":
        return None
    m = re.fullmatch(r"k(\d+)", variant)
    if m:
        return m.group(1)
    if variant in ("dynamic", "dynamic_undo"):
        return variant
    raise ValueError("unknown variant %r" % variant)


def env_args(variant):
    """Arguments for `env` that set or unset the variable explicitly (sudo / ip netns exec can drop env)."""
    val = threshold_value(variant)
    return ["-u", THRESHOLD_ENV] if val is None else ["%s=%s" % (THRESHOLD_ENV, val)]


def run_command(cmd, dry_run=False, check=True, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    if dry_run:
        return 0
    r = subprocess.run(cmd, cwd=ROOT, check=False, **kw)
    if check and r.returncode:
        raise subprocess.CalledProcessError(r.returncode, cmd)
    return r.returncode


def server_command(variant, content_dir, server_qlog_dir):
    return (["sudo", "ip", "netns", "exec", "ns-server", "env"] + env_args(variant)
            + ["STATIC_ROOT=%s" % content_dir, sys.executable, str(ROOT / "examples" / "http3_server.py"),
               "--host", SERVER_IP, "--port", str(SERVER_PORT),
               "--certificate", str(TRANSFER_DIR / "ns-cert.pem"),
               "--private-key", str(TRANSFER_DIR / "ns-key.pem"),
               "--quic-log", str(server_qlog_dir),
               "--congestion-control-algorithm", "cubic"])


def client_command(variant, run_id, run_dir, extra):
    return (["sudo", "ip", "netns", "exec", "ns-client", "env"] + env_args(variant)
            + [sys.executable, str(HERE / "stream_client.py"),
               "--url", "https://%s:%d/manifest.mpd" % (SERVER_IP, SERVER_PORT),
               "--ca-certs", str(TRANSFER_DIR / "ns-cert.pem"),
               "--run-id", run_id,
               "--segments-out", str(run_dir / "segments.csv"),
               "--qlog-dir", str(run_dir / "client-qlog")] + extra)


def start_server(cmd, run_dir):
    log = open(run_dir / "server.log", "a")
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(75):
            if proc.poll() is not None:
                raise RuntimeError("HTTP/3 server exited during start-up. Read %s/server.log" % run_dir)
            chk = subprocess.run(["sudo", "ip", "netns", "exec", "ns-server", "ss", "-lun"],
                                 capture_output=True, text=True, check=False)
            if chk.returncode == 0 and ("%s:%d" % (SERVER_IP, SERVER_PORT)) in chk.stdout:
                return proc, log
            time.sleep(0.2)
        raise RuntimeError("HTTP/3 server did not become ready. Read %s/server.log" % run_dir)
    except Exception:
        stop_server(proc, log)
        raise


# --- summary row -----------------------------------------------------------------------------
def summarize_run(variant, profile, run, segments_csv, meta_json):
    """One row in the agreed video schema, computed from the client's per-segment CSV and its meta file.

    startup_delay_s, stall_count, total_stall_s come from the client's playback buffer (meta.json).
    avg_bitrate_mbps = mean bitrate of the downloaded segments (all segments are 4 s, so this equals the
    time-weighted mean); quality_switches = number of times the bitrate differs from the previous segment."""
    meta = json.loads(Path(meta_json).read_text())
    if not meta.get("completed"):
        raise RuntimeError("client did not finish the video (completed=false in %s)" % meta_json)
    with open(segments_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError("no segments in %s" % segments_csv)
    rates = [float(r["bitrate_mbps"]) for r in rows]
    avg = sum(rates) / len(rates)
    switches = sum(1 for a, b in zip(rates, rates[1:]) if a != b)
    stalls, stall_s = int(meta["stall_count"]), float(meta["total_stall_s"])
    return dict(variant=variant, profile=profile, run=run,
                startup_delay_s=round(float(meta["startup_delay_s"]), 3), stall_count=stalls,
                total_stall_s=round(stall_s, 3), avg_bitrate_mbps=round(avg, 3), quality_switches=switches,
                qoe_score=round(vc.qoe_score(avg, stalls, stall_s, switches), 4))


def append_result(results_file, row):
    results_file = Path(results_file)
    results_file.parent.mkdir(parents=True, exist_ok=True)
    new = not results_file.exists() or results_file.stat().st_size == 0
    if not new:
        with open(results_file, newline="") as f:
            header = next(csv.reader(f), [])
        if header != RESULT_COLUMNS:
            raise RuntimeError("%s has a different header %s; refusing to mix schemas" % (results_file, header))
    with open(results_file, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(row)


def git_info():
    def g(*a):
        r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, check=False)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    return dict(commit=g("rev-parse", "HEAD"), branch=g("rev-parse", "--abbrev-ref", "HEAD"),
                dirty=bool(g("status", "--porcelain")))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", required=True, choices=VARIANTS)
    ap.add_argument("--profile", required=True, choices=PROFILES + ["none"])
    ap.add_argument("--run", type=int, required=True, help="single run number (>= 1)")
    ap.add_argument("--output-dir", default=str(HERE / "results"))
    ap.add_argument("--content-dir", default=str(CONTENT))
    ap.add_argument("--max-segments", type=int, help="play only the first N segments (quick tests)")
    ap.add_argument("--dl-if", default="rc0")
    ap.add_argument("--ul-if", default="rs0")
    ap.add_argument("--router-ns", default="ns-router")
    ap.add_argument("--client-timeout", type=float, default=900.0, help="kill the client after this many seconds")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.run < 1:
        ap.error("--run must be at least 1")

    content = Path(a.content_dir).resolve()
    run_dir = Path(a.output_dir).resolve() / a.variant / a.profile / ("run_%d" % a.run)
    run_id = "%s__%s__%d" % (a.variant, a.profile, a.run)
    required = [content / "manifest.mpd", TRANSFER_DIR / "ns-cert.pem", TRANSFER_DIR / "ns-key.pem",
                NETEM / "setup.sh", NETEM / "teardown.sh", HERE / "stream_client.py"]
    for p in required:
        if not p.is_file():
            if a.dry_run:
                print("WARNING (dry run continues): required file not found: %s" % p)
            else:
                ap.error("Required file not found: %s" % p)
    if run_dir.exists() and any(run_dir.iterdir()) and not a.dry_run:
        ap.error("%s already has files. Old results are never overwritten: pick another --run or --output-dir."
                 % run_dir)

    setup = ["sudo", "bash", str(NETEM / "setup.sh"), a.profile, a.dl_if, a.ul_if, a.router_ns]
    teardown = ["sudo", "bash", str(NETEM / "teardown.sh"), a.dl_if, a.ul_if, a.router_ns]
    extra = ["--max-segments", str(a.max_segments)] if a.max_segments else []
    srv = server_command(a.variant, content, run_dir / "server-qlog")
    cli = client_command(a.variant, run_id, run_dir, extra)

    if a.dry_run:
        print("DRY RUN: nothing is executed. Run directory would be %s" % run_dir)
        if a.profile != "none":
            run_command(setup, dry_run=True)
        run_command(srv + ["&"], dry_run=True)
        run_command(cli, dry_run=True)
        if a.profile != "none":
            run_command(teardown, dry_run=True)
        return 0

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "server-qlog").mkdir(exist_ok=True)
    if os.geteuid() != 0:
        if subprocess.run(["sudo", "-v"], check=False).returncode:
            print("sudo authentication failed; stopping.", file=sys.stderr)
            return 1

    info = dict(variant=a.variant, profile=a.profile, run=a.run, run_id=run_id,
                threshold_env=threshold_value(a.variant), started=datetime.now().isoformat(timespec="seconds"),
                git=git_info())
    proc = log = None
    failure = None
    setup_attempted = False
    try:
        if a.profile != "none":
            setup_attempted = True
            run_command(setup)
        proc, log = start_server(srv, run_dir)
        run_command(cli, timeout=a.client_timeout)
        # aioquic writes the SERVER qlog only after the connection has fully closed: wait, then stop.
        info["server_qlog_complete"] = wait_for_server_qlog(run_dir / "server-qlog", timeout=15.0)
        stop_server(proc, log)
        proc = log = None
        row = summarize_run(a.variant, a.profile, a.run, run_dir / "segments.csv", run_dir / "segments.csv.meta.json")
        append_result(Path(a.output_dir).resolve() / "video_results.csv", row)
        info["result"] = row
        print("Saved result:", row)
    except Exception as exc:                      # includes CalledProcessError and TimeoutExpired
        failure = str(exc)
        info["failure"] = failure
        print("Run failed: %s" % exc, file=sys.stderr)
    finally:
        stop_server(proc, log)
        # server and client ran under sudo, so they created root-owned files: give them back to the user
        run_command(["sudo", "chown", "-R", "%d:%d" % (os.getuid(), os.getgid()), str(run_dir)], check=False)
        if setup_attempted:
            code = run_command(teardown, check=False)
            if code:
                print("WARNING: teardown exited with %d - check 'sudo ip netns exec %s tc qdisc show'"
                      % (code, a.router_ns), file=sys.stderr)
                failure = failure or "teardown failed"
        info["finished"] = datetime.now().isoformat(timespec="seconds")
        (run_dir / "run_info.json").write_text(json.dumps(info, indent=2))
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
