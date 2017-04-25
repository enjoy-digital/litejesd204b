from collections import namedtuple

from litex.gen import *

from litejesd204b.common import control_characters


Control = namedtuple("Control", "value")


def link_layout(data_width):
    layout = [
        ("data", data_width),
        ("ctrl", data_width//8),

        ("last", 1),

        ("frame_last", data_width//8),
        ("multiframe_last", data_width//8)
    ]
    return layout


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

        swizzle_in = Signal(data_width)
        swizzle_out = Signal(data_width)
        self.comb += [
            swizzle_in.eq(Cat(*[sink.data[data_width-8*(i+1):data_width-8*i]
                for i in range(data_width//8)])),
            source.data.eq(Cat(*[swizzle_out[data_width-8*(i+1):data_width-8*i]
                for i in range(data_width//8)]))
        ]

        self.comb += [
            full.eq(Cat(feedback, state)),
            feedback.eq(full[15:15+data_width] ^
                        full[14:14+data_width] ^
                        swizzle_in)
        ]

        self.sync += [
            self.valid.eq(1),
            swizzle_out.eq(feedback),
            state.eq(full)
        ]


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
                # last scrambled octet in a multiframe equals 0x7c
                If(sink.data[8*i:8*(i+1)] == control_characters["A"],
                    If(sink.multiframe_last[i],
                        source.ctrl[i].eq(1)
                    )
                # last scrambled octet in a frame but not at the end of a
                # multiframe equals 0xfc
                ).Elif(sink.data[8*i:8*(i+1)] == control_characters["F"],
                    If(sink.frame_last[i] & ~sink.multiframe_last[i],
                        source.ctrl[i].eq(1)
                    )
                )
            ]


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


@ResetInserter()
class ILASGenerator(Module):
    """Initial Lane Alignment Sequence Generator
    cf section 5.3.3.5
    """
    def __init__(self, data_width,
                 octets_per_frame,
                 frames_per_multiframe,
                 configuration_data,
                 with_counter=True):
        self.source = source = Record(link_layout(data_width))

        # # #

        # compute ilas's octets

        octets_per_multiframe = octets_per_frame*frames_per_multiframe

        ilas_octets = []
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
            ilas_octets += multiframe

        # pack ilas's octets in a lookup table

        octets_per_clock = data_width//8

        ilas_data_words = []
        ilas_ctrl_words = []
        for i in range(len(ilas_octets)//octets_per_clock):
            data_word = 0
            ctrl_word = 0
            for j in range(octets_per_clock):
                octet = ilas_octets[i*octets_per_clock+j]
                if isinstance(octet, Control):
                    data_word |= (octet.value << 8*j)
                    ctrl_word |= (1 << j)
                else:
                    data_word |= (octet << 8*j)
            ilas_data_words.append(data_word)
            ilas_ctrl_words.append(ctrl_word)

        assert len(ilas_data_words) == (octets_per_frame*
                                        frames_per_multiframe*
                                        4//octets_per_clock)

        data_lut = Memory(data_width, len(ilas_data_words), init=ilas_data_words)
        data_port = data_lut.get_port(async_read=True)
        self.specials += data_lut, data_port

        ctrl_lut = Memory(data_width//8, len(ilas_ctrl_words), init=ilas_ctrl_words)
        ctrl_port = ctrl_lut.get_port(async_read=True)
        self.specials += ctrl_lut, ctrl_port

        # stream data/ctrl from lookup tables
        counter = Signal(max=len(ilas_data_words)+1)
        self.comb += [
            source.last.eq(counter == (len(ilas_data_words)-1)),
            data_port.adr.eq(counter),
            ctrl_port.adr.eq(counter),
            source.data.eq(data_port.dat_r),
            source.ctrl.eq(ctrl_port.dat_r)
        ]
        self.sync += \
            If(counter != len(ilas_data_words),
                counter.eq(counter + 1)
            )


class LiteJESD204BLinkTX(Module):
    """Link TX layer
    """
    def __init__(self, data_width, jesd_settings, n=0):
        self.jsync = Signal()
        self.ready = Signal()

        self.sink = sink = Record([("data", data_width)])
        self.source = source = Record(link_layout(data_width))

        # # #

        #   CGS-----+
        #   ILAS----+-mux(fsm) --> source
        #  Datapath-+

        # Init
        cgs = CGSGenerator(data_width)
        ilas = ILASGenerator(data_width,
                             jesd_settings.octets_per_frame,
                             jesd_settings.transport.k,
                             jesd_settings.get_configuration_data(n))
        self.submodules += cgs, ilas


        # Datapath
        self.scrambler = scrambler = Scrambler(data_width)
        self.framer = framer = Framer(data_width,
                                      jesd_settings.octets_per_frame,
                                      jesd_settings.transport.k)
        self.inserter = inserter = AlignInserter(data_width)
        self.submodules += scrambler, framer, inserter
        self.comb += [
            scrambler.sink.eq(sink),
            framer.sink.eq(scrambler.source),
            inserter.sink.eq(framer.source)
        ]

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="CGS")

        # Code Group Synchronization
        fsm.act("CGS",
            ilas.reset.eq(1),
            scrambler.reset.eq(1),
            framer.reset.eq(1),
            source.data.eq(cgs.source.data),
            source.ctrl.eq(cgs.source.ctrl),
            If(self.jsync,
                NextState("ILAS")
            )
        )

        # Initial Lane Alignment Sequence
        fsm.act("ILAS",
            framer.reset.eq(1),
            source.data.eq(ilas.source.data),
            source.ctrl.eq(ilas.source.ctrl),
            If(ilas.source.last,
                NextState("USER_DATA")
            )
        )

        # User Data
        fsm.act("USER_DATA",
            ilas.reset.eq(1),
            self.ready.eq(1),
            source.eq(inserter.source),
        )
