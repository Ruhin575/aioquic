"""Tests for dynamic_undo: rolling back a congestion cut caused by losses
that later turn out to be spurious."""

import os
from unittest import TestCase, mock

from aioquic.quic.logger import QuicLogger
from aioquic.quic.rangeset import RangeSet
from aioquic.quic.recovery import (
    K_PACKET_THRESHOLD,
    MAX_UNDO_PENDING,
    QuicPacketRecovery,
    QuicPacketSpace,
)

from .utils import ack_eliciting_packet


def send_probe():
    pass


def make_recovery(mode="dynamic_undo", algorithm="reno", logger=False):
    quic_logger = (
        QuicLogger().start_trace(is_client=False, odcid=b"") if logger else None
    )
    with mock.patch.dict(os.environ, {"AIOQUIC_PACKET_THRESHOLD": mode}):
        recovery = QuicPacketRecovery(
            congestion_control_algorithm=algorithm,
            initial_rtt=0.1,
            max_datagram_size=1280,
            peer_completed_address_validation=True,
            send_probe=send_probe,
            quic_logger=quic_logger,
        )
    space = QuicPacketSpace(is_application_data=True)
    recovery.spaces = [QuicPacketSpace(), QuicPacketSpace(), space]
    recovery.handshake_confirmed = True
    return recovery, space, quic_logger


def send(recovery, space, sent_times):
    for packet_number, sent_time in sent_times.items():
        recovery.on_packet_sent(
            packet=ack_eliciting_packet(
                packet_number=packet_number, sent_time=sent_time
            ),
            space=space,
        )


def ack(recovery, space, start, stop, now):
    recovery.on_ack_received(
        ack_rangeset=RangeSet([range(start, stop)]),
        ack_delay=0.0,
        now=now,
        space=space,
    )


class DynamicUndoTest(TestCase):
    def test_all_spurious_losses_restore_window(self):
        for algorithm in ("reno", "cubic"):
            with self.subTest(algorithm=algorithm):
                recovery, space, _ = make_recovery(algorithm=algorithm)
                send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
                cc = recovery._cc

                ack(recovery, space, 2, 10, now=1.1)
                snapshot = recovery._undo_snapshot
                self.assertIsNotNone(snapshot)
                self.assertEqual(set(recovery._undo_pending), {0, 1})
                pre_cut = snapshot["congestion_window"]
                self.assertLess(cc.congestion_window, pre_cut)

                # Late ACK for both "lost" packets, with nothing newly acked.
                ack(recovery, space, 0, 2, now=1.12)
                self.assertEqual(cc.congestion_window, pre_cut)
                self.assertIsNone(recovery._undo_snapshot)
                self.assertEqual(recovery._undo_pending, {})

    def test_partial_late_acks_do_not_restore(self):
        recovery, space, _ = make_recovery()
        send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
        ack(recovery, space, 2, 10, now=1.1)
        cut_cwnd = recovery._cc.congestion_window

        ack(recovery, space, 0, 1, now=1.12)
        self.assertEqual(recovery._cc.congestion_window, cut_cwnd)
        self.assertEqual(set(recovery._undo_pending), {1})
        self.assertIsNotNone(recovery._undo_snapshot)

    def test_genuine_loss_abandons_undo(self):
        recovery, space, quic_logger = make_recovery(logger=True)
        send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
        ack(recovery, space, 2, 10, now=1.1)
        cut_cwnd = recovery._cc.congestion_window
        ack(recovery, space, 0, 1, now=1.12)

        # Packet 1 never arrives. An ACK more than 2 x smoothed RTT after the
        # loss abandons the episode, so the cut stands.
        send(recovery, space, {10: 1.4})
        ack(recovery, space, 10, 11, now=1.5)
        self.assertIsNone(recovery._undo_snapshot)
        self.assertEqual(recovery._undo_pending, {})
        self.assertLessEqual(recovery._cc.congestion_window, cut_cwnd + 1280)

        # A very late ACK for packet 1 no longer restores anything.
        window = recovery._cc.congestion_window
        ack(recovery, space, 0, 2, now=1.52)
        self.assertEqual(recovery._cc.congestion_window, window)

        events = [e["name"] for e in quic_logger.to_dict()["events"]]
        self.assertIn("recovery:undo_abandoned", events)
        self.assertNotIn("recovery:cwnd_restored", events)

    def test_restore_keeps_bytes_in_flight(self):
        recovery, space, _ = make_recovery()
        send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
        ack(recovery, space, 2, 10, now=1.1)
        send(recovery, space, {10: 1.11, 11: 1.111, 12: 1.112})
        in_flight = recovery._cc.bytes_in_flight
        self.assertEqual(in_flight, 3 * 1280)

        ack(recovery, space, 0, 2, now=1.12)
        self.assertEqual(recovery._cc.bytes_in_flight, in_flight)

    def test_restore_is_logged(self):
        recovery, space, quic_logger = make_recovery(logger=True)
        send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
        ack(recovery, space, 2, 10, now=1.1)
        ack(recovery, space, 0, 2, now=1.12)

        restored = [
            e
            for e in quic_logger.to_dict()["events"]
            if e["name"] == "recovery:cwnd_restored"
        ]
        self.assertEqual(len(restored), 1)
        self.assertLess(
            restored[0]["data"]["old_cwnd"], restored[0]["data"]["new_cwnd"]
        )

    def test_other_modes_never_snapshot(self):
        for mode in ("dynamic", "3", ""):
            with self.subTest(mode=mode):
                recovery, space, _ = make_recovery(mode=mode)
                send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
                ack(recovery, space, 2, 10, now=1.1)
                self.assertIsNone(recovery._undo_snapshot)
                self.assertEqual(recovery._undo_pending, {})

    def test_undo_mode_restores_without_adapting_k(self):
        # The "undo" ablation runs the congestion-undo snapshot with K pinned
        # at the stock threshold. The window is restored on all-spurious
        # losses, exactly as in dynamic_undo, but the adaptive threshold never
        # engages: no packet-rule loss is recorded for adaptation and K stays
        # at K_PACKET_THRESHOLD throughout. Checked under both controllers.
        for algorithm in ("reno", "cubic"):
            with self.subTest(algorithm=algorithm):
                recovery, space, _ = make_recovery(mode="undo", algorithm=algorithm)
                send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
                cc = recovery._cc

                ack(recovery, space, 2, 10, now=1.1)
                snapshot = recovery._undo_snapshot
                self.assertIsNotNone(snapshot)
                self.assertEqual(set(recovery._undo_pending), {0, 1})
                pre_cut = snapshot["congestion_window"]
                self.assertLess(cc.congestion_window, pre_cut)

                # The adaptive machinery never engaged: losses were not recorded
                # for adaptation and K is still the stock threshold.
                self.assertEqual(recovery._recent_lost, {})
                self.assertEqual(recovery._k_adaptive, float(K_PACKET_THRESHOLD))

                # Late ACK for both "lost" packets restores the window, as in
                # dynamic_undo.
                ack(recovery, space, 0, 2, now=1.12)
                self.assertEqual(cc.congestion_window, pre_cut)
                self.assertIsNone(recovery._undo_snapshot)
                self.assertEqual(recovery._undo_pending, {})

                # Still no adaptation after the restore.
                self.assertEqual(recovery._recent_lost, {})
                self.assertEqual(recovery._k_adaptive, float(K_PACKET_THRESHOLD))

    def test_undo_mode_pins_k_where_dynamic_undo_would_raise_it(self):
        # The same spurious-loss sequence in both modes: dynamic_undo raises
        # the adaptive threshold off the late ACKs, the undo-only ablation
        # leaves it pinned at the stock threshold. This isolates the undo
        # mechanism from threshold adaptation.
        def final_k(mode):
            recovery, space, _ = make_recovery(mode=mode)
            send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
            ack(recovery, space, 2, 10, now=1.1)   # declares 0, 1 lost by packet rule
            ack(recovery, space, 0, 2, now=1.12)   # late ACK proves them spurious
            return recovery._k_adaptive

        self.assertGreater(final_k("dynamic_undo"), float(K_PACKET_THRESHOLD))
        self.assertEqual(final_k("undo"), float(K_PACKET_THRESHOLD))

    def test_undo_mode_abandons_on_genuine_loss(self):
        # Safety under the ablation: a loss that is never late-ACKed abandons
        # the episode so the cut stands, with K still pinned and no adaptation
        # events logged.
        recovery, space, quic_logger = make_recovery(mode="undo", logger=True)
        send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
        ack(recovery, space, 2, 10, now=1.1)
        cut_cwnd = recovery._cc.congestion_window
        ack(recovery, space, 0, 1, now=1.12)  # packet 0 comes late; packet 1 never arrives

        # An ACK more than 2 x smoothed RTT after the loss abandons the episode.
        send(recovery, space, {10: 1.4})
        ack(recovery, space, 10, 11, now=1.5)
        self.assertIsNone(recovery._undo_snapshot)
        self.assertEqual(recovery._undo_pending, {})
        self.assertLessEqual(recovery._cc.congestion_window, cut_cwnd + 1280)
        self.assertEqual(recovery._k_adaptive, float(K_PACKET_THRESHOLD))

        events = [e["name"] for e in quic_logger.to_dict()["events"]]
        self.assertIn("recovery:undo_abandoned", events)
        self.assertNotIn("recovery:cwnd_restored", events)
        self.assertNotIn("recovery:k_adapted", events)
        self.assertNotIn("recovery:k_decayed", events)


    def test_loss_within_open_episode_must_also_be_spurious(self):
        recovery, space, _ = make_recovery()
        send(recovery, space, {pn: 1.0 + pn * 0.0001 for pn in range(10)})
        ack(recovery, space, 2, 10, now=1.1)
        pre_cut = recovery._undo_snapshot["congestion_window"]

        # A second burst inside the same episode: 10 and 11 lost after 12..19
        # are acknowledged.
        send(recovery, space, {pn: 1.105 + pn * 0.0001 for pn in range(10, 20)})
        ack(recovery, space, 12, 20, now=1.2)
        self.assertEqual(set(recovery._undo_pending), {0, 1, 10, 11})

        ack(recovery, space, 0, 2, now=1.21)
        self.assertIsNotNone(recovery._undo_snapshot)
        ack(recovery, space, 10, 12, now=1.22)
        self.assertIsNone(recovery._undo_snapshot)
        self.assertEqual(recovery._cc.congestion_window, pre_cut)

    def test_too_many_pending_losses_abandon(self):
        recovery, space, _ = make_recovery()
        count = MAX_UNDO_PENDING + 20
        send(recovery, space, {pn: 1.0 + pn * 0.00001 for pn in range(count)})
        ack(recovery, space, count - 1, count, now=1.1)
        self.assertIsNone(recovery._undo_snapshot)
        self.assertEqual(recovery._undo_pending, {})

    def test_k_decay_is_logged(self):
        recovery, space, quic_logger = make_recovery(mode="dynamic", logger=True)
        recovery._k_adaptive = 10.0
        send(recovery, space, {0: 1.0})
        ack(recovery, space, 0, 1, now=1.1)

        decayed = [
            e
            for e in quic_logger.to_dict()["events"]
            if e["name"] == "recovery:k_decayed"
        ]
        self.assertEqual(len(decayed), 1)
        self.assertEqual(decayed[0]["data"]["old_k"], 10.0)
        self.assertAlmostEqual(decayed[0]["data"]["new_k"], 9.0)
