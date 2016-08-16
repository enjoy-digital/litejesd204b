from litejesd204b.common import *


class LiteJESD204BScrambler(Module):
    """JESD204 Scrambler
    """
    def __init__(self):
        # TODO (optional), polynom = 1 + X^14 + X^15


class LiteJESD204BCharacterRemplacement(Module):
    """JESD204 Character Remplacement
    """
    def __init__(self):
        # TODO
        # if not scrambled:
        #   if dn = dn-1:
        #     if end of multiframe:
        #       dn = A
        #     if end of frame:
        #       dn = F
        # if scrambled:
        #   if dn = 0x7c:
        #     if end of multiframe:
        #       dn = A
        #   if dn = 0xfc:
        #     if end of frame:
        #       dn = F


class LiteJESD204BILAS(Module):
    """JESD204 Initial Lane Alignment Sequence
    """
    def __init__(self):
        # TODO
        # 4 or more multiframes
        # last character of each multiframe = A
        # first, third and fourth multiframes first data = R
        # for ADI DACs, data in between is a ramp
        # second multiframe = R, Q, followed by link parameters
        # after the last A character of the last ILAS multiframe, user data starts


class LiteJESD204BDataLinkTx(Module):
    """JESD204 Data Link Tx layer
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
