from functools import reduce
from operator import and_

from litex.gen import *
from litex.gen.genlib.cdc import MultiReg
from litex.gen.genlib.fifo import AsyncFIFO
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.soc.interconnect.csr import *

from litejesd204b.transport import (LiteJESD204BTransportTX,
                                    LiteJESD204BSTPLGenerator)
from litejesd204b.link import LiteJESD204BLinkTX


class LiteJESD204BCoreTX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable = Signal()
        self.start = Signal()
        self.ready = Signal()

        self.prbs_config = Signal(4)
        self.stpl_enable = Signal()

        self.sink = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        ready = Signal()

        # clocking
        # phys
        for n, phy in enumerate(phys):
            cd_phy = ClockDomain("phy"+str(n))
            self.comb += [
                cd_phy.clk.eq(phy.gtx.cd_tx.clk),
                cd_phy.rst.eq(phy.gtx.cd_tx.rst)
            ]
            self.clock_domains += cd_phy
        # user
        self.clock_domains.cd_user = ClockDomain()
        self.comb += self.cd_user.clk.eq(ClockSignal("phy0"))
        self.specials += AsyncResetSynchronizer(self.cd_user, ~ready)

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings,
                                            converter_data_width)
        transport = ClockDomainsRenamer("user")(transport)
        self.submodules.transport = transport

        # stpl
        stpl_enable = Signal()
        stpl = LiteJESD204BSTPLGenerator(jesd_settings,
                                         converter_data_width)
        self.submodules += stpl
        self.specials += MultiReg(self.stpl_enable,
                                  stpl_enable,
                                  "user")
        self.comb += \
            If(stpl_enable,
                transport.sink.eq(stpl.source)
            ).Else(
                transport.sink.eq(self.sink)
            )

        # buffers
        self.bufs = bufs = []
        for n, phy in enumerate(phys):
            buf = AsyncFIFO(len(phy.data), 8) # FIXME use elastic buffers
            buf = ClockDomainsRenamer(
                {"write": "user", "read": "phy"+str(n)})(buf)
            bufs.append(buf)
            self.submodules += buf

        # link layer
        self.links = links = []
        for n, phy in enumerate(phys):
            link = LiteJESD204BLinkTX(len(phy.data), jesd_settings, n)
            link = ClockDomainsRenamer("phy"+str(n))(link)
            links.append(link)
            self.comb += link.start.eq(self.start)
            self.submodules += link
        self.comb += ready.eq(reduce(or_, [link.ready for link in links]))

        # connect modules together
        for n, (link, buf) in enumerate(zip(links, bufs)):
            self.comb += [
                buf.we.eq(1),
                buf.din.eq(getattr(transport.source, "lane"+str(n))),
                buf.re.eq(1),
                link.sink.data.eq(buf.dout),
                phys[n].data.eq(link.source.data),
                phys[n].ctrl.eq(link.source.ctrl)
            ]

        # control
        for n, phy in enumerate(phys):
            self.comb += phy.gtx.gtx_init.restart.eq(~self.enable)
            self.specials += MultiReg(self.prbs_config,
                                      phy.gtx.prbs_config,
                                      "phy"+str(n))
        self.specials +=  MultiReg(~self.cd_user.rst, self.ready)


class LiteJESD204BCoreTXControl(Module, AutoCSR):
    def __init__(self, core):
        self.enable = CSRStorage()
        self.ready = CSRStatus()

        self.prbs_config = CSRStorage(4)
        self.stpl_enable = CSRStorage()

        # # #

        self.comb += [
            core.enable.eq(self.enable.storage),
            core.prbs_config.eq(self.prbs_config.storage),
            core.stpl_enable.eq(self.stpl_enable.storage),

            self.ready.status.eq(core.ready)
        ]
