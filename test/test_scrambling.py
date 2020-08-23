#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import unittest

from migen import *

from litejesd204b.link import Scrambler, Descrambler

from test.model.common import swap_bytes, seed_to_data
from test.model.link import Scrambler as ScramblerModel
from test.model.link import Descrambler as DescramblerModel


class TestScrambling(unittest.TestCase):
    def scrambler_test(self):
        model = ScramblerModel()
        dut = Scrambler(32)
        dut.errors = 0

        def generator(dut):
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            for i in range(512):
                yield dut.sink.data.eq(swap_bytes(seed_to_data(i, True), 4))
                yield
                if i >= dut.latency:
                    reference = model.scramble(seed_to_data(i-dut.latency, True), 32)
                    reference = swap_bytes(reference, 4)
                    if (yield dut.source.data) != reference:
                        dut.errors += 1

        run_simulation(dut, generator(dut))
        return dut.errors

    def test_scrambler(self):
        errors = self.scrambler_test()
        self.assertEqual(errors, 0)

    def descrambler_test(self):
        model = DescramblerModel()
        dut = Descrambler(32)
        dut.errors = 0

        def generator(dut):
            yield dut.reset.eq(1)
            yield
            yield dut.reset.eq(0)
            for i in range(512):
                yield dut.sink.data.eq(swap_bytes(seed_to_data(i, False), 4))
                yield
                if i >= dut.latency:
                    reference = model.descramble(seed_to_data(i-dut.latency, False), 32)
                    reference = swap_bytes(reference, 4)
                    if (yield dut.source.data) != reference:
                        dut.errors += 1

        run_simulation(dut, generator(dut))
        return dut.errors

    def test_descrambler(self):
        errors = self.descrambler_test()
        self.assertEqual(errors, 0)

    def test_scrambling_loopback(self):
        class DUT(Module):
            def __init__(self):
                scrambler = Scrambler(32)
                descrambler = Descrambler(32)
                self.comb += descrambler.reset.eq(~scrambler.valid)
                self.submodules += scrambler, descrambler
                self.comb += descrambler.sink.eq(scrambler.source)
                self.sink, self.source = scrambler.sink, descrambler.source

        dut = DUT()
        dut.errors = 0

        datas = [seed_to_data(i, False) for i in range(512)]

        def generator(dut):
            for data in datas:
                yield dut.sink.data.eq(data)
                yield

        def checker(dut):
            yield
            yield
            yield
            for data in datas:
                if (yield dut.source.data) != data:
                    dut.errors += 1
                yield

        run_simulation(dut, [generator(dut), checker(dut)])
        self.assertEqual(dut.errors, 0)
