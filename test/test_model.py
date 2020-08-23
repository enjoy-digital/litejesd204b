#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from litejesd204b.common import *

from test.model.common import seed_to_data

from test.model.transport import *
from test.model.link import *
from test.model.line_coding import *


class TestModel(unittest.TestCase):
    def transport_mapping_test(self, nlanes, nconverters, input_samples):
        lanes = samples_to_lanes(samples_per_frame=1,
                                 nlanes=nlanes,
                                 nconverters=nconverters,
                                 nbits=16,
                                 samples=input_samples)
        output_samples = lanes_to_samples(samples_per_frame=1,
                                          nlanes=nlanes,
                                          nconverters=nconverters,
                                          nbits=16,
                                          lanes=lanes)
        return output_samples

    def test_transport_mapping(self):
        nconverters = 4
        input_samples = [[j+i*256 for j in range(8)]
            for i in range(nconverters)]
        for nlanes in [1, 2, 4, 8]:
            output_samples = self.transport_mapping_test(nlanes,
                                                         nconverters,
                                                         input_samples)
            self.assertEqual(input_samples, output_samples)
        input_samples = [[seed_to_data(j+i)%(2**16) for j in range(1024)]
            for i in range(nconverters)]
        for nlanes in [1, 2, 4, 8]:
            output_samples = self.transport_mapping_test(nlanes,
                                                         nconverters,
                                                         input_samples)
            self.assertEqual(input_samples, output_samples)

    def test_transport_short_test_pattern(self):
        samples = short_test_pattern(nconverters=4,
                                     samples_per_frame=2,
                                     repeats=4)
        # cf section 5.1.6.2
        reference_samples = [
            [0, 1, 0, 1, 0, 1, 0, 1],
            [16, 17, 16, 17, 16, 17, 16, 17],
            [32, 33, 32, 33, 32, 33, 32, 33],
            [48, 49, 48, 49, 48, 49, 48, 49]
        ]
        self.assertEqual(samples, reference_samples)

    def test_transport_long_test_pattern(self):
        samples = long_test_pattern(nconverters=4,
                                    nbits=16,
                                    samples_per_frame=2,
                                    frame_per_multiframe=4,
                                    repeats=1)
        # cf section 5.1.6.3
        reference_samples = [
            [1, 1, 1, 2, 1<<15, 1<<15, 1<<15, 1<<15],
            [2, 2, 1, 2, 1<<15, 1<<15, 1<<15, 1<<15],
            [3, 3, 1, 2, 1<<15, 1<<15, 1<<15, 1<<15],
            [4, 4, 1, 2, 1<<15, 1<<15, 1<<15, 1<<15]
        ]
        self.assertEqual(samples, reference_samples)

    def test_link_scrambling(self):
        scrambler = Scrambler()
        descrambler = Descrambler()
        errors = 0
        for i in range(128):
            input_data = seed_to_data(i)
            scrambled_data = scrambler.scramble(input_data, 32)
            output_data = descrambler.descramble(scrambled_data, 32)
            if input_data != output_data:
                errors += 1
        self.assertEqual(errors, 0)

    def test_link_lane_scrambling(self):
        input_lanes = [
            [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]],
            [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
            [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
            [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]]
        ]
        output_lanes = descramble_lanes(scramble_lanes(input_lanes))
        self.assertEqual(input_lanes, output_lanes)

    def test_link_alignment_characters(self):
        input_lanes = [
            [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]],
            [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
            [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
            [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]]
        ]
        lanes = scramble_lanes(input_lanes)
        lanes = insert_alignment_characters(frames_per_multiframe=4,
                                            scrambled=True,
                                            lanes=lanes)
        output_lanes = replace_alignment_characters(frames_per_multiframe=4,
                                                   scrambled=True,
                                                   lanes=lanes)
        output_lanes = descramble_lanes(lanes)
        self.assertEqual(input_lanes, output_lanes)

    def test_line_coding(self):
        input_lanes = [
            [[0, 1], [0, 1], [0, 1], [0, 1], [0, 2], [0, 2], [0, 2], [0, 2]],
            [[1, 0], [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7]],
            [[2, 0], [2, 1], [2, 2], [2, 3], [2, 4], [2, 5], [2, 6], [2, 7]],
            [[3, 0], [3, 1], [3, 2], [3, 3], [3, 4], [3, 5], [3, 6], [3, 7]]
        ]
        encoded_lanes = encode_lanes(input_lanes)
        output_lanes = decode_lanes(encoded_lanes)
        self.assertEqual(input_lanes, output_lanes)

    def test_roundtrip(self, nlanes=4, nconverters=4):
        ps = JESD204BPhysicalSettings(l=nlanes, m=nconverters, n=16, np=16)
        ts = JESD204BTransportSettings(f=2, s=1, k=16, cs=1)
        jesd_settings = JESD204BSettings(ps, ts, did=0x5a, bid=0x5)

        transport = TransportLayer(jesd_settings)
        link = LinkLayer(16, True)

        # tx >>
        # # #
        tx_samples = [[seed_to_data(j)%(2**16) for j in range(4096)]
            for i in range(nconverters)]
        # transport
        tx_lanes = transport.encode(tx_samples)
        # link
        tx_data = link.encode(tx_lanes)
        # line_coding
        tx_encoded_data = encode_lanes(tx_data)

        # >> loopback >>
        # # #
        rx_encoded_data = tx_encoded_data

        # >> rx
        # # #
        # line_coding
        rx_data = decode_lanes(rx_encoded_data)
        # link
        rx_lanes = link.decode(rx_data)
        # transport
        rx_samples = transport.decode(rx_lanes)

        self.assertEqual(tx_samples, rx_samples)
