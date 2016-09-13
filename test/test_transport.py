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

        transport = TransportTX(transport_settings, physical_settings, 64, 64)


        input_samples = [[j+i*256 for j in range(16)] for i in range(nconverters)]
        lanes = samples_to_lanes(samples_per_frame=1,
                                 nlanes=nlanes,
                                 nconverters=nconverters,
                                 nbits=16,
                                 samples=input_samples)

        for i, converter in enumerate(input_samples):
            print("c"+str(i) + ":", end="")
            print(converter)

        for i, lane in enumerate(lanes):
            print("l"+str(i) + ":", end="")
            print(lane)

        def generator(dut):
            yield dut.sink.valid.eq(1)
            yield dut.source.ready.eq(1)
            for i in range(4):
                yield dut.sink.data0.eq((input_samples[0][4*i]   << 0)  |
                                        (input_samples[0][4*i+1] << 16)  |
                                        (input_samples[0][4*i+2] << 32) |
                                        (input_samples[0][4*i+3] << 48))
                yield dut.sink.data1.eq((input_samples[1][4*i]   << 0)  |
                                        (input_samples[1][4*i+1] << 16)  |
                                        (input_samples[1][4*i+2] << 32) |
                                        (input_samples[1][4*i+3] << 48))
                yield dut.sink.data2.eq((input_samples[2][4*i]   << 0)  |
                                        (input_samples[2][4*i+1] << 16)  |
                                        (input_samples[2][4*i+2] << 32) |
                                        (input_samples[2][4*i+3] << 48))
                yield dut.sink.data3.eq((input_samples[3][4*i]   << 0)  |
                                        (input_samples[3][4*i+1] << 16)  |
                                        (input_samples[3][4*i+2] << 32) |
                                        (input_samples[3][4*i+3] << 48))
                if i > 0:
                    print("----")
                    print("c0: %016x" %(yield dut.sink.data0))
                    print("c1: %016x" %(yield dut.sink.data1))
                    print("c2: %016x" %(yield dut.sink.data2))
                    print("c3: %016x" %(yield dut.sink.data3))
                    print("")
                    print("l0: %016x" %(yield dut.source.data0))
                    print("l1: %016x" %(yield dut.source.data1))
                    print("l2: %016x" %(yield dut.source.data2))
                    print("l3: %016x" %(yield dut.source.data3))            
                yield

        run_simulation(transport, generator(transport))

        #print(verilog.convert(transport))
