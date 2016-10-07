from functools import reduce
from operator import and_

from litex.gen import *
from litex.gen.genlib.cdc import MultiReg
from litex.gen.genlib.fifo import AsyncFIFO
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *

from litejesd204b.transport import LiteJESD204BTransportTX
from litejesd204b.link import LiteJESD204BLinkTX


class LiteJESD204BCoreTX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable = Signal()
        self.start = Signal()
        self.ready = Signal()

        self.prbs_config = Signal(4)

        # # #

        ready = Signal()

        # clocking (use clock from first phy for core clock)
        self.clock_domains.cd_tx = ClockDomain("jesd_tx_core")
        self.comb += self.cd_tx.clk.eq(phys[0].gtx.cd_tx.clk)
        self.specials += AsyncResetSynchronizer(self.cd_tx, ~ready)

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings,
                                            converter_data_width)
        transport = ClockDomainsRenamer("jesd_tx_core")(transport)
        self.submodules.transport = transport

        # buffers
        self.bufs = bufs = []
        for phy in phys:
            buf = AsyncFIFO(len(phy.data), 8) # FIXME use elastic buffers
            buf = ClockDomainsRenamer(
                {"write": "jesd_tx_core", "read": phy.gtx.cd_tx.name})(buf)
            bufs.append(buf)
            self.submodules += buf

        # link layer
        self.links = links = []
        for n, phy in enumerate(phys):
            link = LiteJESD204BLinkTX(len(phy.data), jesd_settings, n)
            link = ClockDomainsRenamer(phy.gtx.cd_tx.name)(link)
            links.append(link)
            self.comb += [
                link.start.eq(self.start)
            ]
            self.submodules += link
        self.comb += ready.eq(reduce(or_, [link.ready for link in links]))

        # connect modules together
        for n, (link, buf) in enumerate(zip(links, bufs)):
            self.comb += [
                buf.we.eq(1),
                buf.din.eq(getattr(transport.source, "lane"+str(n))),
                link.sink.data.eq(buf.dout),
                buf.re.eq(1),
                phys[n].data.eq(link.source.data),
                phys[n].ctrl.eq(link.source.ctrl)
            ]

        # control
        for phy in phys:
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
