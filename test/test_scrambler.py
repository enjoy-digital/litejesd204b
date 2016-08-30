#!/usr/bin/env python3
from litex.gen import *

from litejesd204b.core.link import LiteJESD204BScrambler

scrambler_reference = [
    0xf0002800,
    0xc00c2002,
    0x02ff802a,
    0x280c0c02,
    0x22f2f028,
    0xaaeacc2c,
    0x0e00fd7f,
    0xd8002400,
    0xe00ed002,
    0x82d54026,
    0x240e0efd,
    0xd2dad824,
    0x66c6eede,
    0xf37f5795,
    0xfc002a00,
    0x300c0802,
    0xc2f3a028,
    0x2af38c28,
    0x0afefc2a,
    0x88183c04,
    0xa4ea3153,
    0xd600d97f,
    0x380ef402,
    0x62db9024,
    0xa6db4edb,
    0xf6d4d6d9,
    0xb41c36fa,
    0x95b9b94b,
    0x0f7f7d95,
    0xcc0c2202,
    0xf2ffa82a,
    0xe8002c00
]


class TB(Module):
    def __init__(self):
        self.submodules.scrambler = LiteJESD204BScrambler(32)


def main_generator(dut):
    yield tb.scrambler.enable.eq(1)
    yield tb.scrambler.data_in.eq(0)
    yield
    yield
    errors = 0
    for i in range(32):
        if (yield tb.scrambler.data_out) != scrambler_reference[i]:
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
