from litejesd204b.common import *


class LiteJESD204BDataLinkTx(Module):
    """JESD204 Data Link Tx layers
    """
    def __init__(self, dw):
        self.reset = Signal()
        self.start = Signal()
        self.ready = Signal()
        self.sync = Signal()

        self.sink = stream.Endpoint(data_link_layout(dw))
        self.source = stream.Endpoint(data_link_layout(dw))

        # # #

        self.fsm = fsm = ResetInserter()(FSM(reset_state="RESET"))
        self.submodules += fsm
        self.comb += fsm.reset.eq(self.reset)

        # Init
        fsm.act("RESET",
            If(self.start,
                NextState("CGS")
            )
        )

        # Code Group Syncronization
        fsm.act("CGS",
            self.source.valid.eq(1),
            self.source.data.eq(control_characters["K"]),
            self.source.charisk.eq(2**dw-1),
            If(~self.sync,
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
            self.ready.eq(1),
            self.sink.connect(self.source)
        )
