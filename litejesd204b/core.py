from functools import reduce
from operator import and_

from litex.gen import *
from litex.gen.genlib.cdc import MultiReg, ElasticBuffer
from litex.gen.genlib.misc import WaitTimer

from litex.soc.interconnect.csr import *

from litejesd204b.transport import (LiteJESD204BTransportTX,
                                    LiteJESD204BSTPLGenerator)
from litejesd204b.link import LiteJESD204BLinkTX


class LiteJESD204BCoreTXWatchdog(Module):
    def __init__(self):
        self.enable = Signal()
        self.start = Signal()
        self.ready = Signal()
        self.prbs = Signal()

        self.restart = Signal()

        # # #

        init_timer = WaitTimer(1024)
        ready_timer = WaitTimer(1024*1024)
        self.submodules += init_timer, ready_timer

        self.submodules.fsm = fsm = FSM(reset_state="INIT")
        fsm.act("INIT",
            self.restart.eq(~self.prbs),
            init_timer.wait.eq(self.enable),
            If(init_timer.done,
                NextState("RUN")
            )
        )
        fsm.act("RUN",
            ready_timer.wait.eq(~self.ready),
             If(~self.enable |
               (self.ready & ~self.start) |
               ready_timer.done,
                NextState("INIT")
            )
        )


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

        # watchdog
        self.submodules.watchdog = watchdog = LiteJESD204BCoreTXWatchdog()
        self.comb += [
            watchdog.enable.eq(self.enable),
            watchdog.start.eq(self.start),
            watchdog.ready.eq(self.ready),
            watchdog.prbs.eq(self.prbs_config != 0)
        ]

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings,
                                            converter_data_width)
        self.submodules.transport = transport

        # stpl
        stpl = LiteJESD204BSTPLGenerator(jesd_settings,
                                         converter_data_width)
        self.submodules += stpl
        stpl_enable = Signal()
        self.specials += \
            MultiReg(self.stpl_enable, stpl_enable)
        self.comb += \
            If(stpl_enable,
                transport.sink.eq(stpl.source)
            ).Else(
                transport.sink.eq(self.sink)
            )

        links = []
        for n, (phy, lane) in enumerate(zip(phys, transport.source.flatten())):
            phy_name = "phy{}".format(n)
            phy_cd = phy_name + "_tx"

            # claim the phy
            setattr(self.submodules, phy_name, phy)

            ebuf = ElasticBuffer(len(phy.data), 4, "sys", phy_cd)
            setattr(self.submodules, "ebuf{}".format(n), ebuf)

            link = LiteJESD204BLinkTX(len(phy.data), jesd_settings, n)
            link = ClockDomainsRenamer(phy_cd)(link)
            links.append(link)
            self.comb += link.start.eq(self.start)
            self.submodules += link

            # connect data
            self.comb += [
                ebuf.din.eq(lane),
                link.sink.data.eq(ebuf.dout),
                phy.data.eq(link.source.data),
                phy.ctrl.eq(link.source.ctrl)
            ]

            # connect control
            self.comb += phy.transmitter.init.restart.eq(watchdog.restart)
            self.specials += MultiReg(self.prbs_config,
                                      phy.transmitter.prbs_config,
                                      phy_cd)
        ready = Signal()
        self.comb += ready.eq(reduce(and_, [link.ready for link in links]))
        self.specials += MultiReg(ready, self.ready)


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
