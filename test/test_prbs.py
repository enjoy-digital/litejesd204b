import unittest

from litex.gen import *

from litejesd204b.phy.prbs import PRBS7Generator
from litejesd204b.phy.prbs import PRBS15Generator
from litejesd204b.phy.prbs import PRBS31Generator

from test.model.phy import PRBS7Generator as PRBS7GeneratorModel
from test.model.phy import PRBS15Generator as PRBS15GeneratorModel
from test.model.phy import PRBS31Generator as PRBS31GeneratorModel


def prbs_test():
    duts = {
        "prbs7":  PRBS7Generator(8),
        "prbs15": PRBS15Generator(16),
        "prbs31": PRBS31Generator(32)
    }
    models = {
        "prbs7":  PRBS7GeneratorModel(),
        "prbs15": PRBS15GeneratorModel(),
        "prbs31": PRBS31GeneratorModel()
    }
    errors = 0
    for test in ["prbs7", "prbs15", "prbs31"]:
        dut = duts[test]
        dut.errors = 0
        model = models[test]
        def generator(dut, cycles):
            yield
            for i in range(cycles):
                if (yield dut.o) != model.getbits(len(dut.o)):
                    dut.errors += 1
                yield
        run_simulation(dut, generator(dut, 1024))
        errors += dut.errors

    return errors


class TestPRBS(unittest.TestCase):
    def test_prbs(self):
        errors = prbs_test()
        self.assertEqual(errors, 0)
