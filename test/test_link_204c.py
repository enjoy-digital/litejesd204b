#
# This file is part of LiteJESD204B
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import random
import unittest

from migen import *

from litejesd204b.common import *
from litejesd204b.link_204c import Scrambler64b66b, Descrambler64b66b, CRC12
from litejesd204b.link_204c import SyncWordTX, SyncWordRX, BlockSync
from litejesd204b.link_204c import LiteJESD204CLinkTX, LiteJESD204CLinkRX

from test.model.link_204c import Scrambler64b66bModel, Descrambler64b66bModel, CRC12Model
from test.model.link_204c import sync_word_crc12_mode, sync_word_to_headers
from test.model.link_204c import serialize_blocks, deserialize_blocks

# Note on simulation timing: generator writes (sig.eq) become active on the
# following cycle, so cycle 0 always runs with the reset input values (a
# "phantom" all-zero word for the datapath modules); the reference models are
# primed accordingly.


def jesd204c_settings(e=1):
    ps = JESD204BPhysicalSettings(l=4, m=8, n=16, np=16)
    ts = JESD204BTransportSettings(f=4, s=1, k=32, cs=0)
    return JESD204CSettings(ps, ts, did=0x5a, bid=0x5, e=e)


class TestScrambling64b66b(unittest.TestCase):
    def test_scrambler_vs_model(self):
        prng  = random.Random(42)
        model = Scrambler64b66bModel()
        model.scramble_word(0) # Phantom cycle 0.
        dut   = Scrambler64b66b()
        words = [prng.getrandbits(64) for _ in range(256)]
        refs  = [model.scramble_word(w) for w in words]
        outs  = []

        def generator(dut):
            for w in words:
                yield dut.sink.data.eq(w)
                yield # Word is now active; combinational output settled.
                outs.append((yield dut.source.data))

        run_simulation(dut, generator(dut))
        self.assertEqual(outs, refs)

    def test_descrambler_vs_model(self):
        prng  = random.Random(43)
        model = Descrambler64b66bModel()
        model.descramble_word(0) # Phantom cycle 0.
        dut   = Descrambler64b66b()
        words = [prng.getrandbits(64) for _ in range(256)]
        refs  = [model.descramble_word(w) for w in words]
        outs  = []

        def generator(dut):
            for w in words:
                yield dut.sink.data.eq(w)
                yield
                outs.append((yield dut.source.data))

        run_simulation(dut, generator(dut))
        self.assertEqual(outs, refs)

    def test_roundtrip_and_self_sync(self):
        # Descrambler with arbitrary initial state recovers after 58 bits (one word).
        prng        = random.Random(44)
        scrambler   = Scrambler64b66bModel()
        descrambler = Descrambler64b66bModel()
        descrambler.state = [prng.getrandbits(1) for _ in range(58)] # Arbitrary state.
        words     = [prng.getrandbits(64) for _ in range(64)]
        recovered = [descrambler.descramble_word(scrambler.scramble_word(w)) for w in words]
        self.assertEqual(recovered[1:], words[1:])


class TestCRC12(unittest.TestCase):
    def test_crc12_vs_model(self):
        # The phantom cycle 0 (data=0, init=0, state=0) leaves the state at 0.
        prng  = random.Random(45)
        model = CRC12Model()
        dut   = CRC12()
        n_mb  = 4
        words = [prng.getrandbits(64) for _ in range(32*n_mb)]
        # References: CRC over each complete multiblock.
        refs = []
        for n, w in enumerate(words):
            model.update_word(w, init=(n % 32 == 0))
            if n % 32 == 31:
                refs.append(model.state)

        outs = []

        def generator(dut):
            for n, w in enumerate(words):
                yield dut.data.eq(w)
                yield dut.init.eq(int(n % 32 == 0))
                yield # Word n active; value covers words <= n-1.
                if (n % 32 == 0) and (n > 0):
                    outs.append((yield dut.value)) # CRC of the previous multiblock.
            # Flush: one more cycle so the last word's edge occurs, then read.
            yield dut.data.eq(0)
            yield dut.init.eq(1)
            yield
            outs.append((yield dut.value))

        run_simulation(dut, generator(dut))
        self.assertEqual(outs, refs)


class TestSyncWord(unittest.TestCase):
    def test_sync_word_tx_vs_model(self):
        dut = SyncWordTX()
        crc, cmd, eoemb = 0xabc, 0, 1
        ref = sync_word_to_headers(sync_word_crc12_mode(crc, cmd, eoemb))
        headers = []

        def generator(dut):
            yield dut.crc12.eq(crc)
            yield dut.eoemb.eq(eoemb)
            yield dut.mb_start.eq(1)
            yield # mb_start active on cycle 1.
            yield dut.mb_start.eq(0)
            yield # Load edge: sync_word visible from cycle 2.
            for i in range(32):
                headers.append((yield dut.header))
                yield

        run_simulation(dut, generator(dut))
        self.assertEqual(headers, ref)

    def test_sync_word_rx_lock_and_crc(self):
        # Feed the headers of valid multiblocks; check EMB lock after 4 EoEMB and
        # the CRC-12 extraction.
        e   = 1
        dut = SyncWordRX(beats_per_emb=e*32)
        crcs = [0x123, 0x456, 0x789, 0xabc, 0xdef, 0x321, 0x654, 0x987]
        headers = []
        for crc in crcs:
            headers += sync_word_to_headers(sync_word_crc12_mode(crc, 0, 1))

        stats = dict(locked_at=None, crcs_rx=[])

        def generator(dut):
            yield dut.sh_lock.eq(1)
            for n, h in enumerate(headers):
                yield dut.header.eq(h)
                yield
                if (yield dut.emb_lock) and stats["locked_at"] is None:
                    stats["locked_at"] = n
                if (yield dut.valid_eomb):
                    stats["crcs_rx"].append((yield dut.crc12))

        run_simulation(dut, generator(dut))
        self.assertIsNotNone(stats["locked_at"])
        # Lock requires 4 EoEMB (1 to leave INIT + 3 counted in HUNT).
        self.assertLessEqual(stats["locked_at"], 5*32 + 2)
        # After lock, the received CRCs must match the transmitted ones.
        self.assertTrue(len(stats["crcs_rx"]) >= 3)
        for rx, tx in zip(stats["crcs_rx"], crcs[4:]):
            self.assertEqual(rx, tx)


class TestBlockSync(unittest.TestCase):
    def test_lock_and_slip(self):
        dut = BlockSync(slip_latency=4)
        stats = dict(slips=0, locked=False)

        def generator(dut):
            # Invalid headers: expect slips.
            yield dut.header.eq(0b00)
            for i in range(64):
                yield
                stats["slips"] += (yield dut.slip)
            # Valid headers: expect lock after 64.
            for i in range(80):
                yield dut.header.eq(0b01 if (i & 1) else 0b10)
                yield
            stats["locked"] = bool((yield dut.lock))

        run_simulation(dut, generator(dut))
        self.assertTrue(stats["slips"] >= 8)
        self.assertTrue(stats["locked"])


class TestLink204C(unittest.TestCase):
    def link_roundtrip(self, e=1, bit_offset=0, corrupt_beat=None):
        settings = jesd204c_settings(e=e)
        lemc     = settings.lemc_cycles

        prng     = random.Random(46)
        n_beats  = 16*lemc
        payload  = [prng.getrandbits(64) for _ in range(n_beats)]

        tx_blocks = []
        stats     = dict(rx_payload=[], frame_starts=[], crc_errors=0, ready_at=None)

        tx = LiteJESD204CLinkTX(settings)

        def tx_generator(dut):
            for n, w in enumerate(payload):
                yield dut.lemc_zero.eq(int(n % lemc == 0))
                yield dut.sink.data.eq(w)
                yield # Beat n active; outputs read on the next iteration.
                tx_blocks.append(((yield dut.source.data), (yield dut.source.header)))

        run_simulation(tx, tx_generator(tx))

        # Bit-level channel: serialize, optional corruption, arbitrary bit offset.
        bits = serialize_blocks(tx_blocks)
        if corrupt_beat is not None:
            # Flip one payload bit (beat corrupt_beat, payload bit 12).
            pos = 66*corrupt_beat + 2 + 12
            bits[pos] ^= 1
        rx_blocks = deserialize_blocks(bits, offset=bit_offset)

        rx = LiteJESD204CLinkRX(settings)

        def rx_generator(dut):
            yield dut.sh_lock.eq(1) # Channel is block-aligned by construction.
            for n, (data, header) in enumerate(rx_blocks):
                yield dut.sink.data.eq(data)
                yield dut.sink.header.eq(header)
                yield
                if (yield dut.ready) and stats["ready_at"] is None:
                    stats["ready_at"] = n
                if (yield dut.frame_start):
                    stats["frame_starts"].append(n)
                stats["crc_errors"] += (yield dut.crc_error)
                stats["rx_payload"].append((yield dut.source.data))

        run_simulation(rx, rx_generator(rx))
        return payload, tx_blocks, stats

    def test_link_roundtrip(self):
        settings = jesd204c_settings()
        lemc     = settings.lemc_cycles
        payload, tx_blocks, stats = self.link_roundtrip()
        self.assertIsNotNone(stats["ready_at"])
        self.assertTrue(len(stats["frame_starts"]) >= 2)
        self.assertEqual(stats["crc_errors"], 0)
        # Once locked, the RX payload must match the TX payload, starting on an
        # extended multiblock boundary at each frame_start.
        start  = stats["frame_starts"][2]
        rx_seq = stats["rx_payload"][start:start + 2*lemc]
        candidates = [k for k in range(0, len(payload) - 2*lemc + 1, lemc) if payload[k] == rx_seq[0]]
        self.assertTrue(len(candidates) >= 1)
        matched = any(rx_seq == payload[k:k + 2*lemc] for k in candidates)
        self.assertTrue(matched)

    def test_link_roundtrip_e2(self):
        payload, tx_blocks, stats = self.link_roundtrip(e=2)
        self.assertIsNotNone(stats["ready_at"])
        self.assertEqual(stats["crc_errors"], 0)
        self.assertTrue(len(stats["frame_starts"]) >= 2)

    def test_link_crc_error_detection(self):
        settings = jesd204c_settings()
        lemc     = settings.lemc_cycles
        # Corrupt one beat well after lock (beat in the 10th EMB).
        payload, tx_blocks, stats = self.link_roundtrip(corrupt_beat=10*lemc + 7)
        self.assertIsNotNone(stats["ready_at"])
        self.assertEqual(stats["crc_errors"], 1)


if __name__ == "__main__":
    unittest.main()
