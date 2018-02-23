from operator import xor, add
from functools import reduce

from migen import *
from migen.genlib.cdc import MultiReg


class PRBSGenerator(Module):
    def __init__(self, n_out, n_state=23, taps=[17, 22]):
        self.o = Signal(n_out)

        # # #

        state = Signal(n_state, reset=1)
        curval = [state[i] for i in range(n_state)]
        curval += [0]*(n_out - n_state)
        for i in range(n_out):
            nv = reduce(xor, [curval[tap] for tap in taps])
            curval.insert(0, nv)
            curval.pop()

        self.sync += [
            state.eq(Cat(*curval[:n_state])),
            self.o.eq(Cat(*curval))
        ]


class PRBS7Generator(PRBSGenerator):
    def __init__(self, n_out):
        PRBSGenerator.__init__(self, n_out, n_state=7, taps=[5, 6])


class PRBS15Generator(PRBSGenerator):
    def __init__(self, n_out):
        PRBSGenerator.__init__(self, n_out, n_state=15, taps=[13, 14])


class PRBS31Generator(PRBSGenerator):
    def __init__(self, n_out):
        PRBSGenerator.__init__(self, n_out, n_state=31, taps=[27, 30])


class PRBSTX(Module):
    def __init__(self, width, reverse=False):
        self.config = Signal(2)
        self.i = Signal(width)
        self.o = Signal(width)

        # # #

        config = Signal(2)

        # generators
        self.specials += MultiReg(self.config, config)
        prbs7 = PRBS7Generator(width)
        prbs15 = PRBS15Generator(width)
        prbs31 = PRBS31Generator(width)
        self.submodules += prbs7, prbs15, prbs31

        # select
        prbs_data = Signal(width)
        self.comb += \
            If(config == 0b11,
                prbs_data.eq(prbs31.o)
            ).Elif(config == 0b10,
                prbs_data.eq(prbs15.o)
            ).Else(
                prbs_data.eq(prbs7.o)
            )

        # optional bits reversing
        if reverse:
            new_prbs_data = Signal(width)
            self.comb += new_prbs_data.eq(prbs_data[::-1])
            prbs_data = new_prbs_data

        # prbs / data mux
        self.comb += \
            If(config == 0,
                self.o.eq(self.i)
            ).Else(
                self.o.eq(prbs_data)
            )
