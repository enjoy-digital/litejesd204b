from collections import namedtuple

from migen import *

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
        self.sink = sink = Record([("data", data_width)])
        self.source = source = Record([("data", data_width)])
        self.valid = Signal()
        self.latency = 1

        # # #

        state = Signal(15, reset=seed)
        feedback = Signal(data_width)
        full = Signal(data_width+15)

        self.comb += [
            full.eq(Cat(feedback, state)),
            feedback.eq(full[15:15+data_width] ^
                        full[14:14+data_width] ^
                        swizzle(sink.data, data_width))
        ]

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
        self.sink = sink = Record([("data", data_width)])
        self.source = source = Record([("data", data_width)])
        self.valid = Signal()
        self.latency = 1

        # # #

        state = Signal(15, reset=seed)
        feedback = Signal(data_width)
        full = Signal(data_width+15)

        self.comb += [
            full.eq(Cat(swizzle(sink.data, data_width), state)),
            feedback.eq(full[15:15+data_width] ^
                        full[14:14+data_width] ^
                        full[0:32])
        ]

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
        self.sink = sink = Record([("data", data_width)])
        self.source = source = Record(link_layout(data_width))
        self.latency = 0

        # # #

        frame_width = octets_per_frame*8
        frames_per_clock = data_width//frame_width
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
        self.sink = sink = Record(link_layout(data_width))
        self.source = source = Record([("data", data_width)])
        self.latency = 0

        # # #

        frame_width = octets_per_frame*8
        frames_per_clock = data_width//frame_width
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
        self.sink = sink = Record(link_layout(data_width))
        self.source = source = Record(link_layout(data_width))
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


class AlignRemover(Module):
    """Alignment Character Remover
    cf section 5.3.3.4.3
    """
    def __init__(self, data_width):
        self.sink = sink = Record(link_layout(data_width))
        self.source = source = Record(link_layout(data_width))
        self.latency = 0

        # # #

        # recopy data and set ctrl to 0
        self.comb += source.eq(sink)
        for i in range(data_width//8):
            self.comb += source.ctrl.eq(0)

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
        self.sink = sink = Record(link_layout(data_width))
        self.error = Signal()

        # # #

        data = Signal(data_width)
        ctrl = Signal(data_width//8)
        for i in range(data_width//8):
            self.comb += [
                If(sink.data[8*i:8*(i+1)] != control_characters["K"],
                    self.error.eq(1)
                ),
                If(sink.ctrl[i] != 1,
                    self.error.eq(1)
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
                multiframe = [i*octets_per_multiframe + j
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
        self.sink = sink = Record(link_layout(data_width))
        self.done = Signal()
        self.errors = Signal(16)

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

        # compare data/ctrl with lookup tables
        counter = Signal(max=len(self.data_words)+1)
        self.comb += [
            data_port.adr.eq(counter),
            ctrl_port.adr.eq(counter),
        ]
        self.sync += [
            If(counter != len(self.data_words),
                counter.eq(counter + 1),
                If(sink.data != data_port.dat_r,
                    self.errors.eq(self.errors + 1)
                ),
                If(sink.ctrl != ctrl_port.dat_r,
                    self.errors.eq(self.errors + 1)
                )
            )
        ]

        # done
        self.comb += self.done.eq(counter == len(self.data_words))

# Link TX ------------------------------------------------------------------------------------------

@ResetInserter()
class LiteJESD204BLinkTX(Module):
    """Link TX layer
    """
    def __init__(self, data_width, jesd_settings, n=0):
        self.jsync = Signal() # input
        self.jref = Signal()  # input
        self.ready = Signal() # output

        self.sink = sink = Record([("data", data_width)])
        self.source = source = Record(link_layout(data_width))

        # # #

        # Control (CGS + ILAS)
        cgs = CGSGenerator(data_width)
        ilas = ILASGenerator(data_width,
                             jesd_settings.octets_per_lane,
                             jesd_settings.transport.k,
                             jesd_settings.get_configuration_data(n))
        self.submodules += cgs, ilas


        # Datapath
        scrambler = Scrambler(data_width)
        framer = Framer(data_width, jesd_settings.octets_per_frame, jesd_settings.transport.k)
        alignment = AlignInserter(data_width)
        self.submodules += scrambler, framer, alignment
        self.comb += [
            scrambler.sink.eq(sink),
            framer.sink.eq(scrambler.source),
            alignment.sink.eq(framer.source)
        ]

        jsync = Signal()
        jref = Signal()
        jref_d = Signal()
        jref_rising = Signal()
        self.sync += [
            jsync.eq(self.jsync),
            jref.eq(self.jref),
            jref_d.eq(jref)
        ]
        self.comb += jref_rising.eq(jref & ~jref_d)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="SEND-CGS")

        # Code Group Synchronization
        fsm.act("SEND-CGS",
            ilas.reset.eq(1),
            scrambler.reset.eq(1),
            framer.reset.eq(1),
            source.data.eq(cgs.source.data),
            source.ctrl.eq(cgs.source.ctrl),
            # start ILAS on first LMFC after jsync is asserted
            If(jsync & jref_rising,
                NextState("SEND-ILAS")
            )
        )

        # Initial Lane Alignment Sequence
        fsm.act("SEND-ILAS",
            framer.reset.eq(1),
            source.data.eq(ilas.source.data),
            source.ctrl.eq(ilas.source.ctrl),
            If(ilas.source.last,
                NextState("SEND-DATA")
            )
        )

        # Data
        fsm.act("SEND-DATA",
            ilas.reset.eq(1),
            self.ready.eq(1),
            source.eq(alignment.source),
        )


# Link RX ------------------------------------------------------------------------------------------

@ResetInserter()
class LiteJESD204BLinkRX(Module):
    # WORK IN PROGRESS - UNTESTED
    """Link RX layer
    """
    def __init__(self, data_width, jesd_settings, n=0):
        self.jsync = Signal() # output
        self.jref = Signal()  # input
        self.ready = Signal() # output

        self.sink = sink = Record(link_layout(data_width))
        self.source = source = Record([("data", data_width)])

        # # #

        # Control (CGS + ILAS)
        cgs = CGSChecker(data_width)
        ilas = ILASChecker(data_width,
                             jesd_settings.octets_per_lane,
                             jesd_settings.transport.k,
                             jesd_settings.get_configuration_data(n))
        self.submodules += cgs, ilas

        self.cgs = cgs

        # Datapath
        descrambler = Descrambler(data_width)
        deframer = Deframer(data_width, jesd_settings.octets_per_frame, jesd_settings.transport.k)
        alignment = AlignRemover(data_width)
        self.submodules += descrambler, deframer, alignment
        self.comb += [
            source.eq(descrambler.source),
            descrambler.sink.eq(deframer.source),
            deframer.sink.eq(alignment.source)
        ]

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="RECEIVE-CGS")

        # Code Group Synchronization
        fsm.act("RECEIVE-CGS",
            ilas.reset.eq(1),
            descrambler.reset.eq(1),
            deframer.reset.eq(1),
            cgs.sink.data.eq(sink.data),
            cgs.sink.ctrl.eq(sink.ctrl),
            If(~cgs.error,
                NextState("RECEIVE-ILAS")
            )
        )
        fsm.act("WAIT-ILAS",
            self.jsync.eq(1),
            ilas.reset.eq(1),
            descrambler.reset.eq(1),
            deframer.reset.eq(1),
            ilas.sink.data.eq(sink.data),
            ilas.sink.ctrl.eq(sink.ctrl),
            If(cgs.error,
                ilas.reset.eq(0),
                NextState("RECEIVE-ILAS")
            )
        )

        # Initial Lane Alignment Sequence
        fsm.act("RECEIVE-ILAS",
            self.jsync.eq(1),
            descrambler.reset.eq(1),
            deframer.reset.eq(1),
            ilas.sink.data.eq(sink.data),
            ilas.sink.ctrl.eq(sink.ctrl),
            If(ilas.done,
                If(ilas.errors,
                    NextState("RECEIVE-CGS")
                ).Else(
                    NextState("RECEIVE-DATA")
                )
            )
        )

        # Data
        fsm.act("RECEIVE-DATA",
            ilas.reset.eq(1),
            self.jsync.eq(1),
            self.ready.eq(1),
            alignment.sink.eq(sink),
        )
