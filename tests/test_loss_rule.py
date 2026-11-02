"""
Rule-attribution tests.
Check that every recovery:packet_lost qlog event says which rule declared the
packet lost ("packet", "time", "both", "pto" or "handshake"), and that
AIOQUIC_PACKET_THRESHOLD accepts an integer or "dynamic" / "dynamic_undo".
"""

import os
from unittest import TestCase, mock

from aioquic.quic.logger import QuicLogger
from aioquic.quic.rangeset import RangeSet
from aioquic.quic.recovery import (
    K_PACKET_THRESHOLD,
    QuicPacketRecovery,
    QuicPacketSpace,
)

from .utils import ack_eliciting_packet


def send_probe():
    pass


def make_recovery(**env) -> tuple[QuicPacketRecovery, QuicPacketSpace, object]:
    with mock.patch.dict(os.environ, env, clear=False):
        if not env:
            os.environ.pop("AIOQUIC_PACKET_THRESHOLD", None)
        trace = QuicLogger().start_trace(is_client=False, odcid=b"\x00" * 8)
        recovery = QuicPacketRecovery(
            congestion_control_algorithm="reno",
            initial_rtt=0.1,
            max_datagram_size=1280,
            peer_completed_address_validation=True,
            quic_logger=trace,
            send_probe=send_probe,
        )
    space = QuicPacketSpace(is_application_data=True)
    recovery.spaces = [QuicPacketSpace(), QuicPacketSpace(), space]
    recovery.handshake_confirmed = True
    return recovery, space, trace


def send(recovery, space, sent_times: dict[int, float]) -> None:
    for packet_number, sent_time in sent_times.items():
        recovery.on_packet_sent(
            packet=ack_eliciting_packet(
                packet_number=packet_number, sent_time=sent_time
            ),
            space=space,
        )


def lost_events(trace) -> dict[int, dict]:
    return {
        e["data"]["packet_number"]: e["data"]
        for e in trace.to_dict()["events"]
        if e["name"] == "recovery:packet_lost"
    }


class PacketThresholdEnvTest(TestCase):
    def test_unset_is_stock(self):
        recovery, _, _ = make_recovery()
        self.assertEqual(recovery._packet_threshold, K_PACKET_THRESHOLD)
        self.assertEqual(recovery._threshold_mode, "static")

    def test_integers(self):
        for k in (0, 5, 10, 20, 100):
            recovery, _, _ = make_recovery(AIOQUIC_PACKET_THRESHOLD=str(k))
            self.assertEqual(recovery._packet_threshold, k)
            self.assertEqual(recovery._threshold_mode, "static")

    def test_dynamic_strings_keep_stock_threshold(self):
        for mode in ("dynamic", "dynamic_undo"):
            recovery, _, _ = make_recovery(AIOQUIC_PACKET_THRESHOLD=mode)
            self.assertEqual(recovery._threshold_mode, mode)
            self.assertEqual(recovery._packet_threshold, K_PACKET_THRESHOLD)

    def test_rejects_garbage_and_negative(self):
        for bad in ("abc", "-1", "3.5"):
            with self.assertRaises(ValueError):
                make_recovery(AIOQUIC_PACKET_THRESHOLD=bad)


class LossRuleTest(TestCase):
    def test_packet_rule(self):
        # Packets 0..4 sent at the same moment; 4 is ACKed right away, so
        # packet 0 is 4 behind (>= K=3) but not old enough for the time rule.
        recovery, space, trace = make_recovery()
        send(recovery, space, {i: 0.0 for i in range(5)})
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(4, 5)]),
            ack_delay=0.0,
            now=0.1,
            space=space,
        )
        events = lost_events(trace)
        self.assertEqual(events[0]["rule"], "packet")
        self.assertTrue(events[0]["by_packet"])
        self.assertFalse(events[0]["by_time"])
        # largest_acked=4, K=3: packets 0 and 1 are lost, 2 and 3 are not.
        self.assertEqual(events[1]["rule"], "packet")
        self.assertEqual(sorted(events), [0, 1])

    def test_time_rule(self):
        # Packet 0 sent long before packet 1; ACK 1 only. Gap is 1 (< K) but
        # packet 0 is older than 9/8 * RTT.
        recovery, space, trace = make_recovery()
        send(recovery, space, {0: 0.0, 1: 1.0})
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(1, 2)]),
            ack_delay=0.0,
            now=1.1,
            space=space,
        )
        events = lost_events(trace)
        self.assertEqual(events[0]["rule"], "time")
        self.assertFalse(events[0]["by_packet"])
        self.assertTrue(events[0]["by_time"])

    def test_both_rules(self):
        # Packet 0 is both 4 behind and old.
        recovery, space, trace = make_recovery()
        send(recovery, space, {0: 0.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0})
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(4, 5)]),
            ack_delay=0.0,
            now=1.1,
            space=space,
        )
        events = lost_events(trace)
        self.assertEqual(events[0]["rule"], "both")
        self.assertTrue(events[0]["by_packet"])
        self.assertTrue(events[0]["by_time"])

    def test_high_threshold_suppresses_packet_rule(self):
        recovery, space, trace = make_recovery(AIOQUIC_PACKET_THRESHOLD="20")
        send(recovery, space, {i: 0.0 for i in range(5)})
        recovery.on_ack_received(
            ack_rangeset=RangeSet([range(4, 5)]),
            ack_delay=0.0,
            now=0.1,
            space=space,
        )
        self.assertEqual(lost_events(trace), {})

    def test_pto_rule(self):
        recovery, space, trace = make_recovery()
        send(recovery, space, {0: 1.0, 1: 1.1})
        recovery.on_loss_detection_timeout(now=2.0)
        events = lost_events(trace)
        self.assertEqual(events[0]["rule"], "pto")
        self.assertFalse(events[0]["by_packet"])
        self.assertFalse(events[0]["by_time"])

    def test_handshake_speed_up_is_not_pto(self):
        from aioquic import tls
        from aioquic.quic.packet import QuicPacketType
        from aioquic.quic.packet_builder import QuicSentPacket

        recovery, _, trace = make_recovery()
        initial = recovery.spaces[0]
        recovery.on_packet_sent(
            packet=QuicSentPacket(
                epoch=tls.Epoch.INITIAL,
                in_flight=True,
                is_ack_eliciting=True,
                is_crypto_packet=True,
                packet_number=0,
                packet_type=QuicPacketType.INITIAL,
                sent_bytes=1280,
                sent_time=0.0,
            ),
            space=initial,
        )
        recovery.reschedule_data(now=0.5, speed_up_handshake=True)
        self.assertEqual(lost_events(trace)[0]["rule"], "handshake")
