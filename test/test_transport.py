import unittest

from litex.gen import *
from litex.gen.fhdl import verilog

from litejesd204b.common import *
from litejesd204b.core.transport import TransportTX
from test.model.transport import samples_to_lanes


class TestTransport(unittest.TestCase):
    def test_transport_tx(self):
        nlanes = 4
        nconverters = 4

        transport_settings = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        physical_settings = JESD204BPhysicalSettings(l=nlanes, m=nconverters, n=16, np=16, sc=1*1e9)

        transport = TransportTX(transport_settings, physical_settings, 64)

        input_samples = [[j+i*256 for j in range(16)] for i in range(nconverters)]
        lanes = samples_to_lanes(samples_per_frame=1,
                                 nlanes=nlanes,
                                 nconverters=nconverters,
                                 nbits=16,
                                 samples=input_samples)

        dut_lanes = [[] for i in range(4)]

        def generator(dut):
            yield dut.sink.valid.eq(1)
            yield dut.source.ready.eq(1)
            for i in range(5):
                if i < 4:
                    for c in range(nconverters):
                        converter_data = getattr(dut.sink, "data"+str(c))
                        yield converter_data.eq((input_samples[c][4*i]   << 0)  |
                                                (input_samples[c][4*i+1] << 16) |
                                                (input_samples[c][4*i+2] << 32) |
                                                (input_samples[c][4*i+3] << 48))
                if i > 0:
                    for l in range(nlanes):
                        lane_data = (yield getattr(dut.source, "data"+str(l)))
                        for f in range(4):
                            frame = [(lane_data >> f*16)     & 0xff, 
                                     (lane_data >> (f*16+8)) & 0xff]
                            dut_lanes[l].append(frame)         
                yield

        run_simulation(transport, generator(transport))

        self.assertEqual(lanes, dut_lanes)
