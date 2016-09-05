import unittest

from litejesd204b.common import *

from test.model.link import Scrambler, Descrambler
from test.model.link import scramble_lane, descramble_lane
from test.model.link import scramble_lanes, descramble_lanes
from test.model.link import LinkLayer

from test.model.transport import TransportLayer
from test.model.transport import short_test_pattern, long_test_pattern


class TestModel(unittest.TestCase):
    def test_transport_mapping(self):
        transport_settings = LiteJESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        transport = TransportLayer(transport_settings)
        nlanes = 4
        nconverters = 4

        # FIXME use random data
        input_samples = [[j+i*256 for j in range(8)] for i in range(nconverters)]
        lanes = transport.samples_to_lanes(nlanes, nconverters, 16, input_samples)
        # FIXME add assertion on lanes data
        output_samples = transport.lanes_to_samples(nlanes, nconverters, 16, lanes)

        self.assertEqual(input_samples, output_samples)

    def test_transport_short_test_pattern(self):
        samples = short_test_pattern(nconverters=4,
                                     samples_per_frame=2,
                                     repeats=8)
        # FIXME
        #for converter_samples in samples:
        #    print(converter_samples)

    def test_transport_long_test_pattern(self):
        samples = long_test_pattern(nconverters=4,
                                    nbits=16,
                                    samples_per_frame=2,
                                    frame_per_multiframe=8,
                                    repeats=1)
        # FIXME
        #for converter_samples in samples:
        #    print(converter_samples)

    def test_link_scrambling(self):
        scrambler = Scrambler()
        descrambler = Descrambler()
        errors = 0
        for i in range(128):
            # FIXME use random data
            if descrambler.descramble(scrambler.scramble(i, 32), 32) != i:
                errors += 1
        self.assertEqual(errors, 0)

    def test_link_lane_scrambling(self):
        # FIXME use random data
        input_lane = [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]]
        output_lane = descramble_lane(scramble_lane(input_lane))
        self.assertEqual(input_lane, output_lane)

    def test_link_alignment_characters_without_scrambling(self):
        link = LinkLayer(4, False)
        # FIXME use random data
        input_lanes = [
            [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]],
            [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
            [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
            [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]],
        ]
        output_lanes = link.insert_alignment_characters(input_lanes)
        output_lanes = link.remove_alignment_characters(input_lanes)
        self.assertEqual(input_lanes, output_lanes)

    def test_link_alignment_characters_with_scrambling(self):
        link = LinkLayer(4, True)
        # FIXME use random data
        input_lanes = [
            [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]],
            [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
            [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
            [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]],
        ]
        #output_lanes = scramble_lanes(input_lanes)
        output_lanes = link.insert_alignment_characters(input_lanes)
        output_lanes = link.remove_alignment_characters(input_lanes)
        #output_lanes = descramble_lanes(input_lanes)
        self.assertEqual(input_lanes, output_lanes)
