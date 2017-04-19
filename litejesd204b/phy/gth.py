from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer
from litex.soc.cores.code_8b10b import Encoder

from litejesd204b.phy.gth_init import GTHInit


class GTHChannelPLL(Module):
    def __init__(self, refclk, refclk_freq, linerate):
        self.refclk = refclk
        self.reset = Signal()
        self.lock = Signal()
        self.config = self.compute_config(refclk_freq, linerate)

    @staticmethod
    def compute_config(refclk_freq, linerate):
        for n1 in 4, 5:
            for n2 in 1, 2, 3, 4, 5:
                for m in 1, 2:
                    vco_freq = refclk_freq*(n1*n2)/m
                    if 2.0e9 <= vco_freq <= 6.25e9:
                        for d in 1, 2, 4, 8, 16:
                            current_linerate = vco_freq*2/d
                            if current_linerate == linerate:
                                return {"n1": n1, "n2": n2, "m": m, "d": d,
                                        "vco_freq": vco_freq,
                                        "clkin": refclk_freq,
                                        "linerate": linerate}
        msg = "No config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
        raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))

    def __repr__(self):
        r = """
GTHChannelPLL
==============
  overview:
  ---------
       +--------------------------------------------------+
       |                                                  |
       |   +-----+  +---------------------------+ +-----+ |
       |   |     |  | Phase Frequency Detector  | |     | |
CLKIN +----> /M  +-->       Charge Pump         +-> VCO +---> CLKOUT
       |   |     |  |       Loop Filter         | |     | |
       |   +-----+  +---------------------------+ +--+--+ |
       |              ^                              |    |
       |              |    +-------+    +-------+    |    |
       |              +----+  /N2  <----+  /N1  <----+    |
       |                   +-------+    +-------+         |
       +--------------------------------------------------+
                            +-------+
                   CLKOUT +->  2/D  +-> LINERATE
                            +-------+
  config:
  -------
    CLKIN    = {clkin}MHz
    CLKOUT   = CLKIN x (N1 x N2) / M = {clkin}MHz x ({n1} x {n2}) / {m}
             = {vco_freq}GHz
    LINERATE = CLKOUT x 2 / D = {vco_freq}GHz x 2 / {d}
             = {linerate}GHz
""".format(clkin=self.config["clkin"]/1e6,
           n1=self.config["n1"],
           n2=self.config["n2"],
           m=self.config["m"],
           vco_freq=self.config["vco_freq"]/1e9,
           d=self.config["d"],
           linerate=self.config["linerate"]/1e9)
        return r


class GTHQuadPLL(Module):
    def __init__(self, refclk, refclk_freq, linerate):
        self.clk = Signal()
        self.refclk = Signal()
        self.reset = Signal()
        self.lock = Signal()
        self.config = self.compute_config(refclk_freq, linerate)

        # # #

        self.specials += \
            Instance("GTHE3_COMMON",
                # common
                i_GTREFCLK00=refclk,
                i_GTREFCLK01=refclk,
                i_QPLLRSVD1=0,
                i_QPLLRSVD2=0,
                i_QPLLRSVD3=0,
                i_QPLLRSVD4=0,
                i_BGBYPASSB=1,
                i_BGMONITORENB=1,
                i_BGPDB=1,
                i_BGRCALOVRD=0b11111,
                i_BGRCALOVRDENB=0b1,
                i_RCALENB=1,

                # qpll0
                p_QPLL0_FBDIV=self.config["n"],
                p_QPLL0_REFCLK_DIV=self.config["m"],
                i_QPLL0CLKRSVD0=0,
                i_QPLL0CLKRSVD1=0,
                i_QPLL0LOCKDETCLK=ClockSignal(),
                i_QPLL0LOCKEN=1,
                o_QPLL0LOCK=self.lock if self.config["qpll"] == "qpll0" else
                            Signal(),
                o_QPLL0OUTCLK=self.clk if self.config["qpll"] == "qpll0" else
                              Signal(),
                o_QPLL0OUTREFCLK=self.refclk if self.config["qpll"] == "qpll0" else
                                 Signal(),
                i_QPLL0PD=0 if self.config["qpll"] == "qpll0" else 1,
                i_QPLL0REFCLKSEL=0b001,
                i_QPLL0RESET=self.reset,

                # qpll1
                p_QPLL1_FBDIV=self.config["n"],
                p_QPLL1_REFCLK_DIV=self.config["m"],
                i_QPLL1CLKRSVD0=0,
                i_QPLL1CLKRSVD1=0,
                i_QPLL1LOCKDETCLK=ClockSignal(),
                i_QPLL1LOCKEN=1,
                o_QPLL1LOCK=self.lock if self.config["qpll"] == "qpll1" else
                            Signal(),
                o_QPLL1OUTCLK=self.clk if self.config["qpll"] == "qpll1" else
                              Signal(),
                o_QPLL1OUTREFCLK=self.refclk if self.config["qpll"] == "qpll1" else
                                 Signal(),
                i_QPLL1PD=0 if self.config["qpll"] == "qpll1" else 1,
                i_QPLL1REFCLKSEL=0b001,
                i_QPLL1RESET=self.reset,
             )

    @staticmethod
    def compute_config(refclk_freq, linerate):
        for n in [16, 20, 32, 40, 60, 64, 66, 75, 80, 84,
                  90, 96, 100, 112, 120, 125, 150, 160]:
            for m in 1, 2, 3, 4:
                vco_freq = refclk_freq*n/m
                if 9.8e9 <= vco_freq <= 16.375e9:
                    qpll = "qpll0"
                elif 8e9 <= vco_freq <= 13e9:
                    qpll = "qpll1"
                else:
                    qpll = None
                if qpll is not None:
                    for d in 1, 2, 4, 8, 16:
                        current_linerate = (vco_freq/2)*2/d
                        if current_linerate == linerate:
                            return {"n": n, "m": m, "d": d,
                                    "vco_freq": vco_freq,
                                    "qpll": qpll,
                                    "clkin": refclk_freq,
                                    "clkout": vco_freq/2,
                                    "linerate": linerate}
        msg = "No config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
        raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))

    def __repr__(self):
        r = """
GTXQuadPLL
===========
  overview:
  ---------
       +-------------------------------------------------------------++
       |                                          +------------+      |
       |   +-----+  +---------------------------+ |   QPLL0    | +--+ |
       |   |     |  | Phase Frequency Detector  +->    VCO     | |  | |
CLKIN +----> /M  +-->       Charge Pump         | +------------+->/2+--> CLKOUT
       |   |     |  |       Loop Filter         +->   QPLL1    | |  | |
       |   +-----+  +---------------------------+ |    VCO     | +--+ |
       |              ^                           +-----+------+      |
       |              |        +-------+                |             |
       |              +--------+  /N   <----------------+             |
       |                       +-------+                              |
       +--------------------------------------------------------------+
                               +-------+
                      CLKOUT +->  2/D  +-> LINERATE
                               +-------+
  config:
  -------
    CLKIN    = {clkin}MHz
    CLKOUT   = CLKIN x N / (2 x M) = {clkin}MHz x {n} / (2 x {m})
             = {clkout}GHz
    VCO      = {vco_freq}GHz ({qpll})
    LINERATE = CLKOUT x 2 / D = {clkout}GHz x 2 / {d}
             = {linerate}GHz
""".format(clkin=self.config["clkin"]/1e6,
           n=self.config["n"],
           m=self.config["m"],
           clkout=self.config["clkout"]/1e9,
           vco_freq=self.config["vco_freq"]/1e9,
           qpll=self.config["qpll"].upper(),
           d=self.config["d"],
           linerate=self.config["linerate"]/1e9)
        return r


class GTHTransmitter(Module):
    def __init__(self, pll, tx_pads, sys_clk_freq):
        self.prbs_config = Signal(4)
        self.produce_square_wave = Signal()

        # # #

        use_cpll = isinstance(pll, GTHChannelPLL)
        use_qpll0 = isinstance(pll, GTHQuadPLL) and pll.config["qpll"] == "qpll0"
        use_qpll1 = isinstance(pll, GTHQuadPLL) and pll.config["qpll"] == "qpll1"

        self.submodules.init = GTHInit(sys_clk_freq, False)
        self.comb += [
            self.init.plllock.eq(pll.lock),
            pll.reset.eq(self.init.pllreset)
        ]

        nwords = 40//10

        txoutclk = Signal()
        txdata = Signal(40)
        self.specials += \
            Instance("GTHE3_CHANNEL",
                # Reset modes
                i_GTRESETSEL=0,
                i_RESETOVRD=0,

                # PMA Attributes
                p_PMA_RSV1=0xf800,
                p_RX_BIAS_CFG0=0x0AB4,
                p_RX_CM_TRIM=0b1010,
                p_RX_CLK25_DIV=5,
                p_TX_CLK25_DIV=5,

                # Power-Down Attributes
                p_PD_TRANS_TIME_FROM_P2=0x3c,
                p_PD_TRANS_TIME_NONE_P2=0x19,
                p_PD_TRANS_TIME_TO_P2=0x64,

                # CPLL
                p_CPLL_CFG0=0x67f8,
                p_CPLL_CFG1=0xa4ac,
                p_CPLL_CFG2=0xf007,
                p_CPLL_CFG3=0x0000,
                p_CPLL_FBDIV=1 if (use_qpll0 | use_qpll1) else pll.config["n2"],
                p_CPLL_FBDIV_45=4 if (use_qpll0 | use_qpll1) else pll.config["n1"],
                p_CPLL_REFCLK_DIV=1 if (use_qpll0 | use_qpll1) else pll.config["m"],
                p_RXOUT_DIV=pll.config["d"],
                p_TXOUT_DIV=pll.config["d"],
                i_CPLLRESET=0,
                i_CPLLPD=0 if (use_qpll0 | use_qpll1) else pll.reset,
                o_CPLLLOCK=Signal() if (use_qpll0 | use_qpll1) else pll.lock,
                i_CPLLLOCKEN=1,
                i_CPLLREFCLKSEL=0b001,
                i_TSTIN=2**20-1,
                i_GTREFCLK0=0 if (use_qpll0 | use_qpll1) else pll.refclk,

                # QPLL
                i_QPLL0CLK=0 if (use_cpll | use_qpll1) else pll.clk,
                i_QPLL0REFCLK=0 if (use_cpll | use_qpll1) else pll.refclk,
                i_QPLL1CLK=0 if (use_cpll | use_qpll0) else pll.clk,
                i_QPLL1REFCLK=0 if (use_cpll | use_qpll0) else pll.refclk,

                # TX clock
                p_TXBUF_EN="FALSE",
                p_TX_XCLK_SEL="TXUSR",
                o_TXOUTCLK=txoutclk,
                i_TXSYSCLKSEL=0b00 if use_cpll else 0b10 if use_qpll0 else 0b11,
                i_TXPLLCLKSEL=0b00 if use_cpll else 0b11 if use_qpll0 else 0b10,
                i_TXOUTCLKSEL=0b11,

                # disable RX
                i_RXPD=0b11,

                # Startup/Reset
                i_GTTXRESET=self.init.gtXxreset,
                o_TXRESETDONE=self.init.Xxresetdone,
                i_TXDLYSRESET=self.init.Xxdlysreset,
                o_TXDLYSRESETDONE=self.init.Xxdlysresetdone,
                o_TXPHALIGNDONE=self.init.Xxphaligndone,
                i_TXUSERRDY=self.init.Xxuserrdy,

                # PRBS
                i_TXPRBSSEL=self.prbs_config[0:3],
                i_TXPRBSFORCEERR=self.prbs_config[3],

                # TX data
                p_TX_DATA_WIDTH=40,
                p_TX_INT_DATAWIDTH=1,
                i_TXCTRL0=Cat(*[txdata[10*i+8] for i in range(nwords)]),
                i_TXCTRL1=Cat(*[txdata[10*i+9] for i in range(nwords)]),
                i_TXDATA=Cat(*[txdata[10*i:10*i+8] for i in range(nwords)]),
                i_TXUSRCLK=ClockSignal("tx"),
                i_TXUSRCLK2=ClockSignal("tx"),

                # TX electrical
                i_TXBUFDIFFCTRL=0b000,
                i_TXDIFFCTRL=0b1100,

                # Pads
                o_GTHTXP=tx_pads.txp,
                o_GTHTXN=tx_pads.txn
            )

        self.clock_domains.cd_tx = ClockDomain()
        self.specials += Instance("BUFG_GT",
            i_I=txoutclk, o_O=self.cd_tx.clk)
        self.specials += AsyncResetSynchronizer(
            self.cd_tx, ~self.init.done)

        self.submodules.encoder = ClockDomainsRenamer("tx")(Encoder(nwords, True))
        self.comb += \
            If(self.produce_square_wave,
                # square wave @ linerate/40 for scope observation
                txdata.eq(0b1111111111111111111100000000000000000000)
            ).Else(
                txdata.eq(Cat(*[self.encoder.output[i] for i in range(nwords)]))
            )
