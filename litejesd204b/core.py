from functools import reduce
from operator import and_

from migen import *
from migen.genlib.cdc import MultiReg, ElasticBuffer
from migen.genlib.misc import WaitTimer
from migen.genlib.io import DifferentialInput

from litex.soc.interconnect.csr import *

from litejesd204b.transport import (LiteJESD204BTransportTX,
                                    LiteJESD204BSTPLGenerator)
from litejesd204b.link import LiteJESD204BLinkTX


class LiteJESD204BCoreTX(Module, AutoCSR):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable = Signal()
        self.jsync = Signal()
        self.jref = Signal()
        self.ready = Signal()
        self.restart = Signal()

        self.prbs_config = Signal(4)
        self.stpl_enable = Signal()

        self.sink = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        # restart when disabled or on re-synchronization request
        self.comb += self.restart.eq(~self.enable | self.ready & ~self.jsync)

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
            self.comb += [
                link.jsync.eq(self.jsync),
                link.jref.eq(self.jref)
            ]
            self.submodules += link

            # connect data
            self.comb += [
                ebuf.din.eq(lane),
                link.sink.data.eq(ebuf.dout),
                phy.data.eq(link.source.data),
                phy.ctrl.eq(link.source.ctrl)
            ]

            # connect control
            self.comb += phy.transmitter.init.restart.eq(self.restart &
            	                                         (self.prbs_config == 0))

            self.specials += MultiReg(self.prbs_config,
                                      phy.transmitter.prbs_config,
                                      phy_cd)
        ready = Signal()
        self.comb += ready.eq(reduce(and_, [link.ready for link in links]))
        self.specials += MultiReg(ready, self.ready)

    def register_jsync(self, jsync):
        self.jsync_registered = True
        if isinstance(jsync, Signal):
            self.comb += self.jsync.eq(jsync)
        elif isinstance(jsync, Record):
            self.specials += DifferentialInput(jsync.p, jsync.n, self.jsync)
        else:
            raise ValueError

    def register_jref(self, jref):
        self.jref_registered = True
        if isinstance(jref, Signal):
            self.comb += self.jref.eq(jref)
        elif isinstance(jref, Record):
            self.specials += DifferentialInput(jref.p, jref.n, self.jref)
        else:
            raise ValueError

    def do_finalize(self):
        assert hasattr(self, "jsync_registered")
        assert hasattr(self, "jref_registered")


class LiteJESD204BCoreTXControl(Module, AutoCSR):
    def __init__(self, core):
        self.enable = CSRStorage()
        self.ready = CSRStatus()

        self.prbs_config = CSRStorage(4)
        self.stpl_enable = CSRStorage()

        self.jsync = CSRStatus()

        self.restart_count_clear = CSR()
        self.restart_count = CSRStatus(8)

        # # #

        # core control/status
        self.comb += [
            core.enable.eq(self.enable.storage),
            core.prbs_config.eq(self.prbs_config.storage),
            core.stpl_enable.eq(self.stpl_enable.storage),

            self.ready.status.eq(core.ready)
        ]
        self.specials += MultiReg(core.jsync, self.jsync.status)

        # restart monitoring

        # restart is a slow signal so we simply pass it to sys_clk and
        # count rising edges
        restart = Signal()
        restart_d = Signal()
        restart_count = Signal(8)
        self.specials += MultiReg(core.restart, restart)
        self.sync += \
            If(self.restart_count_clear.re,
                restart_count.eq(0)
            ).Elif(restart & ~restart_d,
                # don't overflow when max is reached
                If(restart_count != (2**8-1),
                    restart_count.eq(restart_count + 1)
                )
            )
        self.comb += self.restart_count.status.eq(restart_count)


