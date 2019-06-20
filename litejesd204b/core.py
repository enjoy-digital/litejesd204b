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

        self.prbs_config = Signal(4)
        self.stpl_enable = Signal()

        self.sink = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        # restart when disabled or on re-synchronization request
        jsync = Signal()
        self.specials += MultiReg(self.jsync, jsync, "sys")
        self.comb += self.restart.eq(~self.enable | (self.ready & ~jsync))

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd_tx")(transport)
        self.submodules.transport = transport

        # stpl
        stpl = LiteJESD204BSTPLGenerator(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd_tx")(stpl)
        self.submodules += stpl
        stpl_enable = Signal()
        self.specials += MultiReg(self.stpl_enable, stpl_enable)
        self.comb += \
            If(stpl_enable,
                transport.sink.eq(stpl.source)
            ).Else(
                transport.sink.eq(self.sink)
            )

        self.links = links = []
        link_reset = Signal()
        self.comb += link_reset.eq(~reduce(and_, [phy.tx_init.done for phy in phys]) | self.restart)
        for n, (phy, lane) in enumerate(zip(phys, transport.source.flatten())):
            phy_name = "phy{}".format(n if not hasattr(phy, "n") else phy.n)
            phy_cd = phy_name + "_tx"

            ebuf = ElasticBuffer(len(phy.sink.data) + len(phy.source.ctrl), 4, "jesd_tx", phy_cd)
            setattr(self.submodules, "ebuf{}".format(n), ebuf)

            link = LiteJESD204BLinkTX(len(phy.sink.data), jesd_settings, n)
            link = ClockDomainsRenamer("jesd_tx")(link)
            self.submodules += link
            links.append(link)
            self.comb += [
                link.reset.eq(link_reset),
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

            # connect control
            self.comb += phy.tx_restart.eq(self.restart & (self.prbs_config == 0))
            self.specials += MultiReg(self.prbs_config, phy.tx_prbs_config, phy_cd)

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

# Core TX Control ----------------------------------------------------------------------------------

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


# Core RX ------------------------------------------------------------------------------------------

class LiteJESD204BCoreRX(Module):
    # WORK IN PROGRESS - UNTESTED
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable = Signal()
        self.jsync = Signal()
        self.jref = Signal()
        self.ready = Signal()
        self.restart = Signal()

        self.prbs_config = Signal(4)
        self.stpl_enable = Signal()

        self.source = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        ready = Signal()

        self.comb += self.restart.eq(~self.enable)

        # transport layer
        transport = LiteJESD204BTransportRX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd_rx")(transport)
        self.submodules.transport = transport

        # stpl
        stpl = LiteJESD204BSTPLChecker(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd_rx")(stpl)
        self.submodules += stpl
        stpl_enable = Signal()
        self.specials += MultiReg(self.stpl_enable, stpl_enable)
        self.comb += \
            If(stpl_enable,
                stpl.sink.eq(transport.source)
            ).Else(
                self.source.eq(transport.source)
            )

        self.links = links = []
        link_reset = Signal()
        self.comb += link_reset.eq(~reduce(and_, [phy.rx_init.done for phy in phys]) | self.restart)
        for n, (phy, lane) in enumerate(zip(phys, transport.sink.flatten())):
            phy_name = "phy{}".format(n if not hasattr(phy, "n") else phy.n)
            phy_cd = phy_name + "_rx"

            ebuf = ElasticBuffer(len(phy.source.data) + len(phy.source.ctrl), 4, phy_cd, "jesd_rx")
            setattr(self.submodules, "ebuf{}".format(n), ebuf)

            link = LiteJESD204BLinkRX(len(phy.source.data), jesd_settings, n)
            link = ClockDomainsRenamer("jesd_rx")(link)
            self.submodules += link
            links.append(link)
            self.comb += [
                link.reset.eq(link_reset),
                link.jref.eq(self.jref),
                phy.rx_align.eq(link.align)
            ]

            align_fifo = SyncFIFO(len(phy.source.data), 32) # FIXME: determine depth
            align_fifo = ResetInserter()(align_fifo)
            self.submodules += align_fifo
            self.comb += [
                align_fifo.reset.eq(link_reset),
                align_fifo.we.eq(1),
                align_fifo.re.eq(ready),
            ]

            # connect data
            self.comb += [
                phy.source.ready.eq(1),
                ebuf.din[:len(phy.source.data)].eq(phy.source.data),
                ebuf.din[len(phy.source.data):].eq(phy.source.ctrl),
                link.sink.data.eq(ebuf.dout[:len(phy.source.data)]),
                link.sink.ctrl.eq(ebuf.dout[len(phy.source.data):]),
                align_fifo.din.eq(link.source.data),
                lane.eq(align_fifo.dout)
            ]

            # connect control
            self.comb += phy.rx_restart.eq(self.restart & (self.prbs_config == 0))
            self.specials += MultiReg(self.prbs_config, phy.rx_prbs_config, phy_cd)

        self.comb += self.jsync.eq(reduce(and_, [link.jsync for link in links]))
        self.comb += ready.eq(reduce(and_, [link.ready for link in links]))
        self.specials += MultiReg(ready, self.ready)

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

# Core RX Control ----------------------------------------------------------------------------------

class LiteJESD204BCoreRXControl(Module, AutoCSR):
    def __init__(self, core):
        self.enable = CSRStorage()
        self.ready = CSRStatus()

        self.prbs_config = CSRStorage(4)
        self.stpl_enable = CSRStorage()

        self.jsync = CSRStatus()

        # # #

        # core control/status
        self.comb += [
            core.enable.eq(self.enable.storage),
            core.prbs_config.eq(self.prbs_config.storage),
            core.stpl_enable.eq(self.stpl_enable.storage),

            self.ready.status.eq(core.ready)
        ]
        self.specials += MultiReg(core.jsync, self.jsync.status)
