from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *
from litex.soc.cores.code_8b10b import Encoder

from litejesd204b.phy.gtp_init import GTPTXInit
from litejesd204b.phy.prbs import *


class GTPQuadPLL(Module):
    def __init__(self, refclk, refclk_freq, linerate):
        self.clk = Signal()
        self.refclk = Signal()
        self.reset = Signal()
        self.lock = Signal()
        self.config = self.compute_config(refclk_freq, linerate)

        # # #

        self.specials += \
            Instance("GTPE2_COMMON",
                # common
                i_GTREFCLK0=refclk,
                i_BGBYPASSB=1,
                i_BGMONITORENB=1,
                i_BGPDB=1,
                i_BGRCALOVRD=0b11111,
                i_RCALENB=1,

                # pll0
                p_PLL0_FBDIV=self.config["n2"],
                p_PLL0_FBDIV_45=self.config["n1"],
                p_PLL0_REFCLK_DIV=self.config["m"],
                i_PLL0LOCKEN=1,
                i_PLL0PD=0,
                i_PLL0REFCLKSEL=0b001,
                i_PLL0RESET=self.reset,
                o_PLL0LOCK=self.lock,
                o_PLL0OUTCLK=self.clk,
                o_PLL0OUTREFCLK=self.refclk,

                # pll1 (not used: power down)
                i_PLL1PD=1,
             )

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
GTPQuadPLL
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


class GTPTransmitter(Module, AutoCSR):
    def __init__(self, pll, tx_pads, sys_clk_freq, polarity=0):
        self.prbs_config = Signal(2)

        self.produce_square_wave = CSRStorage()

        self.txdiffcttrl = CSRStorage(4, reset=0b1000)
        self.txmaincursor = CSRStorage(7, reset=80)
        self.txprecursor = CSRStorage(5)
        self.txpostcursor = CSRStorage(5)

        # # #


        self.submodules.init = GTPTXInit(sys_clk_freq)
        self.comb += [
            self.init.plllock.eq(pll.lock),
            pll.reset.eq(self.init.pllreset)
        ]

        nwords = 40//10

        txoutclk = Signal()
        txdata = Signal(40)
        self.specials += \
            Instance("GTPE2_CHANNEL",
                i_GTRESETSEL=0,
                i_RESETOVRD=0,
                p_SIM_RESET_SPEEDUP="FALSE",

                # PMA Attributes
                p_PMA_RSV=0x333,
                p_PMA_RSV2=0x2040,
                p_PMA_RSV3=0,
                p_PMA_RSV4=0,
                p_RX_BIAS_CFG=0b0000111100110011,
                p_RX_CM_TRIM=0b1010,
                p_RX_OS_CFG=0b10000000,
				p_RX_CLK25_DIV=5,
				p_TX_CLK25_DIV=5,

                # Power-Down Attributes
                p_PD_TRANS_TIME_FROM_P2=0x3c,
                p_PD_TRANS_TIME_NONE_P2=0x3c,
                p_PD_TRANS_TIME_TO_P2=0x64,

                # QPLL
                i_PLL0CLK=pll.clk,
                i_PLL0REFCLK=pll.refclk,

                # TX clock
                p_TXBUF_EN="FALSE",
                p_TX_XCLK_SEL="TXUSR",
                o_TXOUTCLK=txoutclk,
                p_TXOUT_DIV=pll.config["d"],
                i_TXSYSCLKSEL=0b00,
                i_TXOUTCLKSEL=0b11,

                # disable RX
                i_RXPD=0b11,

                # TX Startup/Reset
                i_GTTXRESET=self.init.gttxreset,
                o_TXRESETDONE=self.init.txresetdone,
                p_TXSYNC_OVRD=1,
                i_TXDLYSRESET=self.init.txdlysreset,
                o_TXDLYSRESETDONE=self.init.txdlysresetdone,
                i_TXPHINIT=self.init.txphinit,
                o_TXPHINITDONE=self.init.txphinitdone,
                i_TXPHALIGNEN=1,
                i_TXPHALIGN=self.init.txphalign,
                o_TXPHALIGNDONE=self.init.txphaligndone,
                i_TXDLYEN=self.init.txdlyen,
                i_TXUSERRDY=self.init.txuserrdy,

                # TX data
                p_TX_DATA_WIDTH=40,
                i_TXCHARDISPMODE=Cat(*[txdata[10*i+9] for i in range(nwords)]),
                i_TXCHARDISPVAL=Cat(*[txdata[10*i+8] for i in range(nwords)]),
                i_TXDATA=Cat(*[txdata[10*i:10*i+8] for i in range(nwords)]),
                i_TXUSRCLK=ClockSignal("tx"),
                i_TXUSRCLK2=ClockSignal("tx"),

                # TX electrical
                i_TXBUFDIFFCTRL=0b100,
                i_TXDIFFCTRL=self.txdiffcttrl.storage,
                p_TX_MAINCURSOR_SEL=1,
                i_TXMAINCURSOR=self.txmaincursor.storage,
                i_TXPRECURSOR=self.txprecursor.storage,
                i_TXPOSTCURSOR=self.txpostcursor.storage,

                # Polarity
                i_TXPOLARITY=polarity,

                # Pads
                o_GTPTXP=tx_pads.txp,
                o_GTPTXN=tx_pads.txn
            )

        self.clock_domains.cd_tx = ClockDomain()
        self.specials += Instance("BUFH",
            i_I=txoutclk, o_O=self.cd_tx.clk)
        self.specials += AsyncResetSynchronizer(
            self.cd_tx, ~self.init.done)

        self.submodules.encoder = ClockDomainsRenamer("tx")(Encoder(nwords, True))
        self.submodules.prbs = ClockDomainsRenamer("tx")(PRBSTX(40, True))
        self.comb += [
            self.prbs.config.eq(self.prbs_config),
            self.prbs.i.eq(Cat(*[self.encoder.output[i] for i in range(nwords)])),
            If(self.produce_square_wave.storage,
                # square wave @ linerate/40 for scope observation
                txdata.eq(0b1111111111111111111100000000000000000000)
            ).Else(
                txdata.eq(self.prbs.o)
            )
        ]