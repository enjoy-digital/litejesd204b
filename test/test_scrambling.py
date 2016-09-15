import unittest

from litex.gen import *

from litejesd204b.core.link import Scrambler

from test.model.common import seed_to_data
from test.model.link import Scrambler as ScramblerModel


def scrambler_test():
    model = ScramblerModel()
    dut = Scrambler(32)
    dut.errors = 0
    def generator(dut):
        for i in range(512):
            yield dut.sink.valid.eq(1)
            yield dut.sink.data.eq(seed_to_data(i, True))
            yield dut.source.ready.eq(1)
            yield
            if i >= 1:
                reference = model.scramble(seed_to_data(i-1, True), 32)
                if (yield dut.source.data) != reference:
                    dut.errors += 1
    run_simulation(dut, generator(dut))

    return dut.errors


class TestScrambling(unittest.TestCase):
    def test_scrambler(self):
        errors = scrambler_test()
        self.assertEqual(errors, 0)
