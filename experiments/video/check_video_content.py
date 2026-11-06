#!/usr/bin/env python3
"""check_video_content.py - the Day 1 acceptance checks for the DASH test video (Amrutha).

    python3 experiments/video/check_video_content.py experiments/video/content --duration 120

Checks (from the work distribution): ONE manifest with 5 video representations (250000..5000000) + audio;
every segment file listed exists; total size < 500 MB; every rendition's real bitrate within 10% of nominal
(file bytes x 8 / duration); all renditions have the same number of segments.
Use --nominal 250000,500000 for the 10 s Day 0 test.
Exit code 0 = all passed, 1 = something failed.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import video_core as vc  # Pooja's parser: this also proves the client can read the manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("content_dir")
    ap.add_argument("--duration", type=float, default=120.0)
    ap.add_argument("--nominal", default="250000,500000,1000000,2500000,5000000")
    ap.add_argument("--tolerance", type=float, default=0.10)
    ap.add_argument("--max-mb", type=float, default=500.0)
    a = ap.parse_args()

    d = Path(a.content_dir)
    nominal = [int(x) for x in a.nominal.split(",")]
    ok = True

    def report(name, passed, detail=""):
        nonlocal ok
        ok &= bool(passed)
        print("[%s] %s %s" % ("PASS" if passed else "FAIL", name, detail))

    mpds = list(d.glob("*.mpd"))
    report("exactly one manifest.mpd", len(mpds) == 1 and mpds[0].name == "manifest.mpd", str([m.name for m in mpds]))
    if not (d / "manifest.mpd").exists():
        sys.exit(1)
    text = (d / "manifest.mpd").read_text()
    root = ET.fromstring(text)
    ns = root.tag[: root.tag.index("}") + 1]
    n_audio = sum(1 for aset in root.iter(ns + "AdaptationSet")
                  if (aset.get("contentType") == "audio" or "audio" in (aset.get("mimeType") or "")))
    report("one audio adaptation set", n_audio == 1, "(found %d)" % n_audio)

    m = vc.parse_mpd(text)          # raises if segment counts differ between renditions
    bw = [r.bandwidth for r in m.representations]
    report("video representations", len(bw) == len(nominal), "bandwidths=%s" % bw)
    report("MPD bandwidths match the ladder", sorted(bw) == sorted(nominal))
    report("all renditions have the same segment count", True, "(%d segments of %.1f s)" % (m.n_segments, m.segment_durations[0]))
    expect_n = int(-(-a.duration // 4))   # ceil: a 10 s test gives 3 segments (4+4+2)
    report("segment count = duration / 4 s", m.n_segments == expect_n, "(%d, expected %d)" % (m.n_segments, expect_n))

    missing, per_rep_bytes = [], {}
    for r in m.representations:
        total = 0
        init = d / vc.init_path(r)
        if not init.exists():
            missing.append(str(init))
        else:
            total += init.stat().st_size
        for i in range(m.n_segments):
            p = d / vc.segment_path(r, i)
            if not p.exists():
                missing.append(str(p))
            else:
                total += p.stat().st_size
        per_rep_bytes[r.id] = total
    report("all init + media segment files exist", not missing, "(missing %d: %s)" % (len(missing), missing[:3]))

    for r in m.representations:
        real = per_rep_bytes[r.id] * 8 / a.duration
        dev = (real - r.bandwidth) / r.bandwidth
        report("bitrate rep %s nominal %d" % (r.id, r.bandwidth), abs(dev) <= a.tolerance,
               "real %.0f bps (%+.1f%%)" % (real, dev * 100))

    total_mb = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6
    report("total size under %.0f MB" % a.max_mb, total_mb < a.max_mb, "(%.1f MB)" % total_mb)
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
