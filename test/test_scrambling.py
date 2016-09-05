import unittest

from litex.gen import *

from litejesd204b.core.link import LiteJESD204BScrambler

from test.model.link import Scrambler


def scrambler_test():
    model = Scrambler()
    dut = LiteJESD204BScrambler(32)
    dut.errors = 0
    def generator(dut):
        yield dut.data_in.eq(0)
        yield dut.enable.eq(1)
        yield
        yield dut.data_in.eq(1)
        yield
        for i in range(512):
            reference = model.scramble(i, 32)
            if (yield dut.data_out) != reference:
                dut.errors += 1
            yield dut.data_in.eq(i+2)
            yield
    run_simulation(dut, generator(dut))

    return dut.errors


class TestScrambling(unittest.TestCase):
    def test_scrambler(self):
        errors = scrambler_test()
        self.assertEqual(errors, 0)
