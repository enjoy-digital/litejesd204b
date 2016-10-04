from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litejesd204b.phy.gtx_init import GTXInit
from litejesd204b.phy.line_coding import Encoder


cpll_min_freq = 1.6*1e9
cpll_max_freq = 3.3*1e9

cpll_n1_values = [4, 5]
cpll_n2_values = [1, 2, 3, 4, 5]
cpll_m_values = [1, 2]
cpll_d_values = [1, 2, 4, 8, 16]


def cpll_get_pll_freq(refclk_freq, n1, n2, m):
    return refclk_freq*(n1*n2)/m


def cpll_get_line_rate(pll_freq, d):
    return pll_freq*2/d


class CPLLConfig:
    def __init__(self, n1, n2, m, d):
        self.n1 = n1
        self.n2 = n2
        self.m = m
        self.d = d


def cpll_get_config(refclk_freq, linerate):
    # bruteforce config finder, returns the first valid config
    valid_configs = []
    for n1 in cpll_n1_values:
        for n2 in cpll_n2_values:
            for m in cpll_m_values:
                for d in cpll_d_values:
                    pll_freq = cpll_get_pll_freq(refclk_freq, n1, n2, m)
                    if pll_freq < cpll_min_freq:
                        break
                    if pll_freq > cpll_max_freq:
                        break
                    if cpll_get_line_rate(pll_freq, d) != linerate:
                        break
                    return CPLLConfig(n1, n2, m, d)
    msg = "No CPLL config found for {:3.2f} MHz refclk / {:3.2f} Gbps linerate."
    raise ValueError(msg.format(refclk_freq/1e6, linerate/1e9))


class GTXTransmitter(Module):
    def __init__(self, refclk_pads_or_signal, refclk_freq, tx_pads,
            sys_clk_freq, linerate, cd_name):
        self.prbs_config = Signal(4)

        # # #

        cpll_config = cpll_get_config(refclk_freq/2, linerate) # ODIV2 --> /2

        if isinstance(refclk_pads_or_signal, Signal):
            self.refclk_div2 = refclk_pads_or_signal
        else:
            self.refclk_div2 = Signal()
            self.specials += Instance("IBUFDS_GTE2",
                i_CEB=0,
                i_I=refclk_pads_or_signal.p,
                i_IB=refclk_pads_or_signal.n,
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
                p_CPLL_FBDIV=cpll_config.n2,
                p_CPLL_FBDIV_45=cpll_config.n1,
                p_CPLL_REFCLK_DIV=cpll_config.m,
                p_RXOUT_DIV=cpll_config.d,
                p_TXOUT_DIV=cpll_config.d,
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

                # PRBS
                i_TXPRBSSEL=self.prbs_config[0:3],
                i_TXPRBSFORCEERR=self.prbs_config[3],

                # TX data
                p_TX_DATA_WIDTH=40,
                p_TX_INT_DATAWIDTH=1,
                i_TXCHARDISPMODE=Cat(*[txdata[10*i+9] for i in range(nwords)]),
                i_TXCHARDISPVAL=Cat(*[txdata[10*i+8] for i in range(nwords)]),
                i_TXDATA=Cat(*[txdata[10*i:10*i+8] for i in range(nwords)]),
                i_TXUSRCLK=ClockSignal(cd_name),
                i_TXUSRCLK2=ClockSignal(cd_name),

                # TX electrical
                i_TXBUFDIFFCTRL=0b100,
                i_TXDIFFCTRL=0b1000,

                # Pads
                o_GTXTXP=tx_pads.txp,
                o_GTXTXN=tx_pads.txn
            )

        self.clock_domains.cd_tx = ClockDomain(cd_name)
        self.specials += Instance("BUFG",
            i_I=txoutclk, o_O=self.cd_tx.clk)
        self.specials += AsyncResetSynchronizer(
            self.cd_tx, ~self.gtx_init.done)

        self.submodules.encoder = ClockDomainsRenamer(cd_name)(Encoder(nwords, True))
        self.comb += txdata.eq(Cat(*[self.encoder.output[i] for i in range(nwords)]))
