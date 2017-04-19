from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer
from litex.soc.cores.code_8b10b import Encoder

from litejesd204b.phy.gtx_init import GTXInit


class GTXChannelPLL(Module):
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
                    if 1.6e9 <= vco_freq <= 3.3e9:
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
GTXChannelPLL
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


class GTXQuadPLL(Module):
    def __init__(self, refclk, refclk_freq, linerate):
        self.clk = Signal()
        self.refclk = Signal()
        self.reset = Signal()
        self.lock = Signal()
        self.config = self.compute_config(refclk_freq, linerate)

        # # #

        fbdiv_ratios = {
            16:  1,
            20:  1,
            32:  1,
            40:  1,
            64:  1,
            66:  0,
            80:  1,
            100: 1
        }
        fbdivs = {
            16:  0b0000100000,
            20:  0b0000110000,
            32:  0b0001100000,
            40:  0b0010000000,
            64:  0b0011100000,
            66:  0b0101000000,
            80:  0b0100100000,
            100: 0b0101110000
        }

        self.specials += \
            Instance("GTXE2_COMMON",
                p_QPLL_CFG=0x0680181 if self.config["vco_band"] == "upper" else
                           0x06801c1,
                p_QPLL_FBDIV=fbdivs[self.config["n"]],
                p_QPLL_FBDIV_RATIO=fbdiv_ratios[self.config["n"]],
                p_QPLL_REFCLK_DIV=self.config["m"],
                i_GTREFCLK0=refclk,
                i_QPLLRESET=self.reset,

                o_QPLLOUTCLK=self.clk,
                o_QPLLOUTREFCLK=self.refclk,
                i_QPLLLOCKEN=1,
                o_QPLLLOCK=self.lock,
                i_QPLLREFCLKSEL=0b001
            )

    @staticmethod
    def compute_config(refclk_freq, linerate):
        for n in 16, 20, 32, 40, 64, 66, 80, 100:
            for m in 1, 2, 3, 4:
                vco_freq = refclk_freq*n/m
                if 5.93e9 <= vco_freq <= 8e9:
                    vco_band = "lower"
                elif 9.8e9 <= vco_freq <= 12.5e9:
                    vco_band = "upper"
                else:
                    vco_band = None
                if vco_band is not None:
                    for d in [1, 2, 4, 8, 16]:
                        current_linerate = (vco_freq/2)*2/d
                        if current_linerate == linerate:
                            return {"n": n, "m": m, "d": d,
                                    "vco_freq": vco_freq,
                                    "vco_band": vco_band,
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
       |   +-----+  +---------------------------+ | Upper Band | +--+ |
       |   |     |  | Phase Frequency Detector  +->    VCO     | |  | |
CLKIN +----> /M  +-->       Charge Pump         | +------------+->/2+--> CLKOUT
       |   |     |  |       Loop Filter         +-> Lower Band | |  | |
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
    VCO      = {vco_freq}GHz ({vco_band})
    LINERATE = CLKOUT x 2 / D = {clkout}GHz x 2 / {d}
             = {linerate}GHz
""".format(clkin=self.config["clkin"]/1e6,
           n=self.config["n"],
           m=self.config["m"],
           clkout=self.config["clkout"]/1e9,
           vco_freq=self.config["vco_freq"]/1e9,
           vco_band=self.config["vco_band"],
           d=self.config["d"],
           linerate=self.config["linerate"]/1e9)
        return r


class GTXTransmitter(Module):
    def __init__(self, pll, tx_pads, sys_clk_freq):
        self.prbs_config = Signal(4)
        self.produce_square_wave = Signal()

        # # #

        use_cpll = isinstance(pll, GTXChannelPLL)
        use_qpll = isinstance(pll, GTXQuadPLL)

        self.submodules.init = GTXInit(sys_clk_freq, False)
        self.comb += [
            self.init.plllock.eq(pll.lock),
            pll.reset.eq(self.init.pllreset)
        ]

        nwords = 40//10

        txoutclk = Signal()
        txdata = Signal(40)
        self.specials += \
            Instance("GTXE2_CHANNEL",
                # PMA Attributes
                p_PMA_RSV=0x00018480,
                p_PMA_RSV2=0x2050,
                p_PMA_RSV3=0,
                p_PMA_RSV4=0,
                p_RX_BIAS_CFG=0b100,
                p_RX_CM_TRIM=0b010,
                p_RX_OS_CFG=0b10000000,
                p_RX_CLK25_DIV=5,
                p_TX_CLK25_DIV=5,

                # Power-Down Attributes
                p_PD_TRANS_TIME_FROM_P2=0x3c,
                p_PD_TRANS_TIME_NONE_P2=0x3c,
                p_PD_TRANS_TIME_TO_P2=0x64,

                # CPLL
                p_CPLL_CFG=0xBC07DC,
                p_CPLL_FBDIV=1 if use_qpll else pll.config["n2"],
                p_CPLL_FBDIV_45=4 if use_qpll else pll.config["n1"],
                p_CPLL_REFCLK_DIV=1 if use_qpll else pll.config["m"],
                p_RXOUT_DIV=pll.config["d"],
                p_TXOUT_DIV=pll.config["d"],
                i_CPLLRESET=0 if use_qpll else pll.reset,
                o_CPLLLOCK=Signal() if use_qpll else pll.lock,
                i_CPLLLOCKEN=1,
                i_CPLLREFCLKSEL=0b001,
                i_TSTIN=2**20-1,
                i_GTREFCLK0=0 if use_qpll else pll.refclk,

                # QPLL
                i_QPLLCLK=0 if use_cpll else pll.clk,
                i_QPLLREFCLK=0 if use_cpll else pll.refclk,

                # TX clock
                p_TXBUF_EN="FALSE",
                p_TX_XCLK_SEL="TXUSR",
                o_TXOUTCLK=txoutclk,
                i_TXSYSCLKSEL=0b11 if use_qpll else 0b00,
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
                i_TXCHARDISPMODE=Cat(*[txdata[10*i+9] for i in range(nwords)]),
                i_TXCHARDISPVAL=Cat(*[txdata[10*i+8] for i in range(nwords)]),
                i_TXDATA=Cat(*[txdata[10*i:10*i+8] for i in range(nwords)]),
                i_TXUSRCLK=ClockSignal("tx"),
                i_TXUSRCLK2=ClockSignal("tx"),

                # TX electrical
                i_TXBUFDIFFCTRL=0b100,
                i_TXDIFFCTRL=0b1000,

                # Pads
                o_GTXTXP=tx_pads.txp,
                o_GTXTXN=tx_pads.txn
            )

        self.clock_domains.cd_tx = ClockDomain()
        self.specials += Instance("BUFH",
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
