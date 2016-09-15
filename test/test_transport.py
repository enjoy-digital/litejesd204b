import unittest
from math import ceil

from litex.gen import *
from litex.gen.fhdl import verilog

from litejesd204b.common import *
from litejesd204b.core.transport import LiteJESD204BTransportTX
from test.model.transport import samples_to_lanes


class TestTransport(unittest.TestCase):
    def test_transport_tx(self, nlanes=4, nconverters=4, converter_data_width=64):
        transport_settings = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        physical_settings = JESD204BPhysicalSettings(l=nlanes, m=nconverters, n=16, np=16, sc=1*1e9)

        transport = LiteJESD204BTransportTX(transport_settings, physical_settings, converter_data_width)

        input_samples = [[j+i*256 for j in range(16)] for i in range(nconverters)]
        reference_lanes = samples_to_lanes(samples_per_frame=1,
                                           nlanes=nlanes,
                                           nconverters=nconverters,
                                           nbits=16,
                                           samples=input_samples)

        dut_lanes = [[] for i in range(4)]


        samples_per_frame = transport_settings.s        
        nibbles_per_word = ceil(physical_settings.np//4)
        octets_per_lane = samples_per_frame*nibbles_per_word//2
        lane_data_width = len(transport.source.data0)

        def generator(dut):
            yield dut.sink.valid.eq(1)
            yield dut.source.ready.eq(1)
            for i in range(5):
                if i < 4:
                    for c in range(nconverters):
                        converter_data = getattr(dut.sink, "data"+str(c))
                        for j in range(nconverters):
                            yield converter_data[16*j:16*(j+1)].eq(input_samples[c][4*i+j])
                if i > 0:
                    for l in range(nlanes):
                        lane_data = (yield getattr(dut.source, "data"+str(l)))
                        for f in range(lane_data_width//(octets_per_lane*8)):
                            frame = [(lane_data >> f*16+8*i) & 0xff for i in range(octets_per_lane)]
                            dut_lanes[l].append(frame)
                yield

        run_simulation(transport, generator(transport))

        self.assertEqual(reference_lanes, dut_lanes)
