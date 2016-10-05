from functools import reduce
from operator import and_

from litex.gen import *
from litex.gen.genlib.cdc import MultiReg
from litex.gen.genlib.fifo import AsyncFIFO
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *

from litejesd204b.transport import LiteJESD204BTransportTX
from litejesd204b.link import LiteJESD204BLinkTX

#TODO:
# - use elastic buffers between transport and links instead of async fifos

class LiteJESD204BCoreTX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable = Signal()
        self.start = Signal()
        self.ready = Signal()

        self.prbs_config = Signal(4)

        # # #

        ready = Signal()

        # clocking (use clock from first phy for core clock)
        self.clock_domains.cd_tx = ClockDomain()
        self.comb += self.cd_tx.clk.eq(phys[0].gtx.cd_tx.clk)
        self.specials += AsyncResetSynchronizer(self.cd_tx, ~ready)

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings,
                                            converter_data_width)
        transport = ClockDomainsRenamer("tx")(transport)
        self.submodules.transport = transport

        # cdc
        self.cdcs = cdcs = []
        for i, phy in enumerate(phys):
            cdc = AsyncFIFO(len(phy.data), 8)
            cdc = ClockDomainsRenamer(
                {"write": "tx", "read": phy.gtx.cd_tx.name})(cdc)
            cdcs.append(cdc)
            self.submodules += cdc

        # link layer
        self.links = links = []
        for i, phy in enumerate(phys):
            jesd_settings.lid = i
            link = LiteJESD204BLinkTX(len(phy.data), jesd_settings)
            link = ClockDomainsRenamer(phy.gtx.cd_tx.name)(link)
            links.append(link)
            self.comb += [
                link.start.eq(self.start)
            ]
            self.submodules += link
        self.comb += ready.eq(reduce(or_, [link.ready for link in links]))

        # connect modules together
        for i, (link, cdc) in enumerate(zip(links, cdcs)):
            self.comb += [
                cdc.we.eq(1),
                cdc.din.eq(getattr(transport.source, "lane"+str(i))),
                link.sink.data.eq(cdc.dout),
                cdc.re.eq(1),
                phys[i].data.eq(link.source.data),
                phys[i].ctrl.eq(link.source.ctrl)
            ]

        # control
        for i, phy in enumerate(phys):
            self.comb += phy.gtx.gtx_init.restart.eq(~self.enable)
            self.specials += [
                MultiReg(self.prbs_config,
                    phy.gtx.prbs_config,
                    phy.gtx.cd_tx.name),
            ]
        self.specials +=  MultiReg(~self.cd_tx.rst, self.ready)


class LiteJESD204BCoreTXControl(Module, AutoCSR):
    def __init__(self, core):
        self.enable = CSRStorage()
        self.ready = CSRStatus()

        self.prbs_config = CSRStorage(4)

        # # #

        self.comb += [
            core.enable.eq(self.enable.storage),
            core.prbs_config.eq(self.prbs_config.storage),
            self.ready.status.eq(core.ready)
        ]
