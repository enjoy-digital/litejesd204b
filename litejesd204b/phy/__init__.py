from litex.gen import *

from litejesd204b.common import *
from litejesd204b.phy.gtx import GTXTransmitter


class LiteJESD204BPhyTX(Module):
    def __init__(self, refclk_pads_or_signal, refclk_freq, tx_pads,
            linerate, sys_clk_freq, n=0):
        self.data = Signal(32)
        self.ctrl = Signal(32//8)

        # # #

        # transceiver
        self.submodules.gtx = GTXTransmitter(
                refclk_pads_or_signal=refclk_pads_or_signal,
                refclk_freq=refclk_freq,
                tx_pads=tx_pads,
                linerate=linerate,
                sys_clk_freq=sys_clk_freq,
                cd_name="jesd_tx_phy"+str(n))

        for i in range(32//8):
            self.comb += [
                self.gtx.encoder.d[i].eq(self.data[8*i:8*(i+1)]),
                self.gtx.encoder.k[i].eq(self.ctrl[i])
            ]
