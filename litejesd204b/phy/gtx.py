from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litejesd204b.phy.gtx_init import GTXInit
from litejesd204b.phy.line_coding import Encoder


class GTXTransmitter(Module):
    def __init__(self, clock_pads_or_refclk, tx_pads, sys_clk_freq):
        if isinstance(clock_pads_or_refclk, Signal):
            self.refclk_div2 = clock_pads_or_refclk
        else:
            self.refclk_div2 = Signal()
            self.specials += Instance("IBUFDS_GTE2",
                i_CEB=0,
                i_I=clock_pads_or_refclk.refclk_p,
                i_IB=clock_pads_or_refclk.refclk_n,
                o_ODIV2=self.refclk_div2
            )

        self.submodules.gtx_init = GTXInit(sys_clk_freq, False)

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
                p_RXOUT_DIV=2,
                p_TXOUT_DIV=2,
                o_CPLLLOCK=self.gtx_init.cplllock,
                i_CPLLLOCKEN=1,
                i_CPLLREFCLKSEL=0b001,
                i_TSTIN=2**40-1,
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
                i_TXCHARDISPMODE=Cat(txdata[9], txdata[19], txdata[29], txdata[39]),
                i_TXCHARDISPVAL=Cat(txdata[8], txdata[18], txdata[28], txdata[38]),
                i_TXDATA=Cat(txdata[0:8], txdata[10:18], txdata[20:28], txdata[30:38]),
                i_TXUSRCLK=ClockSignal("tx"),
                i_TXUSRCLK2=ClockSignal("tx"),

                # TX electrical
                i_TXBUFDIFFCTRL=0b100,
                i_TXDIFFCTRL=0b1000,

                # Pads
                o_GTXTXP=tx_pads.txp,
                o_GTXTXN=tx_pads.txn,
            )

        self.clock_domains.cd_tx = ClockDomain()
        self.specials += Instance("BUFG",
            i_I=txoutclk, o_O=self.cd_tx.clk)
        self.specials += AsyncResetSynchronizer(
            self.cd_tx, ~self.gtx_init.done)

        self.submodules.encoder = ClockDomainsRenamer("tx")(Encoder(4, True))
        self.comb += txdata.eq(Cat(self.encoder.output[0],
                                   self.encoder.output[1],
                                   self.encoder.output[2],
                                   self.encoder.output[3]))
