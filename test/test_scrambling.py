import unittest

from litex.gen import *

from litejesd204b.core.link import Scrambler

from test.model.common import seed_to_data
from test.model.link import Scrambler as ScramblerModel

def swap_bytes(data, n):
    return int.from_bytes(data.to_bytes(n, byteorder="little"), byteorder="big")

def scrambler_test():
    model = ScramblerModel()
    dut = Scrambler(32)
    dut.errors = 0
    def generator(dut):
        for i in range(512):
            yield dut.sink.valid.eq(1)
            yield dut.sink.data.eq(swap_bytes(seed_to_data(i, True), 4))
            yield dut.source.ready.eq(1)
            yield
            if i >= 1:
                reference = swap_bytes(model.scramble(seed_to_data(i-1, True), 32), 4)
                if (yield dut.source.data) != reference:
                    dut.errors += 1
    run_simulation(dut, generator(dut))

    return dut.errors


class TestScrambling(unittest.TestCase):
    def test_scrambler(self):
        errors = scrambler_test()
        self.assertEqual(errors, 0)
