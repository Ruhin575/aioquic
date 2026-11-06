"""Offline tests for video_core.py (no network). Run from the repo root:

    python -m pytest experiments/video/test_video_core.py -q
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import video_core as vc  # noqa: E402

MPD = (HERE / "test_data" / "manifest_20s.mpd").read_text()          # a real ffmpeg-written manifest


@pytest.fixture(scope="module")
def manifest():
    return vc.parse_mpd(MPD)


# ---- MPD ----------------------------------------------------------------------------------
def test_parse_mpd_video_only_and_sorted(manifest):
    assert [r.bandwidth for r in manifest.representations] == [250000, 500000, 1000000, 2500000, 5000000]
    assert manifest.n_segments == 5 and manifest.duration_s == pytest.approx(20.0)
    assert all(d == pytest.approx(4.0) for d in manifest.segment_durations)


def test_segment_and_init_paths(manifest):
    rep = manifest.representations[3]                                  # id "3", 2.5 Mbps
    assert vc.init_path(rep) == "init-stream3.m4s"
    assert vc.segment_path(rep, 0) == "chunk-stream3-00001.m4s"
    assert vc.segment_path(rep, 4) == "chunk-stream3-00005.m4s"


def test_parse_mpd_rejects_unaligned_representations():
    bad = MPD.replace('<S t="0" d="51200" r="4" />', '<S t="0" d="51200" r="3" />', 1)
    with pytest.raises(ValueError):
        vc.parse_mpd(bad)


def test_parse_mpd_fixed_duration_template():
    xml = ('<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT12S"><Period>'
           '<AdaptationSet contentType="video"><SegmentTemplate timescale="1000" duration="4000" '
           'media="s$RepresentationID$-$Number$.m4s" initialization="i$RepresentationID$.m4s" startNumber="0"/>'
           '<Representation id="a" bandwidth="1000000"/></AdaptationSet></Period></MPD>')
    m = vc.parse_mpd(xml)
    assert m.n_segments == 3 and vc.segment_path(m.representations[0], 2) == "sa-2.m4s"


# ---- ABR ----------------------------------------------------------------------------------
def test_abr_starts_on_lowest_rung(manifest):
    assert vc.HarmonicABR().choose(manifest.representations).bandwidth == 250000


def test_abr_picks_highest_that_fits(manifest):
    abr = vc.HarmonicABR()
    for _ in range(3):
        abr.add_sample(10e6)
    assert abr.choose(manifest.representations).bandwidth == 5000000          # 0.8 x 10 = 8 Mbps
    abr = vc.HarmonicABR()
    for _ in range(3):
        abr.add_sample(1.5e6)                                                  # budget 1.2 Mbps
    assert abr.choose(manifest.representations).bandwidth == 1000000


def test_abr_harmonic_mean_reacts_to_one_bad_download(manifest):
    abr = vc.HarmonicABR()
    for s in (10e6, 10e6, 1e6):
        abr.add_sample(s)
    assert abr.estimate_bps() == pytest.approx(2.5e6)                         # 3 / (0.1 + 0.1 + 1) Mbps
    assert abr.choose(manifest.representations).bandwidth == 1000000          # not 2.5 Mbps


def test_abr_window_is_three(manifest):
    abr = vc.HarmonicABR()
    for s in (1e6, 10e6, 10e6, 10e6):
        abr.add_sample(s)
    assert abr.estimate_bps() == pytest.approx(10e6)                          # the 1 Mbps sample fell out


# ---- Playback buffer ----------------------------------------------------------------------
def test_startup_delay_is_time_of_first_segment():
    b = vc.PlaybackBuffer(t0=0.0, startup_buffer_s=4.0)
    b.add_segment(1.5, 4.0)
    assert b.playing and b.startup_delay == pytest.approx(1.5)


def test_no_playback_until_startup_buffer_reached():
    b = vc.PlaybackBuffer(0.0, startup_buffer_s=8.0)
    b.add_segment(1.0, 4.0)
    assert not b.playing and b.startup_delay is None
    b.add_segment(2.0, 4.0)
    assert b.playing and b.startup_delay == pytest.approx(2.0)


def test_stall_is_counted_and_timed():
    b = vc.PlaybackBuffer(0.0, startup_buffer_s=4.0)
    b.add_segment(1.0, 4.0)            # playing from t=1, buffer empties at t=5
    b.add_segment(7.0, 4.0)            # next segment arrives 2 s late
    assert b.stall_count == 1 and b.total_stall_s == pytest.approx(2.0)
    assert b.playing and b.level == pytest.approx(4.0)


def test_buffer_never_negative_and_no_stall_when_fed_in_time():
    b = vc.PlaybackBuffer(0.0, 4.0)
    for i in range(10):
        b.add_segment(1.0 + 3.5 * i, 4.0)       # a segment every 3.5 s, each 4 s long
    assert b.stall_count == 0 and b.level >= 0


def test_end_of_video_is_not_a_stall():
    b = vc.PlaybackBuffer(0.0, 4.0)
    b.add_segment(1.0, 4.0)
    b.mark_all_downloaded(1.0)
    b.advance(100.0)
    assert b.stall_count == 0 and b.ended and not b.playing


def test_last_segment_resumes_a_stall_even_below_resume_target():
    b = vc.PlaybackBuffer(0.0, startup_buffer_s=4.0, resume_buffer_s=8.0)
    b.add_segment(1.0, 4.0)
    b.advance(6.0)                              # empty since t=5 -> stall
    b.add_segment(6.0, 4.0)                     # 4 s < resume target 8 s: still stalled
    assert not b.playing
    b.mark_all_downloaded(6.0)                  # nothing more is coming: resume
    assert b.playing and b.stall_count == 1 and b.total_stall_s == pytest.approx(1.0)


# ---- Whole session (the offline "baseline trace") -----------------------------------------
def run(manifest, mbps, **kw):
    return vc.simulate_session(manifest, lambda t: mbps * 1e6, **kw)


def test_baseline_link_has_no_stalls_fast_startup_high_bitrate(manifest):
    rows, s = run(manifest, 13.3)
    assert s["stall_count"] == 0 and s["total_stall_s"] == 0
    assert s["startup_delay_s"] < 3.0
    assert max(r["bitrate_mbps"] for r in rows) == 5.0 and rows[-1]["bitrate_mbps"] in (2.5, 5.0)


def test_rows_follow_the_agreed_schema(manifest):
    rows, _ = run(manifest, 13.3)
    assert list(rows[0].keys()) == vc.ROW_COLUMNS and len(rows) == manifest.n_segments


def test_slow_link_picks_low_rungs(manifest):
    rows, s = run(manifest, 0.75)
    assert max(r["bitrate_mbps"] for r in rows) <= 0.5


def test_link_below_lowest_rung_stalls(manifest):
    _, s = run(manifest, 0.2)
    assert s["stall_count"] >= 1 and s["total_stall_s"] > 0


def test_row_stall_columns_sum_to_session_totals(manifest):
    rows, s = run(manifest, 0.2)
    assert sum(r["stall"] for r in rows) == s["stall_count"]
    assert sum(r["stall_s"] for r in rows) == pytest.approx(s["total_stall_s"], abs=1e-3)


def test_buffer_cap_limits_download_ahead():
    xml = MPD
    long_manifest = vc.Manifest(vc.parse_mpd(xml).representations, [4.0] * 30)
    rows, _ = run(long_manifest, 13.3, max_buffer_s=12.0)
    assert max(r["buffer_level_s"] for r in rows) <= 12.0 + 1e-6


def test_qoe_formula():
    assert vc.qoe_score(2.0, 1, 10.0, 3) == pytest.approx(2.0 - 0.3 - 0.5 - 0.3)