from migen import *

from litejesd204b.common import *
from litejesd204b.phy.gtp import GTPTransmitter
from litejesd204b.phy.gtx import GTXTransmitter
from litejesd204b.phy.gth import GTHTransmitter

from litex.soc.interconnect.csr import *


class LiteJESD204BPhyTX(Module, AutoCSR):
    def __init__(self, pll, tx_pads, sys_clk_freq, transceiver="gtx"):
        self.data = Signal(32)
        self.ctrl = Signal(32//8)

        # # #

        transmitters = {
            "gtp": GTPTransmitter,
            "gtx": GTXTransmitter,
            "gth": GTHTransmitter
        }
        self.submodules.transmitter = transmitters[transceiver](
            pll=pll,
            tx_pads=tx_pads,
            sys_clk_freq=sys_clk_freq
        )
        for i in range(32//8):
            self.comb += [
                self.transmitter.encoder.d[i].eq(self.data[8*i:8*(i+1)]),
                self.transmitter.encoder.k[i].eq(self.ctrl[i])
            ]
