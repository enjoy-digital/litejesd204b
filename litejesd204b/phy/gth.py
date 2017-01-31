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


class GTHQuadPLL(Module):
    min_vco_freq_qpll0 = 9.8e9
    max_vco_freq_qpll0 = 16.375e9
    min_vco_freq_qpll1 = 8e9
    max_vco_freq_qpll1 = 13e9
    n_values = [16, 20, 32, 40, 60, 64, 66, 75, 80, 84,
                90, 96, 100, 112, 120, 125, 150, 160]
    m_values = [1, 2, 3, 4]
    d_values = [1, 2, 4, 8, 16]

    def __init__(self, refclk, refclk_freq, linerate):
        self.clk = Signal()
        self.refclk = Signal()
        self.reset = Signal()
        self.lock = Signal()
        self.config = self.compute_config(refclk_freq, linerate)

        # # #

        # TODO:
        # - only set configuration to selected QPLL?
        # - simulate (instance is minimal, do we need others ports/attributes?)
        self.specials += \
            Instance("GTHE3_COMMON",
            	# common
            	p_TXOUT_DIV=self.config["d"],
            	i_GTGREFCLK0=refclk,

				# qpll0
                p_QPLL0_FBDIV=self.config["n"],
                p_QPLL0_REFCLK_DIV=self.config["m"],
                #o_QPLLDMONITOR0=,
                i_QPLL0CLKRSVD0=0,
                i_QPLL0CLKRSVD1=0,
                #o_QPLL0FBCLKLOST=,
                #o_QPLL0LOCK=,
                #o_QPLL0LOCK=,
                i_QPLL0LOCKDETCLK=ClockSignal(),
                i_QPLL0LOCKEN=1,
                o_QPLL0OUTCLK=self.clk if self.config["qpll"] == "qpll0" else
                              Signal(),
 				o_QPLL0OUTREFCLK=self.refclk if self.config["qpll"] == "qpll0" else
				                 Signal(),
				i_QPLL0PD=0,
				#o_QPLL0REFCLKLOST=,
				i_QPLL0REFCLKSEL=0b001,
				i_QPLL0RESET=self.reset,

				# qpll1
                p_QPLL1_FBDIV=self.config["n"],
                p_QPLL1_REFCLK_DIV=self.config["m"],
                #o_QPLLDMONITOR1=,
                i_QPLL1CLKRSVD0=0,
                i_QPLL1CLKRSVD1=0,
                #o_QPLL1FBCLKLOST=,
                #o_QPLL1LOCK=,
                #o_QPLL1LOCK=,
                i_QPLL1LOCKDETCLK=ClockSignal(),
                i_QPLL1LOCKEN=1,
                o_QPLL1OUTCLK=self.clk if self.config["qpll"] == "qpll1" else
                              Signal(),
 				o_QPLL1OUTREFCLK=self.refclk if self.config["qpll"] == "qpll1" else
				                 Signal(),
				i_QPLL1PD=0,
				#o_QPLL1REFCLKLOST=,
				i_QPLL1REFCLKSEL=0b001,
				i_QPLL1RESET=self.reset,
     		)

    @staticmethod
    def compute_vco_freq(refclk_freq, n, m):
        return refclk_freq*n/m

    @staticmethod
    def compute_linerate(vco_freq, d):
        return (vco_freq/2)*2/d

    @classmethod
    def compute_config(cls, refclk_freq, linerate):
        for n in cls.n_values:
            for m in cls.m_values:
                vco_freq = cls.compute_vco_freq(refclk_freq, n, m)
                qpll = None
                if (vco_freq >= cls.min_vco_freq_qpll0 and
                    vco_freq <= cls.max_vco_freq_qpll0):
                    qpll = "qpll0"
                if (vco_freq >= cls.min_vco_freq_qpll1 and
                    vco_freq <= cls.max_vco_freq_qpll1):
                    qpll = "qpll1"
                if qpll is not None:
                    for d in cls.d_values:
                        if cls.compute_linerate(vco_freq, d) == linerate:
                            return {"n": n, "m": m, "d": d, "qpll": qpll}
        msg = "No config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
        raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))
