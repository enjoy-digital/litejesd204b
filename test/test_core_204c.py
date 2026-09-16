#
# This file is part of LiteJESD204B
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litex.soc.interconnect import stream

from litejesd204b.common import *
from litejesd204b.link_204c import link_204c_layout
from litejesd204b.core_204c import LiteJESD204CCoreTX, LiteJESD204CCoreRX

# Core-level TX -> RX loopback through fake PHYs: each PHY loops its TX blocks back to its RX side
# (block aligned, so BlockSync locks without slipping), the cores run in the "jesd" domain and the
# PHYs in their "jesd_phy{n}_tx/rx" domains, all at the same period so the elastic buffers of the
# clock domain crossings are exercised.


def jesd204c_settings(e=1):
    # 2 lanes / 4 converters (32-bit) to keep the simulation time reasonable.
    ps = JESD204BPhysicalSettings(l=2, m=4, n=16, np=16)
    ts = JESD204BTransportSettings(f=4, s=1, k=32, cs=0)
    return JESD204CSettings(ps, ts, did=0x5a, bid=0x5, e=e)


class FakePHY(Module):
    def __init__(self, n):
        self.n       = n
        self.sink    = stream.Endpoint(link_204c_layout())
        self.source  = stream.Endpoint(link_204c_layout())
        self.rx_slip = Signal()

        # # #

        self.comb += [
            self.sink.ready.eq(1),
            self.source.valid.eq(1),
            self.source.data.eq(self.sink.data),
            self.source.header.eq(self.sink.header),
        ]


class DUT(Module):
    def __init__(self, settings, converter_data_width=32):
        self.jref = Signal()

        self.clock_domains.cd_jesd = ClockDomain()
        self.phys = []
        for n in range(settings.phy.l):
            for direction in ["tx", "rx"]:
                self.clock_domains += ClockDomain(f"jesd_phy{n}_{direction}")
            phy = FakePHY(n)
            setattr(self.submodules, f"phy{n}", phy)
            self.phys.append(phy)

        self.submodules.tx = LiteJESD204CCoreTX(self.phys, settings, converter_data_width)
        self.submodules.rx = LiteJESD204CCoreRX(self.phys, settings, converter_data_width)
        self.tx.register_jref(self.jref)
        self.rx.register_jref(self.jref)

    def get_fragment_and_clocks(self, period=10):
        # Include the local clock domains of the elastic buffers (renamed by Migen when finalized).
        fragment = self.get_fragment()
        clocks   = {cd.name: period for cd in fragment.clock_domains}
        return fragment, clocks


class TestCore204C(unittest.TestCase):
    def core_loopback(self, e=1, converter_data_width=32):
        settings    = jesd204c_settings(e=e)
        lemc        = settings.lemc_cycles
        nconverters = settings.nconverters
        dut         = DUT(settings, converter_data_width)
        stats       = dict(tx_ready_at=None, rx_ready_at=None, stpl_errors=[])
        stats.update(tx_ramp=[], rx_ramp=[])

        def ramp(cycle):
            return [(cycle + (i << 16)) & (2**converter_data_width - 1) for i in range(nconverters)]

        def generator(dut):
            cycle = 0

            def step(n=1):
                nonlocal cycle
                for _ in range(n):
                    yield dut.jref.eq(int(cycle % (4*lemc) == 0)) # SYSREF at the LEMC period.
                    yield
                    cycle += 1

            # Reset (cores disabled), then enable in STPL mode.
            yield dut.tx.stpl_enable.eq(1)
            yield dut.rx.stpl_enable.eq(1)
            yield from step(8)
            yield dut.tx.enable.eq(1)
            yield dut.rx.enable.eq(1)

            # Wait for the TX and RX cores to be ready.
            for _ in range(32*lemc):
                yield from step()
                if stats["tx_ready_at"] is None and (yield dut.tx.ready):
                    stats["tx_ready_at"] = cycle
                if stats["rx_ready_at"] is None and (yield dut.rx.ready):
                    stats["rx_ready_at"] = cycle
                if stats["rx_ready_at"] is not None:
                    break
            if stats["rx_ready_at"] is None:
                return

            # STPL: the checker's error count must not move once the pattern flows through.
            yield from step(lemc)
            for _ in range(lemc):
                stats["stpl_errors"].append((yield dut.rx.stpl.errors))
                yield from step()

            # Ramp on the converters, captured on both sides for the latency check.
            yield dut.tx.stpl_enable.eq(0)
            yield dut.rx.stpl_enable.eq(0)
            for _ in range(2*lemc):
                for i, value in enumerate(ramp(cycle)):
                    yield getattr(dut.tx.sink, f"converter{i}").eq(value)
                stats["tx_ramp"].append(ramp(cycle))
                yield from step()
                rx_values = []
                for i in range(nconverters):
                    rx_values.append((yield getattr(dut.rx.source, f"converter{i}")))
                stats["rx_ramp"].append(rx_values)
            stats["cycles"] = cycle

        fragment, clocks = dut.get_fragment_and_clocks()
        run_simulation(fragment, {"jesd": generator(dut)}, clocks=clocks)
        return settings, stats

    def check_loopback(self, settings, stats):
        lemc = settings.lemc_cycles
        self.assertIsNotNone(stats["tx_ready_at"])
        self.assertIsNotNone(stats["rx_ready_at"])
        self.assertTrue(stats["tx_ready_at"] <= stats["rx_ready_at"])
        # STPL: no error accumulated while locked.
        self.assertEqual(len(set(stats["stpl_errors"])), 1)
        # Ramp: the RX converters follow the TX converters with a constant latency (the ramp data
        # is unique per cycle: the first match sets the latency, every later cycle must match).
        tx_ramp, rx_ramp = stats["tx_ramp"], stats["rx_ramp"]
        first = [c for c, v in enumerate(rx_ramp) if v in tx_ramp]
        self.assertTrue(len(first) >= 1)
        latency = first[0] - tx_ramp.index(rx_ramp[first[0]])
        self.assertTrue(0 < latency < lemc)
        for c in range(first[0], len(rx_ramp)):
            self.assertEqual(rx_ramp[c], tx_ramp[c - latency], f"cycle {c}, latency {latency}")
        self.assertTrue(len(rx_ramp) - first[0] >= lemc)

    def test_core_loopback(self):
        settings, stats = self.core_loopback(e=1)
        self.check_loopback(settings, stats)

    def test_core_loopback_e2(self):
        settings, stats = self.core_loopback(e=2)
        self.check_loopback(settings, stats)
