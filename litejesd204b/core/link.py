from collections import namedtuple

from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litejesd204b.common import *
from litejesd204b.phy.prbs import PRBS15Generator


Control = namedtuple("Control", "value")


class Scrambler(Module):
    """Scrambler
    cf section 5.2.3
    """
    def __init__(self, data_width):
        self.sink = sink = stream.Endpoint(data_layout(data_width))
        self.source = source = stream.Endpoint(data_layout(data_width))

        # # #

        state = Signal(15, reset=0x7fff)
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
            feedback.eq(full[15:15+data_width] ^ full[14:14+data_width] ^ swizzle_in)
        ]

        self.sync += \
            If(sink.valid & source.ready,
                source.valid.eq(1),
                swizzle_out.eq(feedback),
                state.eq(full)
            ).Elif(self.source.ready,
                source.valid.eq(0)
            )


class Framer(Module):
    """Framer
    """
    def __init__(self, data_width, octets_per_frame, frames_per_multiframe):
        self.sink = sink = stream.Endpoint(data_layout(data_width))
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        frame_width = octets_per_frame*8
        frames_per_clock = data_width//frame_width
        clocks_per_multiframe = frames_per_multiframe//frames_per_clock

        assert frame_width <= data_width # at least a frame per clock
        assert data_width%frame_width == 0 # multiple number of frame per clock
        assert frames_per_multiframe%frames_per_clock == 0 # multiframes aligned on clock

        frame_last = 0
        for i in range(data_width//8):
            if (i+1)%octets_per_frame == 0:
                frame_last |= (1<<i)

        counter = Signal(8)
        self.sync += \
            If(sink.valid & source.ready,
                If(source.multiframe_last != 0,
                    counter.eq(0)
                ).Else(
                    counter.eq(counter+1)
                )
            )

        self.comb += [
            sink.connect(source),
            source.frame_last.eq(frame_last),
            If(counter == (clocks_per_multiframe-1),
                source.multiframe_last.eq(1<<(data_width//8)-1)
            )
        ]


class AlignInserter(Module):
    """Alignment Character Inserter
    cf section 5.3.3.4
    """
    def __init__(self, data_width, scrambled=True):
        assert scrambled == True  # only supporting scrambled mode for now

        self.sink = sink = stream.Endpoint(link_layout(data_width))
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        self.comb += sink.connect(source)

        for i in range(data_width//8):
            self.comb += \
                If(sink.data[8*i:8*(i+1)] == control_characters["A"],
                    If(sink.multiframe_last[i],
                        source.ctrl[i].eq(1)
                    )
                ).Elif(sink.data[8*i:8*(i+1)] == control_characters["F"],
                    If(sink.frame_last[i],
                        source.ctrl[i].eq(1)
                    )
                )


class CGSGenerator(Module):
    """Code Group Synchronization
    """
    def __init__(self, data_width):
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        data = Signal(data_width)
        ctrl = Signal(data_width//8)
        for i in range(data_width//8):
            self.comb += [
                data[8*i:8*(i+1)].eq(control_characters["K"]),
                ctrl[i].eq(1)
            ]

        self.comb += [
            source.valid.eq(1),
            source.data.eq(data),
            source.ctrl.eq(ctrl)
        ]


class ILASGenerator(Module):
    """Initial Lane Alignment Sequence Generator
    cf section 5.3.3.5
    """
    def __init__(self, data_width,
                 octets_per_frame,
                 frames_per_multiframe,
                 configuration_data,
                 with_counter=True):
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        # compute ilas's octets

        octets_per_multiframe = octets_per_frame*frames_per_multiframe

        ilas_octets = []
        for i in range(4):
            if with_counter:
                multiframe = [i*octets_per_multiframe + j for j in range(octets_per_multiframe)]
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

        assert len(ilas_data_words) == octets_per_frame*frames_per_multiframe*4//octets_per_clock

        data_lut = Memory(data_width, len(ilas_data_words), init=ilas_data_words)
        data_port = data_lut.get_port(async_read=True)
        self.specials += data_lut, data_port

        ctrl_lut = Memory(data_width//8, len(ilas_ctrl_words), init=ilas_ctrl_words)
        ctrl_port = ctrl_lut.get_port(async_read=True)
        self.specials += ctrl_lut, ctrl_port

        # stream data/ctrl from lookup tables
        counter = Signal(max=len(ilas_data_words))
        self.comb += [
            source.last.eq(counter == (len(ilas_data_words)-1)),
            data_port.adr.eq(counter),
            ctrl_port.adr.eq(counter),
            source.data.eq(data_port.dat_r),
            source.ctrl.eq(ctrl_port.dat_r)
        ]
        source.valid.reset = 1
        self.sync += \
            If(source.valid & source.ready,
                source.valid.eq(~source.last),
                If(counter != len(ilas_data_words),
                    counter.eq(counter + 1)
                )
            )


class LiteJESD204BLinkTX(Module):
    """Link TX layer
    """
    def __init__(self, data_width, jesd_settings):
        self.start = Signal(reset=1)
        self.prbs = Signal()
        self.ready = Signal()
        self.cgs_done = Signal()

        self.sink = sink = stream.Endpoint(data_layout(data_width))
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        #  PRBS(optional)---+
        #                   +
        #  Init(CGS, ILAS)--+ mux --> source
        #                   +
        #  Datapath---------+

        # PRBS
        self.submodules.prbs_gen = PRBS15Generator(data_width)


        # Init

        cgs = CGSGenerator(data_width)
        ilas = ILASGenerator(data_width,
                             2, # FIXME octets_per_frame
                             jesd_settings.transport.k,
                             jesd_settings.get_configuration_data())
        self.submodules += cgs, ilas


        # Datapath

        scrambler = Scrambler(data_width)
        framer = Framer(data_width,
                        2, # FIXME octets_per_frame
                        jesd_settings.transport.k)
        inserter = AlignInserter(data_width)
        self.submodules += scrambler, framer, inserter
        self.comb += [
            sink.connect(scrambler.sink),
            scrambler.source.connect(framer.sink),
            framer.source.connect(inserter.sink)
        ]

        # FSM

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")

        # Init
        fsm.act("IDLE",
            If(self.prbs,
                NextState("PRBS")
            ).Elif(self.start,
                NextState("CGS")
            )
        )

        # PRBS
        fsm.act("PRBS",
            source.valid.eq(1),
            source.data.eq(self.prbs_gen.o),
            source.ctrl.eq(0)
        )

        # Code Group Synchronization
        fsm.act("CGS",
            source.valid.eq(cgs.source.valid),
            source.data.eq(cgs.source.data),
            source.ctrl.eq(cgs.source.ctrl),
            cgs.source.ready.eq(source.ready),
            If(self.cgs_done,
                NextState("ILAS")
            )
        )

        # Initial Lane Alignment Sequence
        fsm.act("ILAS",
            source.valid.eq(ilas.source.valid),
            source.data.eq(ilas.source.data),
            source.ctrl.eq(ilas.source.ctrl),
            ilas.source.ready.eq(source.ready),
            If(source.valid & source.ready & ilas.source.last,
                NextState("USER_DATA")
            )
        )

        # User Data
        fsm.act("USER_DATA",
            self.ready.eq(1),
            inserter.source.connect(source)
        )
