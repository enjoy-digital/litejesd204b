from litex.gen import *

from litejesd204b.common import *
from litejesd204b.phy.gtx import GTXTransmitter


class LiteJESD204BPhyTX(Module):
    def __init__(self, clock_pads_or_refclk_div2, tx_pads, sys_clk_freq, n):
        self.cd = "jesd_tx_"+str(n)

        self.data = Signal(32)
        self.ctrl = Signal(32//8)

        # # #

        # transceiver
        self.submodules.gtx = GTXTransmitter(
                clock_pads_or_refclk_div2=clock_pads_or_refclk_div2,
                tx_pads=tx_pads,
                sys_clk_freq=sys_clk_freq,
                cd=self.cd)

        for i in range(32//8):
            self.comb += [
                self.gtx.encoder.d[i].eq(self.data[8*i:8*(i+1)]),
                self.gtx.encoder.k[i].eq(self.ctrl[i])
            ]
