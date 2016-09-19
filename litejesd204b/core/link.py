from collections import namedtuple

from litex.gen import *
from litex.gen.genlib.cdc import PulseSynchronizer, MultiReg
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litejesd204b.common import *


Control = namedtuple("Control", "value")


class _PulseSynchronizer(PulseSynchronizer):
    def __init__(self, i, idomain, o, odomain):
        PulseSynchronizer.__init__(self, idomain, odomain)
        self.comb += [
            self.i.eq(i),
            o.eq(self.o)
        ]


@ResetInserter()
class Scrambler(Module):
    """Scrambler
    cf section 5.2.3
    """
    def __init__(self, data_width):
        self.sink = sink = stream.Endpoint([("data", data_width)])
        self.source = source = stream.Endpoint([("data", data_width)])

        # # #

        state = Signal(15, reset=0x7fff)
        feedback = Signal(data_width)
        full = Signal(data_width+15)

        self.comb += [
            full.eq(Cat(feedback, state)),
            feedback.eq(full[15:15+data_width] ^ full[14:14+data_width] ^ sink.data)
        ]

        self.sync += [
            If(sink.valid & source.ready,
                source.valid.eq(1),
                source.data.eq(feedback),
                state.eq(full)
            ).Elif(self.source.ready,
                source.valid.eq(0)
            )
        ]


@ResetInserter()
class Framer(Module):
    """Framer
    """
    def __init__(self, data_width, octets_per_frame, frames_per_multiframe):
        self.sink = sink = stream.Endpoint([("data", data_width)])
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        frame_width = octets_per_frame*8
        frames_per_clock = data_width/frame_width

        assert frame_width <= data_width # at least a frame per clock
        assert data_width%frame_width == 0 # multiple number of frame per clock
        assert frames_per_multiframe%frames_per_clock == 0 # multiframes aligned on clock

        frame_last = 0
        for i in range(data_width//8):
            if (i+1)%octets_per_frame == 0:
                frame_last |= (1<<i)

        frame_counter = Signal(8)
        self.sync += [
            If(sink.valid & source.ready,
                If(source.multiframe_last != 0,
                    frame_counter.eq(0)
                ).Else(
                    frame_counter.eq(frame_counter+1)
                )
            )
        ]

        self.comb += [
            sink.connect(source),
            source.frame_last.eq(frame_last),
            If(frame_counter == (frames_per_multiframe-1),
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
            self.comb += [
                If(sink.data[8*i:8*(i+1)] == control_characters["A"],
                    If(sink.multiframe_last[i],
                        source.ctrl[i].eq(1)
                    )
                ).Elif(sink.data[8*i:8*(i+1)] == control_characters["F"],
                    If(sink.frame_last[i],
                        source.ctrl[i].eq(1)
                    )
                )
            ]


@ResetInserter()
class ILASGenerator(Module):
    """Initial Lane Alignment Sequence Generator
    cf section 5.3.3.5
    """
    def __init__(self, data_width, octets_per_frame, frames_per_multiframe, configuration_data):
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        # compute ilas's octets

        octets_per_multiframe = octets_per_frame*frames_per_multiframe

        ilas_octets = []
        for i in range(4):
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
                data_word = data_word << 8
                ctrl_word = ctrl_word << 1
                octet = ilas_octets[i*octets_per_clock+j]
                if isinstance(octet, Control):
                    data_word |= octet.value
                    ctrl_word |= 1
                else:
                    data_word |= octet
            ilas_data_words.append(data_word)
            ilas_ctrl_words.append(ctrl_word)

        assert len(ilas_data_words) == octets_per_frame*frames_per_multiframe*4//octets_per_clock

        data_lut = Memory(data_width, len(ilas_data_words), init=ilas_data_words)
        data_port = data_lut.get_port()
        self.specials += data_lut, data_port

        ctrl_lut = Memory(data_width//8, len(ilas_ctrl_words), init=ilas_ctrl_words)
        ctrl_port = ctrl_lut.get_port()
        self.specials += ctrl_lut, ctrl_port

        # stream data/ctrl from lookup tables
        counter = Signal(max=len(ilas_data_words))
        self.comb += [
            source.valid.eq(counter != len(ilas_data_words)),
            source.last.eq(counter == (len(ilas_data_words)-1)),
            data_port.adr.eq(counter),
            ctrl_port.adr.eq(counter),
            source.data.eq(data_port.dat_r),
            source.ctrl.eq(ctrl_port.dat_r)
        ]
        self.sync += \
            If(source.valid & source.ready,
                If(counter != len(ilas_data_words),
                    counter.eq(counter + 1)
                )
            )


class LiteJESD204BLinkTX(Module, AutoCSR):
    """Link TX layer
    """
    def __init__(self, data_width, jesd_settings):
        self.reset = CSR()
        self.start = CSR()
        self.ready = CSRStatus()

        self.ext_sync = Signal()

        self.sink = sink = stream.Endpoint([("data", data_width)])
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        # CSRs
        reset = Signal()
        start = Signal()
        ready = Signal()

        self.submodules += [
            _PulseSynchronizer(self.reset.re, "sys", reset, "link_tx"),
            _PulseSynchronizer(self.start.re, "sys", start, "link_tx")
        ]
        self.specials += MultiReg(ready, self.ready.status, "sys")

        #  Ctrl(CGS, ILAS)--+
        #                   + mux --> source
        #  Datapath --------+


        # Datapath

        # sink --> scrambler --> framer --> align_inserter
        self.submodules.scrambler = Scrambler(data_width)
        self.submodules.framer = Framer(data_width,
                                        2, # FIXME octets_per_frame
                                        jesd_settings.transport.k)
        self.submodules.inserter = AlignInserter(data_width)
        self.comb += [
            self.sink.connect(self.scrambler.sink),
            self.scrambler.source.connect(self.framer.sink),
            self.framer.source.connect(self.inserter.sink)
        ]

        # Ctrl

        self.fsm = fsm = ResetInserter()(FSM(reset_state="RESET"))
        self.submodules += fsm
        self.comb += fsm.reset.eq(reset)


        self.submodules.ilas = ILASGenerator(data_width,
                                             2, # FIXME octets_per_frame
                                             jesd_settings.transport.k,
                                             jesd_settings.get_configuration_data())

        # Init
        fsm.act("RESET",
            self.ilas.reset.eq(1),
            self.scrambler.reset.eq(1),
            self.framer.reset.eq(1),
            If(start,
                NextState("CGS")
            )
        )

        # Code Group Synchronization
        cgs_data = Signal(data_width)
        cgs_ctrl = Signal(data_width//8)
        for i in range(data_width//8):
            self.comb += [
                cgs_data[8*i:8*(i+1)].eq(control_characters["K"]),
                cgs_ctrl[i].eq(1)
            ]
        fsm.act("CGS",
            source.valid.eq(1),
            source.data.eq(cgs_data),
            source.ctrl.eq(cgs_ctrl),
            If(~self.ext_sync, # FIXME when doing det-lat
                NextState("ILAS")
            )
        )

        # Initial Lane Alignment Sequence
        fsm.act("ILAS",
            source.valid.eq(self.ilas.source.valid),
            source.data.eq(self.ilas.source.data),
            source.ctrl.eq(self.ilas.source.ctrl),
            If(source.valid & source.ready & self.ilas.source.last,
                NextState("USER_DATA")
            )
        )

        # User Data
        fsm.act("USER_DATA",
            ready.eq(1),
            self.inserter.source.connect(source)
        )
