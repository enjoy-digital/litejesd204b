#!/usr/bin/env python3
import struct

from litex.gen import *

from litejesd204b.core.link import LiteJESD204BScrambler

from model.link import Scrambler

def swap32(i):
    return struct.unpack("<I", struct.pack(">I", i))[0]


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
    dummy = swap32(scrambler_model.getbits(32, 0)) # XXX understand why needed
    for i in range(512):
        reference = swap32(scrambler_model.getbits(32, 0))
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
