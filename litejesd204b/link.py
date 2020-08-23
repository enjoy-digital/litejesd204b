#
# This file is part of LiteJESD204B
#
# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from collections import namedtuple

from migen import *
from migen.genlib.misc import WaitTimer

from litejesd204b.common import control_characters


Control = namedtuple("Control", "value")

# Layout -------------------------------------------------------------------------------------------

def link_layout(data_width):
    layout = [
        ("data", data_width),
        ("ctrl", data_width//8),

        ("last", 1),

        ("frame_last", data_width//8),
        ("multiframe_last", data_width//8)
    ]
    return layout

# Scrambling ---------------------------------------------------------------------------------------

def swizzle(s, data_width):
    return Cat(*[s[data_width-8*(i+1):data_width-8*i] for i in range(data_width//8)])

@ResetInserter()
class Scrambler(Module):
    """Scrambler
    cf section 5.2.3
    """
    def __init__(self, data_width, seed=0x7f80):
        self.sink    = sink   = Record([("data", data_width)])
        self.source  = source = Record([("data", data_width)])
        self.valid   = Signal()
        self.latency = 1

        # # #

        state    = Signal(15, reset=seed)
        feedback = Signal(data_width)
        full     = Signal(data_width+15)

        self.comb += [
            full.eq(Cat(feedback, state)),
            feedback.eq(full[15:15+data_width] ^
                        full[14:14+data_width] ^
                        swizzle(sink.data, data_width))
        ]

        source.data.reset_less = True
        self.sync += [
            self.valid.eq(1),
            source.data.eq(swizzle(feedback, data_width)),
            state.eq(full)
        ]


@ResetInserter()
class Descrambler(Scrambler):
    """Scrambler
    cf section 5.2.3
    """
    def __init__(self, data_width, seed=0x7f80):
        self.sink    = sink   = Record([("data", data_width)])
        self.source  = source = Record([("data", data_width)])
        self.valid   = Signal()
        self.latency = 1

        # # #

        state    = Signal(15, reset=seed)
        feedback = Signal(data_width)
        full     = Signal(data_width+15)

        self.comb += [
            full.eq(Cat(swizzle(sink.data, data_width), state)),
            feedback.eq(full[15:15+data_width] ^
                        full[14:14+data_width] ^
                        full[0:32])
        ]

        source.data.reset_less = True
        self.sync += [
            self.valid.eq(1),
            source.data.eq(swizzle(feedback, data_width)),
            state.eq(full)
        ]


# Framing ------------------------------------------------------------------------------------------

@ResetInserter()
class Framer(Module):
    """Framer
    """
    def __init__(self, data_width, octets_per_frame, frames_per_multiframe):
        self.sink    = sink   = Record([("data", data_width)])
        self.source  = source = Record(link_layout(data_width))
        self.latency = 0

        # # #

        frame_width           = octets_per_frame*8
        frames_per_clock      = data_width//frame_width
        clocks_per_multiframe = frames_per_multiframe//frames_per_clock

        # at least a frame per clock
        assert frame_width <= data_width
        # multiple number of frame per clock
        assert data_width%frame_width == 0
        # multiframes aligned on clock
        assert frames_per_multiframe%frames_per_clock == 0

        frame_last = 0
        for i in range(data_width//8):
            if (i+1)%octets_per_frame == 0:
                frame_last |= (1<<i)

        counter = Signal(8)
        self.sync += \
            If(source.multiframe_last != 0,
                counter.eq(0)
            ).Else(
                counter.eq(counter+1)
            )

        self.comb += [
            source.data.eq(sink.data),
            source.frame_last.eq(frame_last),
            If(counter == (clocks_per_multiframe-1),
                source.multiframe_last.eq(1<<(data_width//8)-1)
            )
        ]

@ResetInserter()
class Deframer(Module):
    """Deframer
    """
    def __init__(self, data_width, octets_per_frame, frames_per_multiframe):
        self.sink    = sink   = Record(link_layout(data_width))
        self.source  = source = Record([("data", data_width)])
        self.latency = 0

        # # #

        frame_width           = octets_per_frame*8
        frames_per_clock      = data_width//frame_width
        clocks_per_multiframe = frames_per_multiframe//frames_per_clock

        # at least a frame per clock
        assert frame_width <= data_width
        # multiple number of frame per clock
        assert data_width%frame_width == 0
        # multiframes aligned on clock
        assert frames_per_multiframe%frames_per_clock == 0

        # FIXME: start on multiframe boundary?
        self.comb += [
            source.data.eq(sink.data),
        ]

# Alignment ----------------------------------------------------------------------------------------

class AlignInserter(Module):
    """Alignment Character Inserter
    cf section 5.3.3.4.3
    """
    def __init__(self, data_width):
        self.sink    = sink   = Record(link_layout(data_width))
        self.source  = source = Record(link_layout(data_width))
        self.latency = 0

        # # #

        self.comb += source.eq(sink)

        for i in range(data_width//8):
            self.comb += [
                # last scrambled octet in a multiframe equals "A" control character
                If(sink.data[8*i:8*(i+1)] == control_characters["A"],
                    If(sink.multiframe_last[i],
                        source.ctrl[i].eq(1)
                    )
                # last scrambled octet in a frame but not at the end of a
                # multiframe equals "F" control character
                ).Elif(sink.data[8*i:8*(i+1)] == control_characters["F"],
                    If(sink.frame_last[i] & ~sink.multiframe_last[i],
                        source.ctrl[i].eq(1)
                    )
                )
            ]


class AlignReplacer(Module):
    """Alignment Character Replacer
    cf section 5.3.3.4.3
    """
    def __init__(self, data_width):
        self.sink    = sink   = Record(link_layout(data_width))
        self.source  = source = Record(link_layout(data_width))
        self.latency = 0

        # # #

        # recopy scrambler data and set ctrl to 0
        self.comb += source.eq(sink)
        for i in range(data_width//8):
            self.comb += source.ctrl.eq(0)


class Aligner(Module):
    def __init__(self, data_width):
        assert data_width == 32
        self.sink    = sink   = Record(link_layout(data_width))
        self.source  = source = Record(link_layout(data_width))
        self.latency = 1

        # # #

        alignment = Signal(2)

        last_data = Signal(32, reset_less=True)
        last_ctrl = Signal(4,  reset_less=True)

        # Register last data/ctrl
        self.sync += [
            last_data.eq(sink.data),
            last_ctrl.eq(sink.ctrl)
        ]

        # Alignment detection
        for i in range(4):
            self.sync += [
                If(sink.ctrl[i] & (sink.data[8*i:8*(i+1)] == control_characters["R"]),
                    alignment.eq(i)
                )
            ]

        # Data selection
        data = Cat(last_data, sink.data)
        ctrl = Cat(last_ctrl, sink.ctrl)
        cases = {}
        for i in range(4):
            cases[i] = [
                source.data.eq(data[8*i:]),
                source.ctrl.eq(ctrl[i:]),
            ]
        self.comb += Case(alignment, cases)

# Code Group Synchronization -----------------------------------------------------------------------

class CGSGenerator(Module):
    """Code Group Synchronization
    """
    def __init__(self, data_width):
        self.source = source = Record(link_layout(data_width))

        # # #

        data = Signal(data_width)
        ctrl = Signal(data_width//8)
        for i in range(data_width//8):
            self.comb += [
                source.data[8*i:8*(i+1)].eq(control_characters["K"]),
                source.ctrl[i].eq(1)
            ]

class CGSChecker(Module):
    """Code Group Synchronization
    """
    def __init__(self, data_width):
        self.sink  = sink  = Record(link_layout(data_width))
        self.valid = valid = Signal()

        # # #

        data = Signal(data_width)
        ctrl = Signal(data_width//8)
        self.comb += valid.eq(1)
        for i in range(data_width//8):
            self.comb += [
                If(sink.data[8*i:8*(i+1)] != control_characters["K"],
                    valid.eq(0)
                ),
                If(sink.ctrl[i] != 1,
                    valid.eq(0)
                )
            ]

# Initial Lane Alignment Sequence ------------------------------------------------------------------

class ILAS:
    """Initial Lane Alignment Sequence
    cf section 5.3.3.5
    """
    def __init__(self, data_width,
                 octets_per_frame,
                 frames_per_multiframe,
                 configuration_data,
                 with_counter=True):

        # compute ILAS's octets

        octets_per_multiframe = octets_per_frame*frames_per_multiframe

        octets = []
        for i in range(4):
            if with_counter:
                multiframe = [(i*octets_per_multiframe + j) & 0xff
                    for j in range(octets_per_multiframe)]
            else:
                multiframe = [0]*octets_per_multiframe
            multiframe[0]  = Control(control_characters["R"])
            multiframe[-1] = Control(control_characters["A"])
            if i == 1:
                multiframe[1] = Control(control_characters["Q"])
                multiframe[2:2+len(configuration_data)] = configuration_data
            octets += multiframe

        # pack ILAS's octets in a lookup table

        octets_per_clock = data_width//8

        self.data_words = data_words = []
        self.ctrl_words = ctrl_words = []
        for i in range(len(octets)//octets_per_clock):
            data_word = 0
            ctrl_word = 0
            for j in range(octets_per_clock):
                octet = octets[i*octets_per_clock+j]
                if isinstance(octet, Control):
                    data_word |= (octet.value << 8*j)
                    ctrl_word |= (1 << j)
                else:
                    data_word |= (octet << 8*j)
            data_words.append(data_word)
            ctrl_words.append(ctrl_word)

        assert len(data_words) == (octets_per_frame*
                                        frames_per_multiframe*
                                        4//octets_per_clock)

@ResetInserter()
class ILASGenerator(ILAS, Module):
    """Initial Lane Alignment Sequence Generator
    cf section 5.3.3.5
    """
    def __init__(self, data_width,
                 octets_per_frame,
                 frames_per_multiframe,
                 configuration_data,
                 with_counter=True):
        self.source = source = Record(link_layout(data_width))
        self.done = Signal()

        # # #

        # compute ILAS's data/ctrl words
        ILAS.__init__(self,
            data_width,
            octets_per_frame,
            frames_per_multiframe,
            configuration_data,
            with_counter)

        data_lut = Memory(data_width, len(self.data_words), init=self.data_words)
        data_port = data_lut.get_port(async_read=True)
        self.specials += data_lut, data_port

        ctrl_lut = Memory(data_width//8, len(self.ctrl_words), init=self.ctrl_words)
        ctrl_port = ctrl_lut.get_port(async_read=True)
        self.specials += ctrl_lut, ctrl_port

        # stream data/ctrl from lookup tables
        counter = Signal(max=len(self.data_words)+1)
        self.comb += [
            source.last.eq(counter == (len(self.data_words)-1)),
            data_port.adr.eq(counter),
            ctrl_port.adr.eq(counter),
            source.data.eq(data_port.dat_r),
            source.ctrl.eq(ctrl_port.dat_r)
        ]
        self.sync += \
            If(counter != len(self.data_words),
                counter.eq(counter + 1)
            )

        # done
        self.comb += self.done.eq(counter == len(self.data_words))


class ILASStartChecker(Module):
    """Code Group Synchronization
    """
    def __init__(self, data_width):
        self.sink  = sink  = Record(link_layout(data_width))
        self.valid = valid = Signal()

        # # #

        self.comb += [
            valid.eq(1),
            If((~sink.ctrl[0]) | (sink.data[0:8] != control_characters["R"]),
                valid.eq(0)
            ),
            If(sink.ctrl[1] | sink.ctrl[2] | sink.ctrl[3],
                valid.eq(0)
            ),
        ]


@ResetInserter()
class ILASChecker(ILAS, Module):
    """Initial Lane Alignment Sequence Checker
    cf section 5.3.3.5
    """
    def __init__(self, data_width,
                 octets_per_frame,
                 frames_per_multiframe,
                 configuration_data,
                 with_counter=True):
        self.sink  = sink  = Record(link_layout(data_width))
        self.done  = done  = Signal()
        self.valid = valid = Signal()

        # # #

        # detect start
        start =  ILASStartChecker(data_width)
        self.submodules.start = start
        self.comb += start.sink.eq(sink)

        # compute ILAS's data/ctrl words
        ILAS.__init__(self,
            data_width,
            octets_per_frame,
            frames_per_multiframe,
            configuration_data,
            with_counter)

        data_lut  = Memory(data_width, len(self.data_words), init=self.data_words)
        data_port = data_lut.get_port(async_read=True)
        self.specials += data_lut, data_port

        ctrl_lut  = Memory(data_width//8, len(self.ctrl_words), init=self.ctrl_words)
        ctrl_port = ctrl_lut.get_port(async_read=True)
        self.specials += ctrl_lut, ctrl_port

        self.data = data_port.dat_r
        self.ctrl = ctrl_port.dat_r

        # compare data/ctrl with lookup tables
        counter = Signal(max=len(self.data_words)+1)
        self.comb += [
            data_port.adr.eq(counter),
            ctrl_port.adr.eq(counter),
        ]
        self.sync += [
            If(counter != len(self.data_words),
                counter.eq(counter + 1),
            )
        ]
        self.comb += [
            valid.eq(1),
            If(sink.data != self.data,
                valid.eq(0)
            ),
            If(sink.ctrl != self.ctrl,
                valid.eq(0)
            )
        ]

        # done
        self.comb += self.done.eq(counter == len(self.data_words))

# Link TX ------------------------------------------------------------------------------------------

class LiteJESD204BLinkTXDapath(Module):
    def __init__(self, data_width, octets_per_frame, frames_per_multiframe):
        self.sink   = Record([("data", data_width)])
        self.source = Record(link_layout(data_width))

        # # #

        # Scrambling
        scrambler = Scrambler(data_width)
        self.submodules.scrambler = scrambler

        # Framing
        framer = Framer(data_width,
            octets_per_frame,
            frames_per_multiframe)
        self.submodules.framer = framer

        # Alignment
        align_inserter = AlignInserter(data_width)
        self.submodules.align_inserter = align_inserter

        # Flow
        self.latency = scrambler.latency + framer.latency + align_inserter.latency
        self.comb += [
            scrambler.sink.eq(self.sink),
            framer.reset.eq(~scrambler.valid),
            framer.sink.eq(scrambler.source),
            align_inserter.sink.eq(framer.source),
            self.source.eq(align_inserter.source)
        ]


@ResetInserter()
class LiteJESD204BLinkTX(Module):
    """Link TX layer
    """
    def __init__(self, data_width, jesd_settings, n=0):
        self.jsync     = Signal() # input
        self.jref      = Signal() # input
        self.lmfc_zero = Signal() # input
        self.ready     = Signal() # output

        self.sink   = sink   = Record([("data", data_width)])
        self.source = source = Record(link_layout(data_width))

        # # #

        # Code Group Synchronization
        cgs = CGSGenerator(data_width)
        self.submodules.cgs = cgs

        # Initial Lane Alignment Sequence
        ilas = ILASGenerator(data_width,
            jesd_settings.octets_per_lane,
            jesd_settings.transport.k,
            jesd_settings.get_configuration_data(n))
        self.submodules.ilas = ilas

        # Datapath
        datapath = LiteJESD204BLinkTXDapath(data_width,
            jesd_settings.octets_per_frame,
            jesd_settings.transport.k)
        self.submodules.datapath = datapath
        self.comb += datapath.sink.eq(sink)

        # Sync
        jsync_timer = WaitTimer(4) # distinguish errors reporting / re-synchronization requests.
        self.submodules += jsync_timer
        self.comb += jsync_timer.wait.eq(~self.jsync)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="SEND-CGS")
        fsm.act("SEND-CGS",
            ilas.reset.eq(1),
            datapath.scrambler.reset.eq(1),
            datapath.framer.reset.eq(1),
            source.data.eq(cgs.source.data),
            source.ctrl.eq(cgs.source.ctrl),
            # Start ILAS on first LMFC after jsync is asserted
            If(self.lmfc_zero & self.jsync,
                NextState("SEND-ILAS")
            )
        )
        fsm.act("SEND-ILAS",
            datapath.framer.reset.eq(1),
            source.data.eq(ilas.source.data),
            source.ctrl.eq(ilas.source.ctrl),
            If(ilas.source.last,
                NextState("SEND-DATA")
            )
        )
        fsm.act("SEND-DATA",
            self.ready.eq(1),
            source.eq(datapath.source),
            If(jsync_timer.done,
                NextState("SEND-CGS")
            ),
        )

# Link RX ------------------------------------------------------------------------------------------

class LiteJESD204BLinkRXDapath(Module):
    def __init__(self, data_width, octets_per_frame, frames_per_multiframe):
        self.sink   = Record(link_layout(data_width))
        self.source = Record([("data", data_width)])

        # # #

        # Alignment
        align_replacer = AlignReplacer(data_width)
        self.submodules.align_replacer = align_replacer

        # Deframing
        deframer = Deframer(data_width,
            octets_per_frame,
            frames_per_multiframe)
        self.submodules.deframer = deframer

        # Descrambling
        descrambler = Descrambler(data_width)
        self.submodules.descrambler = descrambler

        # Flow
        self.latency = align_replacer.latency + deframer.latency + descrambler.latency
        self.comb += [
            align_replacer.sink.eq(self.sink),
            deframer.sink.eq(align_replacer.source),
            descrambler.sink.eq(deframer.source),
            self.source.eq(descrambler.source)
        ]


@ResetInserter()
class LiteJESD204BLinkRX(Module):
    """Link RX layer
    """
    def __init__(self, data_width, jesd_settings, n=0, ilas_check=True):
        self.jsync     = Signal() # output
        self.jref      = Signal() # input
        self.lmfc_zero = Signal() # input
        self.ready     = Signal() # output
        self.align     = Signal() # output

        self.sink   = sink   = Record(link_layout(data_width))
        self.source = source = Record([("data", data_width)])

        # # #

        # Aligner
        aligner = Aligner(data_width)
        self.submodules.aligner = aligner

        # Code Group Synchronization
        cgs = CGSChecker(data_width)
        self.submodules.cgs = cgs

        # Initial Lane Alignment Sequence
        ilas = ILASChecker(data_width,
            jesd_settings.octets_per_lane,
            jesd_settings.transport.k,
            jesd_settings.get_configuration_data(n))
        self.submodules.ilas = ilas

        # Datapath
        datapath = LiteJESD204BLinkRXDapath(data_width,
            jesd_settings.octets_per_frame,
            jesd_settings.transport.k)
        self.submodules.datapath = datapath
        self.comb += source.eq(datapath.source)

        # Flow
        self.comb += [
            aligner.sink.eq(sink),
            cgs.sink.eq(aligner.source),
            ilas.sink.eq(aligner.source),
            datapath.sink.eq(aligner.source),
        ]

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="RECEIVE-CGS")
        fsm.act("RECEIVE-CGS",
            self.align.eq(1),
            ilas.reset.eq(1),
            datapath.deframer.reset.eq(1),
            datapath.descrambler.reset.eq(1),
            # Assert jsync in first LMFC after CGS
            If(self.lmfc_zero & cgs.valid,
                NextState("ASSERT-SYNC")
            )
        )
        fsm.act("ASSERT-SYNC",
            self.jsync.eq(1),
            ilas.reset.eq(1),
            datapath.deframer.reset.eq(1),
            datapath.descrambler.reset.eq(1),
            If(ilas.start.valid,
                ilas.reset.eq(0),
                NextState("RECEIVE-ILAS")
            )
        )
        fsm.act("RECEIVE-ILAS",
            self.jsync.eq(1),
            datapath.deframer.reset.eq(1),
            datapath.descrambler.reset.eq(1),
            If(ilas.done,
                NextState("RECEIVE-DATA")
            ).Elif(ilas_check & ~ilas.valid,
                NextState("RECEIVE-CGS")
            )
        )
        fsm.act("RECEIVE-DATA",
            self.jsync.eq(1),
            self.ready.eq(1),
            If(cgs.valid,
                NextState("RECEIVE-CGS")
            )
        )
