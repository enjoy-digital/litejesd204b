from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litejesd204b.phy.gtx_init import GTXInit
from litejesd204b.phy.line_coding import Encoder

# 250Mhz refclk / 5 Gbps linerate

# TODO:
# -compute CPLL_FBDIV, CPLL_FBDIV_45, TXOUT_DIV, CPLL_REFCLK_DIV from refclk frequency and linerate


class GTXTransmitter(Module):
    def __init__(self, clock_pads_or_signal, tx_pads, sys_clk_freq, cd):
        if isinstance(clock_pads_or_signal, Signal):
            self.refclk_div2 = clock_pads_or_signal
        else:
            self.refclk_div2 = Signal()
            self.specials += Instance("IBUFDS_GTE2",
                i_CEB=0,
                i_I=clock_pads_or_signal.p,
                i_IB=clock_pads_or_signal.n,
                o_ODIV2=self.refclk_div2
            )

        self.submodules.gtx_init = GTXInit(sys_clk_freq, False)

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
                p_CPLL_FBDIV=4,
                p_CPLL_FBDIV_45=5,
                p_CPLL_REFCLK_DIV=1,
                p_RXOUT_DIV=1,
                p_TXOUT_DIV=1,
                o_CPLLLOCK=self.gtx_init.cplllock,
                i_CPLLLOCKEN=1,
                i_CPLLREFCLKSEL=0b001,
                i_TSTIN=2**20-1,
                i_GTREFCLK0=self.refclk_div2,

                # TX clock
                p_TXBUF_EN="FALSE",
                p_TX_XCLK_SEL="TXUSR",
                o_TXOUTCLK=txoutclk,
                i_TXSYSCLKSEL=0b00,
                i_TXOUTCLKSEL=0b11,

                # disable RX
                i_RXPD=0b11,

                # Startup/Reset
                i_GTTXRESET=self.gtx_init.gtXxreset,
                o_TXRESETDONE=self.gtx_init.Xxresetdone,
                i_TXDLYSRESET=self.gtx_init.Xxdlysreset,
                o_TXDLYSRESETDONE=self.gtx_init.Xxdlysresetdone,
                o_TXPHALIGNDONE=self.gtx_init.Xxphaligndone,
                i_TXUSERRDY=self.gtx_init.Xxuserrdy,

                # TX data
                p_TX_DATA_WIDTH=40,
                p_TX_INT_DATAWIDTH=1,
                i_TXCHARDISPMODE=Cat(*[txdata[10*i+9] for i in range(nwords)]),
                i_TXCHARDISPVAL=Cat(*[txdata[10*i+8] for i in range(nwords)]),
                i_TXDATA=Cat(*[txdata[10*i:10*i+8] for i in range(nwords)]),
                i_TXUSRCLK=ClockSignal(cd),
                i_TXUSRCLK2=ClockSignal(cd),

                # TX electrical
                i_TXBUFDIFFCTRL=0b100,
                i_TXDIFFCTRL=0b1000,

                # Pads
                o_GTXTXP=tx_pads.txp,
                o_GTXTXN=tx_pads.txn
            )

        self.clock_domains.cd_tx = ClockDomain(cd)
        self.specials += Instance("BUFG",
            i_I=txoutclk, o_O=self.cd_tx.clk)
        self.specials += AsyncResetSynchronizer(
            self.cd_tx, ~self.gtx_init.done)

        self.submodules.encoder = ClockDomainsRenamer(cd)(Encoder(nwords, True))
        self.comb += txdata.eq(Cat(*[self.encoder.output[i] for i in range(nwords)]))
