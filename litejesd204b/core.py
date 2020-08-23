#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2016 Robert Jordens <jordens@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause

from functools import reduce
from operator import and_

from migen import *
from migen.genlib.cdc import MultiReg, ElasticBuffer
from migen.genlib.misc import WaitTimer
from migen.genlib.fifo import SyncFIFO

from litex.build.io import DifferentialInput, DifferentialOutput

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

# Local Multiframe Clock ---------------------------------------------------------------------------

class LMFC(Module):
    def __init__(self, lmfc_cycles, load=0):
        load = (lmfc_cycles + load)%lmfc_cycles
        assert load >= 0
        self.load  = Signal(max=lmfc_cycles, reset=load)
        self.jref  = Signal()
        self.count = Signal(max=lmfc_cycles, reset_less=True)
        self.zero  = Signal(reset_less=True)

        # # #

        _jref   = Signal(reset_less=True)
        _jref_d = Signal(reset_less=True)
        self.sync += [
            _jref.eq(self.jref),
            _jref_d.eq(_jref),
            If(_jref & ~_jref_d,
                self.count.eq(self.load)
            ).Else(
                self.count.eq(self.count + 1)
            )
        ]
        self.comb += self.zero.eq(self.count == 0)

# Core TX ------------------------------------------------------------------------------------------

class LiteJESD204BCoreTX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.enable  = Signal()
        self.jsync   = Signal()
        self.jref    = Signal()
        self.ready   = Signal()

        self.stpl_enable = Signal()

        self.sink = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        # Transport layer
        transport = LiteJESD204BTransportTX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd")(transport)
        self.submodules.transport = transport

        # STPL
        stpl = LiteJESD204BSTPLGenerator(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd")(stpl)
        self.submodules.stpl = stpl
        self.comb += \
            If(self.stpl_enable,
                transport.sink.eq(stpl.source)
            ).Else(
                transport.sink.eq(self.sink)
            )

        # LMFC
        lmfc = LMFC(jesd_settings.lmfc_cycles, load=(1 + 4)) # jref + ebuf latency
        lmfc = ClockDomainsRenamer("jesd")(lmfc)
        self.submodules.lmfc = lmfc
        self.sync.jesd += lmfc.jref.eq(self.jref)

        # Links
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
                link.reset.eq(~self.enable),
                link.jsync.eq(self.jsync),
                link.jref.eq(self.jref),
                link.lmfc_zero.eq(self.lmfc.zero),
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
        _jsync = Signal()
        if isinstance(jsync, Signal):
            self.comb += _jsync.eq(jsync)
        elif isinstance(jsync, Record):
            self.specials += DifferentialInput(jsync.p, jsync.n, _jsync)
        else:
            raise ValueError
        self.specials += MultiReg(_jsync, self.jsync, "jesd")

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

        self.stpl_enable = Signal()

        self.source = Record([("converter"+str(i), converter_data_width)
            for i in range(jesd_settings.nconverters)])

        # # #

        # Transport Layer
        transport = LiteJESD204BTransportRX(jesd_settings, converter_data_width)
        transport = ClockDomainsRenamer("jesd")(transport)
        self.submodules.transport = transport

        # STPL
        stpl = LiteJESD204BSTPLChecker(jesd_settings, converter_data_width)
        stpl = ClockDomainsRenamer("jesd")(stpl)
        self.submodules.stpl = stpl
        self.comb += \
            If(self.stpl_enable,
                stpl.sink.eq(transport.source)
            ).Else(
                self.source.eq(transport.source)
            )

        # LMFC
        lmfc = LMFC(jesd_settings.lmfc_cycles, load=-(1 + 4)) # jref + ebuf latency
        lmfc = ClockDomainsRenamer("jesd")(lmfc)
        self.submodules.lmfc = lmfc
        self.sync.jesd += lmfc.jref.eq(self.jref)

        # Links
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
                link.reset.eq(~self.enable),
                link.jref.eq(self.jref),
                link.lmfc_zero.eq(self.lmfc.zero),
                phy.rx_align.eq(link.align)
            ]

            skew_fifo = SyncFIFO(32, jesd_settings.lmfc_cycles)
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
            If(lmfc.zero,
                self.ready.eq(reduce(and_, [link.ready for link in links]))
            ),
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
        self.control = CSRStorage(fields=[
            CSRField("enable", size=1, values=[
                ("``0b0``", "JESD core disabled."),
                ("``0b1``", "JESD core enabled.")
            ])
        ])
        self.status = CSRStatus(fields=[
            CSRField("ready", size=1, offset=0, values=[
                ("``0b0``", "JESD core not ready, all links are not synchronized."),
                ("``0b1``", "JESD core ready, all links are synchronized.")
            ]),
            CSRField("sync_n",    size=1, offset=1, description="JESD ``SYNC~`` status."),
            CSRField("skew_fifo", size=8, offset=8, description="JESD Skew FIFO level (``RX only``)."),
        ])
        self.stpl_enable = CSRStorage(fields=[
            CSRField("enable", size=1, offset=0, values=[
                ("``0b0``", "STPL test disabled."),
                ("``0b1``", "STPL test enabled.")
            ])
        ])
        self.stpl_errors = CSRStatus(32, description="STPL test errors.")
        self.lmfc        = CSRStorage(fields=[
            CSRField("load_on_sysref", size=len(core.lmfc.load),
                reset       = core.lmfc.load.reset,
                description = "LMFC reload value on SYSREF rising edge."),
        ])

        # # #

        self.specials += [
            MultiReg(self.control.fields.enable,      core.enable,      "jesd"),
            MultiReg(self.stpl_enable.storage,        core.stpl_enable, "jesd"),
            MultiReg(self.lmfc.fields.load_on_sysref, core.lmfc.load,   "jesd"),
            MultiReg(core.stpl.errors, self.stpl_errors.status,   "sys"),
            MultiReg(core.ready,       self.status.fields.ready,  "sys"),
            MultiReg(core.jsync,       self.status.fields.sync_n, "sys"),
        ]
        if hasattr(core, "skew_fifos"):
            self.specials += MultiReg(core.skew_fifos[0].level, self.status.fields.skew_fifo)
