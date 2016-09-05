#!/usr/bin/env python3
import struct

from litex.gen import *

from litejesd204b.core.link import LiteJESD204BScrambler

from model.link import Scrambler


class TB(Module):
    def __init__(self):
        self.submodules.scrambler = LiteJESD204BScrambler(32)


def main_generator(dut):
    scrambler_model = Scrambler()
    yield tb.scrambler.enable.eq(1)
    yield tb.scrambler.data_in.eq(0)
    yield
    yield
    errors = 0
    dummy = scrambler_model.scramble(0, 32) # XXX understand why needed
    for i in range(512):
        reference = scrambler_model.scramble(0, 32)
        if (yield tb.scrambler.data_out) != reference:
            errors += 1
        yield
    print("errors: {:d}".format(errors))


if __name__ == "__main__":
    tb = TB()
    generators = {
        "sys" :   [main_generator(tb)]
    }
    clocks = {"sys": 10}
    run_simulation(tb, generators, clocks, vcd_name="sim.vcd")
