import unittest
from math import ceil
import random

from litex.gen import *
from litex.soc.interconnect import stream

from litejesd204b.common import *
from litejesd204b.core.link import Scrambler, Framer, AlignInserter

from test.model.common import Control
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


class TestLink(unittest.TestCase):
    def test_link_tx(self, nlanes=4, data_width=32):
        prng = random.Random(6)
        input_lane = [[prng.randrange(256), prng.randrange(256)] for _ in range(2048)]
        output_lanes = scramble_lanes([input_lane])
        output_lanes = insert_alignment_characters(frames_per_multiframe=4, 
                                                   scrambled=True,
                                                   lanes=output_lanes) 
        link = LinkTXDatapath(data_width)
        link.output_lane = []

        octets_per_cycle = data_width//8

        def flatten_lane(lane):
            flat_lane = []
            for frame in lane:
                flat_lane += frame
            return flat_lane

        def get_lane_data(lane, cycle):
            flat_lane = flatten_lane(lane)
            data = flat_lane[octets_per_cycle*cycle:octets_per_cycle*(cycle+1)]
            return int.from_bytes(data, byteorder='little') if data != [] else None
         
        def generator(dut):
            yield dut.source.ready.eq(1)   
            for i in range(2048):
                # set sink data
                sink_data = get_lane_data(input_lane, i)
                if sink_data is not None:
                    yield dut.sink.valid.eq(1)
                    yield dut.sink.data.eq(sink_data)
                else:
                    yield dut.sink.valid.eq(0)
                # get source data
                if (yield dut.source.valid):
                    source_data = (yield dut.source.data)
                    source_ctrl = (yield dut.source.ctrl)
                    data = list(source_data.to_bytes(octets_per_cycle, byteorder='little'))
                    for i in range(octets_per_cycle):
                        if source_ctrl & (1<<i):
                            data[i] = Control(data[i])
                    dut.output_lane += data
                yield

        run_simulation(link, generator(link))
        self.assertEqual(link.output_lane, flatten_lane(output_lanes[0]))
