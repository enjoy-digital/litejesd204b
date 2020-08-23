#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest
import random

from migen import *

from litejesd204b.link import link_layout
from litejesd204b.link import LiteJESD204BLinkTXDapath, LiteJESD204BLinkRXDapath

from test.model.common import Control
from test.model.link import scramble_lanes, descramble_lanes
from test.model.link import insert_alignment_characters, replace_alignment_characters

def flatten_lane(lane):
    flat_lane = []
    for frame in lane:
        flat_lane += frame
    return flat_lane


class TestLink(unittest.TestCase):
    def test_link_tx(self, nlanes=4, data_width=32):
        prng = random.Random(6)
        input_lane = [[prng.randrange(256), prng.randrange(256)]
            for _ in range(2048)]
        output_lanes = scramble_lanes([input_lane])
        output_lanes = insert_alignment_characters(frames_per_multiframe=4,
                                                   scrambled=True,
                                                   lanes=output_lanes)
        link = ResetInserter()(LiteJESD204BLinkTXDapath(data_width,
            octets_per_frame=2,
            frames_per_multiframe=4))
        link.output_lane = []

        octets_per_cycle = data_width//8

        def get_lane_data(lane, cycle):
            flat_lane = flatten_lane(lane)
            data = flat_lane[octets_per_cycle*cycle:octets_per_cycle*(cycle+1)]
            return int.from_bytes(data, byteorder='little') if data != [] else None

        def generator(dut):
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            for i in range(2048):
                sink_data = get_lane_data(input_lane, i)
                if sink_data is not None:
                    yield dut.sink.data.eq(sink_data)
                yield

        def checker(dut):
            for i in range(2 + dut.latency):
                yield
            for i in range(2048):
                source_data = (yield dut.source.data)
                source_ctrl = (yield dut.source.ctrl)
                data = list(source_data.to_bytes(octets_per_cycle,
                                                 byteorder='little'))
                for i in range(octets_per_cycle):
                    if source_ctrl & (1<<i):
                        data[i] = Control(data[i])
                dut.output_lane += data
                yield

        run_simulation(link, [generator(link), checker(link)])
        reference = flatten_lane(output_lanes[0])
        self.assertEqual(link.output_lane[:len(reference)], reference)


    def test_link_loopback(self, nlanes=4, data_width=32):
        prng = random.Random(6)
        input_lane = [[prng.randrange(256), prng.randrange(256)]
            for _ in range(2048)]
        output_lane = input_lane

        octets_per_cycle = data_width//8

        def get_lane_data(lane, cycle):
            flat_lane = flatten_lane(lane)
            data = flat_lane[octets_per_cycle*cycle:octets_per_cycle*(cycle+1)]
            return int.from_bytes(data, byteorder='little') if data != [] else None

        class DUT(Module):
            def __init__(self):
                tx = ResetInserter()(LiteJESD204BLinkTXDapath(data_width,
                    octets_per_frame=2,
                    frames_per_multiframe=4))
                self.submodules.tx = tx
                rx = ResetInserter()(LiteJESD204BLinkRXDapath(data_width,
                    octets_per_frame=2,
                    frames_per_multiframe=4))
                self.submodules.rx = rx
                self.comb += rx.sink.eq(tx.source)

        dut = DUT()
        dut.errors = 0

        def generator(dut):
            yield dut.tx.reset.eq(1)
            yield
            yield dut.tx.reset.eq(0)
            for i in range(2048):
                sink_data = get_lane_data(input_lane, i)
                if sink_data is not None:
                    yield dut.tx.sink.data.eq(sink_data)
                yield

        def checker(dut):
            yield dut.rx.reset.eq(1)
            yield
            yield
            yield dut.rx.reset.eq(0)
            yield
            yield
            for i in range(2048):
                source_data = get_lane_data(input_lane, i)
                if source_data is not None:
                    if (yield dut.rx.source.data) != source_data:
                        dut.errors += 1
                yield

        run_simulation(dut, [generator(dut), checker(dut)])
        self.assertEqual(dut.errors, 0)