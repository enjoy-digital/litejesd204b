from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litejesd204b.common import *
from litejesd204b.phy.gtx import GTXTransmitter
from litejesd204b.phy.prbs import PRBS7Generator, PRBS15Generator, PRBS31Generator


class LiteJESD204BPhyTX(Module, AutoCSR):
    def __init__(self, clock_pads_or_refclk_div2, tx_pads, sys_clk_freq, n, data_width=32):
        self.cd = "jesd_tx_"+str(n)
        assert data_width == 32 # only supporting 32 bits datapath for now
        self.data_width = data_width
        self.sink = sink = stream.Endpoint(phy_layout(data_width))

        # # #

        self.comb += sink.ready.eq(1)

        # transceiver
        self.submodules.gtx = GTXTransmitter(
                clock_pads_or_refclk_div2=clock_pads_or_refclk_div2,
                tx_pads=tx_pads,
                sys_clk_freq=sys_clk_freq,
                cd=self.cd)

        for i in range(data_width//8):
            self.comb += [
                self.gtx.encoder.d[i].eq(sink.data[8*i:8*(i+1)]),
                self.gtx.encoder.k[i].eq(sink.ctrl[i])
            ]
