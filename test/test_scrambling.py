import unittest

from migen import *

from litejesd204b.link import Scrambler

from test.model.common import swap_bytes, seed_to_data
from test.model.link import Scrambler as ScramblerModel

def scrambler_test():
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


class TestScrambling(unittest.TestCase):
    def test_scrambler(self):
        errors = scrambler_test()
        self.assertEqual(errors, 0)
