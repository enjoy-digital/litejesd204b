#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest
from math import ceil

from migen import *

from litejesd204b.common import *
from litejesd204b.transport import LiteJESD204BTransportTX, LiteJESD204BTransportRX
from litejesd204b.transport import LiteJESD204BSTPLGenerator, LiteJESD204BSTPLChecker

from test.model.transport import samples_to_lanes, lanes_to_samples


class TestTransport(unittest.TestCase):
    def transport_tx_test(self, nlanes, nconverters, converter_data_width):
        ps = JESD204BPhysicalSettings(l=nlanes, m=nconverters, n=16, np=16)
        ts = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        jesd_settings = JESD204BSettings(ps, ts, did=0x5a, bid=0x5)

        transport = LiteJESD204BTransportTX(jesd_settings,
                                            converter_data_width)

        input_samples = [[j+i*256 for j in range(16)] for i in range(nconverters)]
        reference_lanes = samples_to_lanes(samples_per_frame=1,
                                           nlanes=nlanes,
                                           nconverters=nconverters,
                                           nbits=16,
                                           samples=input_samples)

        output_lanes = [[] for i in range(nlanes)]

        octets_per_lane = jesd_settings.octets_per_lane
        lane_data_width = len(transport.source.lane0)

        def generator(dut):
            for i in range(4):
                for c in range(nconverters):
                    converter_data = getattr(dut.sink, "converter"+str(c))
                    for j in range(converter_data_width//jesd_settings.phy.n):
                        yield converter_data[16*j:16*(j+1)].eq(input_samples[c][4*i+j])
                yield

        def checker(dut):
            yield
            for i in range(4):
                for l in range(nlanes):
                    lane_data = (yield getattr(dut.source, "lane"+str(l)))
                    for f in range(lane_data_width//(octets_per_lane*8)):
                        frame = [(lane_data >> (f*8*octets_per_lane)+8*k) & 0xff
                            for k in range(octets_per_lane)]
                        output_lanes[l].append(frame)
                yield

        run_simulation(transport, [generator(transport), checker(transport)])
        return reference_lanes, output_lanes

    def test_transport_tx(self):
        for nlanes in [1, 2, 4, 8]:
            reference, output = self.transport_tx_test(nlanes, 4, 64)
            self.assertEqual(reference, output)

    def transport_rx_test(self, nlanes, nconverters, converter_data_width):
        ps = JESD204BPhysicalSettings(l=nlanes, m=nconverters, n=16, np=16)
        ts = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        jesd_settings = JESD204BSettings(ps, ts, did=0x5a, bid=0x5)

        transport = LiteJESD204BTransportRX(jesd_settings,
                                            converter_data_width)

        reference_samples = [[j+i*256 for j in range(16)] for i in range(nconverters)]
        input_lanes = samples_to_lanes(samples_per_frame=1,
                                       nlanes=nlanes,
                                       nconverters=nconverters,
                                       nbits=16,
                                       samples=reference_samples)

        octets_per_lane = jesd_settings.octets_per_lane
        lane_data_width = len(transport.sink.lane0)

        output_samples = [[] for i in range(nconverters)]

        def generator(dut):
            for i in range(4):
                for l in range(nlanes):
                    lane_data = getattr(dut.sink, "lane"+str(l))
                    for f in range(lane_data_width//(octets_per_lane*8)):
                        for k in range(octets_per_lane):
                            offset = (f*8*octets_per_lane)+8*k
                            yield lane_data[offset:offset+8].eq(input_lanes[l][4*i+f][k])
                yield

        def checker(dut):
            yield
            for i in range(4):
                for c in range(nconverters):
                    converter_data = (yield getattr(dut.source, "converter"+str(c)))
                    for j in range(converter_data_width//jesd_settings.phy.n):
                        output_samples[c].append((converter_data >> 16*j) & 0xffff)
                yield

        run_simulation(transport, [generator(transport), checker(transport)])
        return reference_samples, output_samples

    def test_transport_rx(self):
        for nlanes in [1, 2, 4, 8]:
            reference, output = self.transport_rx_test(nlanes, 4, 64)
            self.assertEqual(reference, output)

    def transport_loopback_test(self, nlanes, nconverters, converter_data_width):
        ps = JESD204BPhysicalSettings(l=nlanes, m=nconverters, n=16, np=16)
        ts = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        jesd_settings = JESD204BSettings(ps, ts, did=0x5a, bid=0x5)

        class DUT(Module):
            def __init__(self):
                transport_tx = LiteJESD204BTransportTX(jesd_settings, converter_data_width)
                transport_rx = LiteJESD204BTransportRX(jesd_settings, converter_data_width)
                self.comb += transport_rx.sink.eq(transport_tx.source)
                self.submodules += transport_tx, transport_rx
                self.sink, self.source = transport_tx.sink, transport_rx.source

        dut = DUT()
        input_samples  = [[j+i*256 for j in range(16)] for i in range(nconverters)]
        output_samples = [[] for i in range(nconverters)]

        def generator(dut):
            for i in range(4):
                for c in range(nconverters):
                    converter_data = getattr(dut.sink, "converter"+str(c))
                    for j in range(nconverters):
                        yield converter_data[16*j:16*(j+1)].eq(input_samples[c][4*i+j])
                yield

        def checker(dut):
            yield
            for i in range(4):
                for c in range(nconverters):
                    converter_data = (yield getattr(dut.source, "converter"+str(c)))
                    for j in range(nconverters):
                        sample = (converter_data >> 16*j) & 0xffff
                        output_samples[c].append(sample)
                yield

        run_simulation(dut, [generator(dut), checker(dut)])
        return input_samples, output_samples

    def test_transport_loopback(self):
        for nlanes in [1, 2, 4, 8]:
            reference, output = self.transport_loopback_test(nlanes, 4, 64)
            self.assertEqual(reference, output)

    def test_stpl_generator(self):
        ps = JESD204BPhysicalSettings(l=4, m=4, n=16, np=16)
        ts = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        jesd_settings = JESD204BSettings(ps, ts, did=0x5a, bid=0x5)

        stpl = LiteJESD204BSTPLGenerator(jesd_settings, 64, random=False)
        stpl.errors = 0

        def checker(dut):
            yield
            dut.errors += (yield dut.source.converter0) != 0x0000000000000000
            dut.errors += (yield dut.source.converter1) != 0x0100010001000100
            dut.errors += (yield dut.source.converter2) != 0x0200020002000200
            dut.errors += (yield dut.source.converter3) != 0x0300030003000300

        run_simulation(stpl, [checker(stpl)])
        self.assertEqual(stpl.errors, 0)

    def test_stpl_checker(self):
        ps = JESD204BPhysicalSettings(l=4, m=4, n=16, np=16)
        ts = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        jesd_settings = JESD204BSettings(ps, ts, did=0x5a, bid=0x5)

        stpl = LiteJESD204BSTPLChecker(jesd_settings, 64, random=False)
        stpl._errors = 0

        def generator(dut):
            yield dut.sink.converter0.eq(0x0000000000000000)
            yield dut.sink.converter1.eq(0x0100010001000100)
            yield dut.sink.converter2.eq(0x0200020002000200)
            yield dut.sink.converter3.eq(0x0300030003000300)
            yield
            yield dut.sink.converter0.eq(0x0000000000000000 ^ 0x0000000000000001)
            yield dut.sink.converter1.eq(0x0100010001000100 ^ 0x0000000000000010)
            yield dut.sink.converter2.eq(0x0200020002000200 ^ 0x0000000000000100)
            yield dut.sink.converter3.eq(0x0300030003000300 ^ 0x0000000000001000)
            yield
            stpl._errors = (yield stpl.errors)

        run_simulation(stpl, [generator(stpl)])
        self.assertEqual(stpl._errors, 1)
