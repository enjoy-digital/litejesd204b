from litex.gen import *
from litex.soc.interconnect import stream
from litex.soc.interconnect.csr import *

from litejesd204b.common import *


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

        if data_width < frame_width:
            raise NotImplementedError
        if data_width%frame_width:
            raise NotImplementedError
        if frames_per_multiframe%frames_per_clock:
            raise NotImplementedError
        
        frame_last = 0
        for i in range(data_width//8):
            if (i+1)%octets_per_frame == 0:
                frame_last |= (1<<(8*i))

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
        if scrambled == False:
            raise NotImplementedError

        self.sink = sink = stream.Endpoint(link_layout(data_width))
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        for i in range(data_width//8):
            self.comb += [
                sink.connect(source),
                If(sink.data[8*i:8*(i+1)] == 0x7c,
                    If(sink.multiframe_last[i],
                        source.data[8*i:8*(i+1)].eq(control_characters["A"]),
                        source.ctrl[i].eq(1)
                    )
                ).Elif(sink.data[8*i:8*(i+1)] == 0xfc,
                    If(sink.frame_last,
                        source.data[8*i:8*(i+1)].eq(control_characters["F"]),
                        source.ctrl[i].eq(1)
                    )
                )
            ]


class ILASGenerator(Module):
    """Initial Lane Alignment Sequence Generator
    """
    def __init__(self):
        # TODO
        # 4 or more multiframes
        # last character of each multiframe = A
        # first, third and fourth multiframes first data = R
        # for ADI DACs, data in between is a ramp
        # second multiframe = R, Q, followed by link parameters
        # after the last A character of the last ILAS multiframe, user data starts
        pass


class LiteJESD204BLinkTX(Module, AutoCSR):
    """Link TX layer
    """
    def __init__(self, data_width):
        self.reset = CSR()
        self.start = CSR()
        self.ready = CSRStatus()

        self.ext_sync = Signal()

        self.sink = sink = stream.Endpoint([("data", data_width)])
        self.source = source = stream.Endpoint(link_layout(data_width))

        # # #

        #  Ctrl(CGS, ILAS)--+
        #                   + mux --> source
        #  Datapath --------+


        # Datapath

        # sink --> scrambler --> framer --> align_inserter
        self.submodules.scrambler = Scrambler(data_width)
        self.submodules.framer = Framer(data_width, 2, 16) # FIXME
        self.submodules.inserter = AlignInserter(data_width)
        self.comb += [
            self.sink.connect(self.scrambler.sink),
            self.scrambler.source.connect(self.framer.sink),
            self.framer.source.connect(self.inserter.sink)
        ]

        # Ctrl

        self.fsm = fsm = ResetInserter()(FSM(reset_state="RESET"))
        self.submodules += fsm
        self.comb += fsm.reset.eq(self.reset.re)

        # Init
        fsm.act("RESET",
            If(self.start.re,
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
            # TODO: add ILAS generator
            NextState("USER_DATA")
        )

        # User Data
        fsm.act("USER_DATA",
            self.ready.status.eq(1),
            self.inserter.source.connect(source)
        )
