import unittest
from math import ceil

from litex.gen import *
from litex.gen.fhdl import verilog
from litex.soc.interconnect import stream

from litejesd204b.common import *
from litejesd204b.core.link import Scrambler, Framer, AlignInserter

from test.model.link import scramble_lanes
from test.model.link import insert_alignment_characters


class LinkTXDatapath(Module):
    def __init__(self, data_width, octets_per_frame=2, frames_per_multiframe=4):
        self.sink = sink = stream.Endpoint([("data", data_width)])
        self.source = source = stream.Endpoint(link_layout(data_width))
        
        self.submodules.scrambler = Scrambler(data_width)
        self.submodules.framer = Framer(data_width, octets_per_frame, frames_per_multiframe)
        self.submodules.inserter = AlignInserter(data_width)
        self.comb += [
            self.sink.connect(self.scrambler.sink),
            self.scrambler.source.connect(self.framer.sink),
            self.framer.source.connect(self.inserter.sink),
            self.inserter.source.connect(source)
        ]


class TestTransport(unittest.TestCase):
    def test_link_tx(self, nlanes=4, lane_data_width=32):
        input_lane = [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]]
        lanes = scramble_lanes([input_lane])
        lanes = insert_alignment_characters(frames_per_multiframe=4, 
                                            scrambled=True,
                                            lanes=lanes)

        link = LinkTXDatapath(32)

        print(lanes)

        def generator(dut):
            yield dut.sink.valid.eq(1)
            yield dut.source.ready.eq(1)
            yield dut.sink.data.eq(0x00010001)
            yield
            yield dut.source.ready.eq(1)
            yield dut.sink.data.eq(0x00010001)
            yield
            yield dut.source.ready.eq(1)
            yield dut.sink.data.eq(0x00020002)
            yield
            yield dut.source.ready.eq(1)
            yield dut.sink.data.eq(0x00020002)
            for i in range(16):
                yield

        run_simulation(link, generator(link), vcd_name="sim.vcd")
