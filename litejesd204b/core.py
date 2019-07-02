# This file is Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2016 Robert Jordens <jordens@gmail.com>
# License: BSD

from functools import reduce
from operator import and_

from migen import *
from migen.genlib.cdc import MultiReg, ElasticBuffer
from migen.genlib.misc import WaitTimer
from migen.genlib.io import DifferentialInput, DifferentialOutput
from migen.genlib.fifo import SyncFIFO

from litex.soc.interconnect.csr import *

from litejesd204b.transport import (LiteJESD204BTransportTX,
                                    LiteJESD204BTransportRX,
                                    LiteJESD204BSTPLGenerator,
                                    LiteJESD204BSTPLChecker)
from litejesd204b.link import LiteJESD204BLinkTX, LiteJESD204BLinkRX

# Core TX ------------------------------------------------------------------------------------------

class LiteJESD204BCoreTX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable = Signal()
        self.jsync = Signal()
        self.jref = Signal()
        self.ready = Signal()
        self.restart = Signal()

        self.stpl_enable = Signal()

        self.sink = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        # restart when disabled or on re-synchronization request
        jsync = Signal()
        self.specials += MultiReg(self.jsync, jsync, "jesd_tx")
        self.comb += self.restart.eq(~self.enable | (self.ready & ~jsync))

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd_tx")(transport)
        self.submodules.transport = transport

        # stpl
        stpl = LiteJESD204BSTPLGenerator(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd_tx")(stpl)
        self.submodules += stpl
        self.comb += \
            If(self.stpl_enable,
                transport.sink.eq(stpl.source)
            ).Else(
                transport.sink.eq(self.sink)
            )

        self.links = links = []
        for n, (phy, lane) in enumerate(zip(phys, transport.source.flatten())):
            phy_name = "jesd_phy{}".format(n if not hasattr(phy, "n") else phy.n)
            phy_cd = phy_name + "_tx"

            ebuf = ElasticBuffer(len(phy.sink.data) + len(phy.source.ctrl), 4, "jesd_tx", phy_cd)
            setattr(self.submodules, "ebuf{}".format(n), ebuf)

            link = LiteJESD204BLinkTX(len(phy.sink.data), jesd_settings, n)
            link = ClockDomainsRenamer("jesd_tx")(link)
            self.submodules += link
            links.append(link)
            self.comb += [
                link.reset.eq(self.restart),
                link.jsync.eq(self.jsync),
                link.jref.eq(self.jref)
            ]

            # connect data
            self.comb += [
                link.sink.data.eq(lane),
                ebuf.din[:len(phy.sink.data)].eq(link.source.data),
                ebuf.din[len(phy.sink.data):].eq(link.source.ctrl),
                phy.sink.valid.eq(1),
                phy.sink.data.eq(ebuf.dout[:len(phy.sink.data)]),
                phy.sink.ctrl.eq(ebuf.dout[len(phy.sink.data):])
            ]

        self.sync.jesd_tx += self.ready.eq(reduce(and_, [link.ready for link in links]))

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

# Core RX ------------------------------------------------------------------------------------------

class LiteJESD204BCoreRX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width, ilas_check=True):
        self.enable = Signal()
        self.jsync = Signal()
        self.jref = Signal()
        self.ready = Signal()
        self.restart = Signal()

        self.stpl_enable = Signal()

        self.source = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        self.comb += self.restart.eq(~self.enable)

        # transport layer
        transport = LiteJESD204BTransportRX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd_rx")(transport)
        self.submodules.transport = transport

        # stpl
        stpl = LiteJESD204BSTPLChecker(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd_rx")(stpl)
        self.submodules += stpl
        self.comb += \
            If(self.stpl_enable,
                stpl.sink.eq(transport.source)
            ).Else(
                self.source.eq(transport.source)
            )

        self.links = links = []
        for n, (phy, lane) in enumerate(zip(phys, transport.sink.flatten())):
            phy_name = "jesd_phy{}".format(n if not hasattr(phy, "n") else phy.n)
            phy_cd = phy_name + "_rx"

            ebuf = ElasticBuffer(len(phy.source.data) + len(phy.source.ctrl), 4, phy_cd, "jesd_rx")
            setattr(self.submodules, "ebuf{}".format(n), ebuf)

            link = LiteJESD204BLinkRX(len(phy.source.data), jesd_settings, n, ilas_check)
            link = ClockDomainsRenamer("jesd_rx")(link)
            self.submodules += link
            links.append(link)
            self.comb += [
                link.reset.eq(self.restart),
                link.jref.eq(self.jref),
                phy.rx_align.eq(link.align)
            ]

            skew_fifo = SyncFIFO(len(phy.source.data), 2*jesd_settings.lmfc_cycles)
            skew_fifo = ClockDomainsRenamer("jesd_rx")(skew_fifo)
            skew_fifo = ResetInserter()(skew_fifo)
            self.submodules += skew_fifo
            self.comb += [
                skew_fifo.reset.eq(~link.ready),
                skew_fifo.we.eq(1),
                skew_fifo.re.eq(self.ready),
            ]

            # connect data
            self.comb += [
                phy.source.ready.eq(1),
                ebuf.din[:len(phy.source.data)].eq(phy.source.data),
                ebuf.din[len(phy.source.data):].eq(phy.source.ctrl),
                link.sink.data.eq(ebuf.dout[:len(phy.source.data)]),
                link.sink.ctrl.eq(ebuf.dout[len(phy.source.data):]),
                skew_fifo.din.eq(link.source.data),
                lane.eq(skew_fifo.dout)
            ]

        self.sync.jesd_rx += [
            self.jsync.eq(reduce(and_, [link.jsync for link in links])),
            self.ready.eq(reduce(and_, [link.ready for link in links])),
        ]

    def register_jsync(self, jsync):
        self.jsync_registered = True
        if isinstance(jsync, Signal):
            self.comb += jsync.eq(self.jsync)
        elif isinstance(jsync, Record):
            self.specials += DifferentialOutput(self.jsync, jsync.p, jsync.n)
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

# Core Control ----------------------------------------------------------------------------------

class LiteJESD204BCoreControl(Module, AutoCSR):
    def __init__(self, core, sys_clk_freq, cd):
        self.enable = CSRStorage()
        self.ready = CSRStatus()

        self.stpl_enable = CSRStorage()

        self.jsync = CSRStatus()

        # # #

        self.specials += [
            MultiReg(self.enable.storage, core.enable, cd),
            MultiReg(self.stpl_enable.storage, core.stpl_enable, cd),
            MultiReg(core.ready, self.ready.status, "sys")
        ]

        jsync_timer = WaitTimer(int(1e-3*sys_clk_freq))
        self.submodules += jsync_timer
        self.specials += MultiReg(core.jsync, jsync_timer.wait, "sys")
        self.comb += self.jsync.status.eq(jsync_timer.done)


class LiteJESD204BCoreTXControl(LiteJESD204BCoreControl):
    def __init__(self, core, sys_clk_freq):
        LiteJESD204BCoreControl.__init__(self, core, sys_clk_freq, "jesd_tx")


class LiteJESD204BCoreRXControl(LiteJESD204BCoreControl):
    def __init__(self, core, sys_clk_freq):
        LiteJESD204BCoreControl.__init__(self, core, sys_clk_freq, "jesd_rx")
