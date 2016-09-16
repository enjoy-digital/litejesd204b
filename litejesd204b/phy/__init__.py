from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litejesd204b.common import *
from litejesd204b.phy.gtx import GTXTransmitter
from litejesd204b.phy.prbs import PRBS7Generator, PRBS15Generator, PRBS31Generator

# TODO:
# fix clocking

class LiteJESD204BPhyTX(Module, AutoCSR):
    def __init__(self, clock_pads_or_refclk, tx_pads, sys_clk_freq, data_width=32):
        assert data_width == 32 # only supporting 32 bits datapath for now
        self.data_width = data_width
        self.sink = sink = stream.Endpoint(phy_layout(data_width))
        
        self.enable = CSRStorage()
        self.config = CSRStorage(2)

        # # #

        # prbs generators
        prbs7 = PRBS7Generator(data_width)
        prbs15 = PRBS15Generator(data_width)
        prbs31 = PRBS31Generator(data_width)
        self.submodules += prbs7, prbs15, prbs31

        # data / prbs generators muxing
        muxed_stream = stream.Endpoint(phy_layout(data_width))
        cases = {}
        cases[0] = self.sink.connect(muxed_stream)
        for i, prbs in enumerate([prbs7, prbs15, prbs31]):
            cases[i+1] = [
                muxed_stream.valid.eq(1),
                muxed_stream.data.eq(prbs.o)
            ]
        self.comb += \
            If(self.enable.storage,
                muxed_stream.ready.eq(1),
                Case(self.config.storage, cases)
            ).Else(
                prbs7.reset.eq(1),
                prbs15.reset.eq(1),
                prbs31.reset.eq(1)
            )

        # transceiver
        self.submodules.gtx = GTXTransmitter(
                clock_pads_or_refclk=clock_pads_or_refclk,
                tx_pads=tx_pads,
                sys_clk_freq=sys_clk_freq)

        for i in range(data_width//8):
            self.comb += [
                self.gtx.encoder.d[i].eq(muxed_stream.data[8*i:8*(i+1)]),
                self.gtx.encoder.k[i].eq(muxed_stream.ctrl[i])
            ]
