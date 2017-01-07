from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litejesd204b.phy.line_coding import Encoder


class GTHChannelPLL(Module):
    min_vco_freq = 2.0e9
    max_vco_freq = 6.25e9
    n1_values = [4, 5]
    n2_values = [1, 2, 3, 4, 5]
    m_values = [1, 2]
    d_values = [1, 2, 4, 8, 16]

    def __init__(self, refclk, refclk_freq, linerate):
        self.refclk = refclk
        self.reset = Signal()
        self.lock = Signal()
        self.config = self.compute_config(refclk_freq, linerate)

    @staticmethod
    def compute_vco_freq(refclk_freq, n1, n2, m):
        return refclk_freq*(n1*n2)/m

    @staticmethod
    def compute_linerate(vco_freq, d):
        return vco_freq*2/d

    @classmethod
    def compute_config(cls, refclk_freq, linerate):
        for n1 in cls.n1_values:
            for n2 in cls.n2_values:
                for m in cls.m_values:
                    vco_freq = cls.compute_vco_freq(refclk_freq, n1, n2, m)
                    if (vco_freq >= cls.min_vco_freq and
                        vco_freq <= cls.max_vco_freq):
                        for d in cls.d_values:
                            if cls.compute_linerate(vco_freq, d) == linerate:
                                return {"n1": n1, "n2": n2, "m": m, "d": d}
        msg = "No config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
        raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))
