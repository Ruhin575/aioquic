#!/usr/bin/env python3
"""video_core.py - pure logic for the video client (no network, no aioquic).

Everything that decides what the player DOES lives here, so it can be unit-tested with a
simulated clock (see test_video_core.py) and reused by stream_client.py (real network)
and make_fake_video_data.py (synthetic stub data).

Contents
  parse_mpd()        read a DASH manifest (SegmentTemplate + SegmentTimeline, as ffmpeg writes it)
  segment_path()     URL path of a media segment, init_path() of an init segment
  HarmonicABR        throughput-based bitrate rule (harmonic mean of last N downloads x safety)
  PlaybackBuffer     buffer model: startup delay, stalls, stall seconds (driven by explicit time)
  qoe_score()        the team's QoE formula (Day 0 contract)
  simulate_session() deterministic offline session over a bandwidth function

Buffer model (documented because the numbers depend on it)
  * time t0 = start of the run (before the connection is opened); all times are seconds.
  * playback starts when the buffer first holds `startup_buffer_s` seconds of video
    (default: one segment). Startup delay = that time - t0.
  * once playing, the buffer drains in real time. If it reaches 0 before the content has been
    fully downloaded, a STALL starts; playback resumes when the buffer holds `resume_buffer_s`.
  * running out of buffer after the LAST segment has arrived is the end of the video, not a stall.
"""
import math
import re
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field

# --- QoE weights (Day 0 contract; adjustable after the baseline) -------------------------
QOE_STALL_COUNT = 0.3
QOE_STALL_SECONDS = 0.05
QOE_SWITCH = 0.1


def qoe_score(avg_bitrate_mbps, stall_count, total_stall_s, quality_switches):
    return (avg_bitrate_mbps - QOE_STALL_COUNT * stall_count
            - QOE_STALL_SECONDS * total_stall_s - QOE_SWITCH * quality_switches)


# --- MPD -----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Representation:
    id: str
    bandwidth: int                 # bits per second, as declared in the MPD
    width: int = 0
    height: int = 0
    init_template: str = ""
    media_template: str = ""
    start_number: int = 1


@dataclass
class Manifest:
    representations: list = field(default_factory=list)      # video only, ascending bandwidth
    segment_durations: list = field(default_factory=list)    # seconds, one per segment

    @property
    def n_segments(self):
        return len(self.segment_durations)

    @property
    def duration_s(self):
        return float(sum(self.segment_durations))


def _iso_duration(text):
    m = re.fullmatch(r"PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?", text or "")
    if not m:
        raise ValueError("cannot parse duration %r" % text)
    h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return 3600 * h + 60 * mi + s


def _durations_from_template(tpl, ns, presentation_s):
    timescale = int(tpl.get("timescale", "1"))
    timeline = tpl.find(ns + "SegmentTimeline")
    durations = []
    if timeline is not None:
        for s in timeline.findall(ns + "S"):
            d = int(s.get("d"))
            repeat = int(s.get("r", "0"))
            durations += [d / timescale] * (repeat + 1)
    else:
        d = int(tpl.get("duration")) / timescale
        durations = [d] * int(math.ceil(presentation_s / d))
    return durations


def parse_mpd(text):
    """Parse a DASH MPD into a Manifest. Only the video adaptation set is used (audio is ignored).

    Supports SegmentTemplate with a SegmentTimeline or a fixed `duration`, placed either on the
    Representation (what ffmpeg writes) or on the AdaptationSet. All video representations must have
    the same number of segments (keyframe-aligned encode) or a ValueError is raised."""
    root = ET.fromstring(text)
    ns = root.tag[: root.tag.index("}") + 1] if root.tag.startswith("{") else ""
    presentation_s = _iso_duration(root.get("mediaPresentationDuration")) \
        if root.get("mediaPresentationDuration") else 0.0
    reps, all_durations = [], []
    for aset in root.iter(ns + "AdaptationSet"):
        rep_elems = aset.findall(ns + "Representation")
        is_video = (aset.get("contentType") == "video"
                    or (aset.get("mimeType") or "").startswith("video")
                    or any((r.get("mimeType") or "").startswith("video") for r in rep_elems))
        if not is_video:
            continue
        set_tpl = aset.find(ns + "SegmentTemplate")
        for r in rep_elems:
            tpl = r.find(ns + "SegmentTemplate")
            if tpl is None:
                tpl = set_tpl
            if tpl is None:
                raise ValueError("representation %s has no SegmentTemplate" % r.get("id"))
            reps.append(Representation(
                id=r.get("id"), bandwidth=int(r.get("bandwidth")),
                width=int(r.get("width", 0)), height=int(r.get("height", 0)),
                init_template=tpl.get("initialization", ""), media_template=tpl.get("media", ""),
                start_number=int(tpl.get("startNumber", "1"))))
            all_durations.append(_durations_from_template(tpl, ns, presentation_s))
    if not reps:
        raise ValueError("no video representations found in the manifest")
    if len({len(d) for d in all_durations}) != 1:
        raise ValueError("video representations have different segment counts: %s"
                         % sorted({len(d) for d in all_durations}))
    order = sorted(range(len(reps)), key=lambda i: reps[i].bandwidth)
    return Manifest(representations=[reps[i] for i in order],
                    segment_durations=all_durations[order[0]])


def _expand(template, rep, number=None):
    out = template.replace("$RepresentationID$", str(rep.id)).replace("$Bandwidth$", str(rep.bandwidth))
    if number is not None:
        out = re.sub(r"\$Number(%0?\d*d)?\$", lambda m: (m.group(1) or "%d") % number, out)
    return out


def segment_path(rep, index):
    """URL path (no leading slash) of media segment `index` (0-based)."""
    return _expand(rep.media_template, rep, rep.start_number + index)


def init_path(rep):
    return _expand(rep.init_template, rep)


# --- ABR -----------------------------------------------------------------------------------
class HarmonicABR:
    """Pick the highest representation whose bandwidth fits `safety` x the harmonic mean of the
    throughput of the last `window` segment downloads. Harmonic mean is dominated by slow samples,
    so one bad download pulls the estimate down quickly."""

    def __init__(self, window=3, safety=0.8, initial_index=0):
        self.samples = deque(maxlen=window)
        self.safety = safety
        self.initial_index = initial_index

    def add_sample(self, throughput_bps):
        if throughput_bps and throughput_bps > 0:
            self.samples.append(float(throughput_bps))

    def estimate_bps(self):
        if not self.samples:
            return None
        return len(self.samples) / sum(1.0 / s for s in self.samples)

    def choose(self, reps):
        """reps: ascending by bandwidth."""
        est = self.estimate_bps()
        if est is None:
            return reps[min(self.initial_index, len(reps) - 1)]
        budget = est * self.safety
        best = reps[0]
        for r in reps:
            if r.bandwidth <= budget:
                best = r
        return best


# --- Playback buffer -----------------------------------------------------------------------
class PlaybackBuffer:
    def __init__(self, t0, startup_buffer_s=4.0, resume_buffer_s=None):
        self.t0 = t0
        self.last_t = t0
        self.startup_buffer_s = startup_buffer_s
        self.resume_buffer_s = startup_buffer_s if resume_buffer_s is None else resume_buffer_s
        self.level = 0.0
        self.playing = False
        self.started = False
        self.ended = False
        self.all_downloaded = False
        self.startup_delay = None
        self.stall_count = 0
        self.total_stall_s = 0.0          # finished stalls only
        self.stall_start = None

    def advance(self, now):
        """Let playback run from the last update to `now`."""
        prev, self.last_t = self.last_t, max(self.last_t, now)
        dt = now - prev
        if dt <= 0 or not self.playing:
            return
        if self.level >= dt:
            self.level -= dt
            return
        played, self.level, self.playing = self.level, 0.0, False
        if self.all_downloaded:
            self.ended = True                      # end of the video, not a stall
        else:
            self.stall_count += 1
            self.stall_start = prev + played

    def _maybe_start(self, now):
        if self.playing or self.ended:
            return
        target = self.startup_buffer_s if not self.started else self.resume_buffer_s
        if self.level >= target or (self.all_downloaded and self.level > 0):
            if not self.started:
                self.started = True
                self.startup_delay = now - self.t0
            elif self.stall_start is not None:
                self.total_stall_s += now - self.stall_start
                self.stall_start = None
            self.playing = True

    def add_segment(self, now, segment_s):
        self.advance(now)
        self.level += segment_s
        self._maybe_start(now)

    def mark_all_downloaded(self, now):
        self.advance(now)
        self.all_downloaded = True
        self._maybe_start(now)


# --- Offline simulation --------------------------------------------------------------------
ROW_COLUMNS = ["run_id", "segment_index", "timestamp", "bitrate_mbps",
               "download_time_s", "buffer_level_s", "stall", "stall_s"]


def simulate_session(manifest, bandwidth_bps, run_id="sim", rtt_s=0.1, max_buffer_s=30.0,
                     startup_buffer_s=None, abr=None):
    """Run the player logic against a bandwidth function bandwidth_bps(t) -> bits/s, with no network.

    Segment sizes are rep.bandwidth x duration (constant bitrate). The download time of a segment is
    rtt + size / bandwidth(request time). Returns (rows, summary); rows follow ROW_COLUMNS."""
    reps = manifest.representations
    abr = abr or HarmonicABR()
    first = manifest.segment_durations[0]
    buf = PlaybackBuffer(0.0, startup_buffer_s if startup_buffer_s is not None else first)
    now = 2 * rtt_s                                  # handshake + manifest fetch
    rows, prev_stalls, prev_stall_s = [], 0, 0.0
    for idx, seg_s in enumerate(manifest.segment_durations):
        buf.advance(now)
        if buf.playing and buf.level + seg_s > max_buffer_s:        # buffer full: wait
            now += buf.level + seg_s - max_buffer_s
            buf.advance(now)
        rep = abr.choose(reps)
        t_req = now
        size_bits = rep.bandwidth * seg_s
        dl = rtt_s + size_bits / max(bandwidth_bps(t_req), 1.0)
        now = t_req + dl
        abr.add_sample(size_bits / dl)
        buf.add_segment(now, seg_s)
        rows.append(dict(run_id=run_id, segment_index=idx, timestamp=round(now, 4),
                         bitrate_mbps=rep.bandwidth / 1e6, download_time_s=round(dl, 4),
                         buffer_level_s=round(buf.level, 4), stall=buf.stall_count - prev_stalls,
                         stall_s=round(buf.total_stall_s - prev_stall_s, 4)))
        prev_stalls, prev_stall_s = buf.stall_count, buf.total_stall_s
    buf.mark_all_downloaded(now)
    if rows and (buf.stall_count > prev_stalls or buf.total_stall_s > prev_stall_s):
        rows[-1]["stall"] += buf.stall_count - prev_stalls
        rows[-1]["stall_s"] = round(rows[-1]["stall_s"] + buf.total_stall_s - prev_stall_s, 4)
    summary = dict(run_id=run_id, startup_delay_s=buf.startup_delay, stall_count=buf.stall_count,
                   total_stall_s=buf.total_stall_s, n_segments=manifest.n_segments,
                   video_duration_s=manifest.duration_s)
    return rows, summary