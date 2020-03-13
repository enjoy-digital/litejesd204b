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
from litex.soc.interconnect import stream

from litejesd204b.transport import LiteJESD204BTransportTX, LiteJESD204BTransportRX
from litejesd204b.transport import LiteJESD204BSTPLGenerator, LiteJESD204BSTPLChecker
from litejesd204b.link import LiteJESD204BLinkTX, LiteJESD204BLinkRX

# Clock Domain Crossing ----------------------------------------------------------------------------

class LiteJESD204BTXCDC(Module):
    def __init__(self, phy, phy_cd):
        assert len(phy.sink.data) in [16, 32]
        self.sink   =   sink = stream.Endpoint([("data", 32), ("ctrl", 4)])
        self.source = source = stream.Endpoint([("data", len(phy.sink.data)), ("ctrl", len(phy.sink.ctrl))])

        # # #

        use_ebuf = (len(phy.sink.data) == 32)

        if use_ebuf:
            ebuf = ElasticBuffer(len(phy.sink.data) + len(phy.source.ctrl), 4, "jesd", phy_cd)
            self.submodules.ebuf = ebuf
            self.comb += [
                sink.ready.eq(1),
                ebuf.din[:32].eq(sink.data),
                ebuf.din[32:].eq(sink.ctrl),
                source.valid.eq(1),
                source.data.eq(ebuf.dout[:32]),
                source.ctrl.eq(ebuf.dout[32:])
            ]
        else:
            cdc = stream.AsyncFIFO([("data", 32), ("ctrl", 4)], 4)
            cdc = ClockDomainsRenamer({"write": "jesd", "read": phy_cd})(cdc)
            self.submodules += cdc
            converter = stream.StrideConverter(
                [("data", 32), ("ctrl", 4)],
                [("data", len(phy.sink.data)), ("ctrl", len(phy.sink.ctrl))],
                reverse=False)
            converter = ClockDomainsRenamer(phy_cd)(converter)
            self.submodules += converter
            self.comb += [
                sink.connect(cdc.sink),
                cdc.source.connect(converter.sink),
                converter.source.connect(source)
            ]


class LiteJESD204BRXCDC(Module):
    def __init__(self, phy, phy_cd):
        assert len(phy.source.data) in [16, 32]
        self.sink   =   sink = stream.Endpoint([("data", len(phy.source.data)), ("ctrl", len(phy.source.ctrl))])
        self.source = source = stream.Endpoint([("data", 32), ("ctrl", 4)])

        # # #

        use_ebuf = (len(phy.source.data) == 32)

        if use_ebuf:
            ebuf = ElasticBuffer(len(phy.source.data) + len(phy.source.ctrl), 4, phy_cd, "jesd")
            self.submodules.ebuf = ebuf
            self.comb += [
                sink.ready.eq(1),
                ebuf.din[:32].eq(sink.data),
                ebuf.din[32:].eq(sink.ctrl),
                source.valid.eq(1),
                source.data.eq(ebuf.dout[:32]),
                source.ctrl.eq(ebuf.dout[32:])
            ]
        else:
            converter = stream.StrideConverter(
                [("data", len(phy.source.data)), ("ctrl", len(phy.source.ctrl))],
                [("data", 32), ("ctrl", 4)],
                reverse=False)
            converter = ClockDomainsRenamer(phy_cd)(converter)
            self.submodules += converter
            cdc = stream.AsyncFIFO([("data", 32), ("ctrl", 4)], 4)
            cdc = ClockDomainsRenamer({"write": phy_cd, "read": "jesd"})(cdc)
            self.submodules += cdc
            self.comb += [
                sink.connect(converter.sink),
                converter.source.connect(cdc.sink),
                cdc.source.connect(source)
            ]

# Core TX ------------------------------------------------------------------------------------------

class LiteJESD204BCoreTX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable  = Signal()
        self.jsync   = Signal()
        self.jref    = Signal()
        self.ready   = Signal()
        self.restart = Signal()

        self.stpl_enable = Signal()

        self.sink = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        # Restart when disabled...
        self.comb += If(~self.enable, self.restart.eq(1))

        # ... or on re-synchronization request from the DAC.
        jsync = Signal()
        jsync_timer = ClockDomainsRenamer("jesd")(WaitTimer(256))
        self.submodules += jsync_timer
        self.comb += jsync_timer.wait.eq(~jsync)
        self.specials += MultiReg(self.jsync, jsync, "jesd")
        self.comb += If(self.ready & jsync_timer.done, self.restart.eq(1))

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd")(transport)
        self.submodules.transport = transport

        # stpl
        stpl = LiteJESD204BSTPLGenerator(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd")(stpl)
        self.submodules.stpl = stpl
        self.comb += \
            If(self.stpl_enable,
                transport.sink.eq(stpl.source)
            ).Else(
                transport.sink.eq(self.sink)
            )

        self.links = links = []
        for n, (phy, lane) in enumerate(zip(phys, transport.source.flatten())):
            phy_name = "jesd_phy{}".format(n if not hasattr(phy, "n") else phy.n)
            phy_cd   = phy_name + "_tx"

            cdc = LiteJESD204BTXCDC(phy, phy_cd)
            setattr(self.submodules, "cdc"+str(n), cdc)

            link = LiteJESD204BLinkTX(32, jesd_settings, n)
            link = ClockDomainsRenamer("jesd")(link)
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
                cdc.sink.valid.eq(1),
                cdc.sink.data.eq(link.source.data),
                cdc.sink.ctrl.eq(link.source.ctrl),
                cdc.source.connect(phy.sink)
            ]

        self.sync.jesd += self.ready.eq(reduce(and_, [link.ready for link in links]))

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
        self.enable  = Signal()
        self.jsync   = Signal()
        self.jref    = Signal()
        self.ready   = Signal()
        self.restart = Signal()

        self.stpl_enable = Signal()

        self.source = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        # Restart when disabled.
        self.comb += If(~self.enable, self.restart.eq(1))

        # transport layer
        transport = LiteJESD204BTransportRX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd")(transport)
        self.submodules.transport = transport

        # stpl
        stpl = LiteJESD204BSTPLChecker(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd")(stpl)
        self.submodules.stpl = stpl
        self.comb += \
            If(self.stpl_enable,
                stpl.sink.eq(transport.source)
            ).Else(
                self.source.eq(transport.source)
            )

        self.links      = links      = []
        self.skew_fifos = skew_fifos = []
        for n, (phy, lane) in enumerate(zip(phys, transport.sink.flatten())):
            phy_name = "jesd_phy{}".format(n if not hasattr(phy, "n") else phy.n)
            phy_cd = phy_name + "_rx"

            cdc = LiteJESD204BRXCDC(phy, phy_cd)
            setattr(self.submodules, "cdc"+str(n), cdc)

            link = LiteJESD204BLinkRX(32, jesd_settings, n, ilas_check)
            link = ClockDomainsRenamer("jesd")(link)
            self.submodules += link
            links.append(link)
            self.comb += [
                link.reset.eq(self.restart),
                link.jref.eq(self.jref),
                phy.rx_align.eq(link.align)
            ]

            skew_fifo = SyncFIFO(32, 2*jesd_settings.lmfc_cycles)
            skew_fifo = ClockDomainsRenamer("jesd")(skew_fifo)
            skew_fifo = ResetInserter()(skew_fifo)
            skew_fifos.append(skew_fifo)
            self.submodules += skew_fifo
            self.comb += [
                skew_fifo.reset.eq(~link.ready),
                skew_fifo.we.eq(1),
                skew_fifo.re.eq(self.ready),
            ]

            # connect data
            self.comb += [
                phy.source.connect(cdc.sink),
                link.sink.data.eq(cdc.source.data),
                link.sink.ctrl.eq(cdc.source.ctrl),
                cdc.source.ready.eq(1),
                skew_fifo.din.eq(link.source.data),
                lane.eq(skew_fifo.dout)
            ]

        self.sync.jesd += [
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
    def __init__(self, core, sys_clk_freq):
        self.enable      = CSRStorage()
        self.ready       = CSRStatus()

        self.stpl_enable = CSRStorage()
        self.stpl_errors = CSRStatus(32)

        self.jsync       = CSRStatus()

        # # #

        self.core = core

        self.specials += [
            MultiReg(self.enable.storage, core.enable, "jesd"),
            MultiReg(self.stpl_enable.storage, core.stpl_enable, "jesd"),
            MultiReg(core.stpl.errors, self.stpl_errors.status, "sys"),
            MultiReg(core.ready, self.ready.status, "sys")
        ]

        jsync_timer = WaitTimer(int(1e-3*sys_clk_freq))
        self.submodules += jsync_timer
        self.specials += MultiReg(core.jsync, jsync_timer.wait, "sys")
        self.comb += self.jsync.status.eq(jsync_timer.done)

    def add_advanced_controls(self):
        self.jsync_toggles = CSRStatus(32)
        self.lmfc_load     = CSRStorage(
            size  = len(self.core.links[0].lmfc.load),
            reset = self.core.links[0].lmfc.load.reset)
        if isinstance(self.core, LiteJESD204BCoreRX):
            for n in range(len(self.core.skew_fifos)):
                csr = CSRStatus(len(self.core.skew_fifos[n].level),
                    name="skew_fifo{}_level".format(n))
                setattr(self, "skew_fifo{}_level".format(n), csr)

        # # #

        # JSYNC toggles
        jsync         = Signal()
        jsync_d       = Signal()
        jsync_toggle  = Signal()
        jsync_toggles = Signal(32)
        self.specials += MultiReg(self.core.jsync, jsync)
        self.sync += jsync_d.eq(jsync)
        self.comb += jsync_toggle.eq(jsync ^ jsync_d)
        self.sync += [
            If(~self.enable.storage,
                jsync_toggles.eq(0)
            ).Elif(jsync_toggle,
                If(jsync_toggles != (2**32-1),
                    jsync_toggles.eq(jsync_toggles + 1)
                )
            )
        ]
        self.comb += self.jsync_toggles.status.eq(jsync_toggles)

        # LMFC load on SYSREF
        for n in range(len(self.core.links)):
            self.comb += self.core.links[n].lmfc.load.eq(self.lmfc_load.storage)

        # Skew FIFOs level (RX only)
        if isinstance(self.core, LiteJESD204BCoreRX):
            for n in range(len(self.core.skew_fifos)):
                csr_status = getattr(self, "skew_fifo{}_level".format(n))
                self.specials += MultiReg(self.core.skew_fifos[n].level, csr_status.status)
