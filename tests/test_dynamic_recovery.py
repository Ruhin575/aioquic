"""Tests for adaptive packet-threshold recovery."""

import os
from unittest import TestCase, mock

from aioquic.quic.rangeset import RangeSet
from aioquic.quic.recovery import (
    K_DECAY,
    K_MAX,
    K_PACKET_THRESHOLD,
    QuicPacketRecovery,
    QuicPacketSpace,
)

from .utils import ack_eliciting_packet


def send_probe():
    pass


def make_dynamic_recovery(mode="dynamic"):
    with mock.patch.dict(os.environ, {"AIOQUIC_PACKET_THRESHOLD": mode}):
        recovery = QuicPacketRecovery(
            congestion_control_algorithm="reno",
            initial_rtt=0.1,
            max_datagram_size=1280,
            peer_completed_address_validation=True,
            send_probe=send_probe,
        )
    space = QuicPacketSpace(is_application_data=True)
    recovery.spaces = [QuicPacketSpace(), QuicPacketSpace(), space]
    recovery.handshake_confirmed = True
    return recovery, space


def send_packets(recovery, space, sent_times):
    for packet_number, sent_time in sent_times.items():
        recovery.on_packet_sent(
            packet=ack_eliciting_packet(
                packet_number=packet_number, sent_time=sent_time
            ),
            space=space,
        )


class DynamicRecoveryTest(TestCase):
    def test_dynamic_mode_starts_at_stock_threshold(self):
        for mode in ("dynamic", "dynamic_undo"):
            recovery, _ = make_dynamic_recovery(mode)
            self.assertEqual(recovery._threshold_mode, mode)
            self.assertEqual(recovery._k_adaptive, float(K_PACKET_THRESHOLD))

    def test_late_ack_of_packet_threshold_loss_adapts_k(self):
        recovery, space = make_dynamic_recovery()
        send_packets(recovery, space, {i: 0.0 for i in range(5)})

        # ACKing packet 4 makes packets 0 and 1 packet-threshold losses.
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(4, 5)]),
            ack_delay=0.0,
            now=0.1,
            space=space,
        )
        self.assertIn(0, recovery._recent_lost)
        self.assertEqual(recovery._k_adaptive, float(K_PACKET_THRESHOLD))

        # Packet 0 has already been removed from sent_packets. Its late ACK
        # must still be examined and should raise K to at least gap + 1.
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(0, 1)]),
            ack_delay=0.0,
            now=0.11,
            space=space,
        )
        self.assertGreaterEqual(recovery._k_adaptive, 5.0)
        self.assertNotIn(0, recovery._recent_lost)

    def test_adaptive_threshold_is_capped(self):
        recovery, _ = make_dynamic_recovery()
        recovery._adapt_k(K_MAX + 100)
        self.assertEqual(recovery._k_adaptive, float(K_MAX))

    def test_clean_rtt_sample_decays_threshold(self):
        recovery, space = make_dynamic_recovery()
        recovery._k_adaptive = 10.0
        send_packets(recovery, space, {0: 0.0})

        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(0, 1)]),
            ack_delay=0.0,
            now=0.1,
            space=space,
        )

        self.assertAlmostEqual(recovery._k_adaptive, 10.0 * K_DECAY)

    def test_late_ack_adaptation_prevents_decay_in_same_rtt_round(self):
        recovery, space = make_dynamic_recovery()
        recovery._k_adaptive = 10.0
        recovery._rtt_initialized = True
        recovery._rtt_smoothed = 0.1
        recovery._rtt_latest = 0.1
        recovery._rtt_min = 0.1
        recovery._rtt_variance = 0.05
        recovery._recent_lost[7] = (1.0, 0.9, 12)

        # A new, RTT-sampling ACK that also acknowledges the previously lost
        # packet should adapt K, rather than decaying it.
        send_packets(recovery, space, {8: 1.0})
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(7, 9)]),
            ack_delay=0.0,
            now=1.1,
            space=space,
        )
        self.assertEqual(recovery._k_adaptive, 13.0)
        self.assertTrue(recovery._k_adapted_this_round)

    def test_old_recent_losses_expire_after_two_smoothed_rtts(self):
        recovery, space = make_dynamic_recovery()
        recovery._rtt_smoothed = 0.1
        recovery._recent_lost[3] = (1.0, 0.9, 2)

        # An ACK for an unrelated packet still runs expiry before the
        # no-newly-acked early return.
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(100, 101)]),
            ack_delay=0.0,
            now=1.21,
            space=space,
        )
        self.assertNotIn(3, recovery._recent_lost)
