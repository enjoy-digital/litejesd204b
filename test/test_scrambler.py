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
    yield tb.scrambler.data_in.eq(0)
    yield tb.scrambler.enable.eq(1)
    yield
    yield tb.scrambler.data_in.eq(1)
    yield
    errors = 0
    for i in range(512):
        reference = scrambler_model.scramble(i, 32)
        if (yield tb.scrambler.data_out) != reference:
            errors += 1
        yield tb.scrambler.data_in.eq(i+2)
        yield
    print("errors: {:d}".format(errors))


if __name__ == "__main__":
    tb = TB()
    generators = {
        "sys" :   [main_generator(tb)]
    }
    clocks = {"sys": 10}
    run_simulation(tb, generators, clocks, vcd_name="sim.vcd")
