from math import ceil

from litex.gen import *
from litex.gen.genlib.cdc import MultiReg
from litex.gen.genlib.misc import WaitTimer
from litex.gen.genlib.fsm import FSM


class GTXInit(Module):
    def __init__(self, sys_clk_freq, rx):
        self.done = Signal()
        self.restart = Signal()

        # GTX signals
        self.cplllock = Signal()
        self.gtXxreset = Signal()
        self.Xxresetdone = Signal()
        self.Xxdlysreset = Signal()
        self.Xxdlysresetdone = Signal()
        self.Xxphaligndone = Signal()
        self.Xxuserrdy = Signal()

        # # #

        # Double-latch transceiver asynch outputs
        cplllock = Signal()
        Xxresetdone = Signal()
        Xxdlysresetdone = Signal()
        Xxphaligndone = Signal()
        self.specials += [
            MultiReg(self.cplllock, cplllock),
            MultiReg(self.Xxresetdone, Xxresetdone),
            MultiReg(self.Xxdlysresetdone, Xxdlysresetdone),
            MultiReg(self.Xxphaligndone, Xxphaligndone),
        ]

        # Deglitch FSM outputs driving transceiver asynch inputs
        gtXxreset = Signal()
        Xxdlysreset = Signal()
        Xxuserrdy = Signal()
        self.sync += [
            self.gtXxreset.eq(gtXxreset),
            self.Xxdlysreset.eq(Xxdlysreset),
            self.Xxuserrdy.eq(Xxuserrdy)
        ]

        # After configuration, transceiver resets have to stay low for
        # at least 500ns (see AR43482)
        startup_cycles = ceil(500*sys_clk_freq/1000000000)
        startup_timer = WaitTimer(startup_cycles)
        self.submodules += startup_timer

        self.debug = Signal(32)

        startup_fsm = ResetInserter()(FSM(reset_state="INITIAL"))
        self.submodules += startup_fsm

        ready_timer = WaitTimer(1*sys_clk_freq//1000)
        self.submodules += ready_timer
        self.comb += [
            ready_timer.wait.eq(~self.done & ~startup_fsm.reset),
            startup_fsm.reset.eq(self.restart | ready_timer.done),
        ]

        if rx:
            cdr_stable_timer = WaitTimer(1024)
            self.submodules += cdr_stable_timer

        Xxphaligndone_r = Signal(reset=1)
        Xxphaligndone_rising = Signal()
        self.sync += Xxphaligndone_r.eq(Xxphaligndone)
        self.comb += Xxphaligndone_rising.eq(Xxphaligndone & ~Xxphaligndone_r)

        startup_fsm.act("INITIAL",
            self.debug.eq(0),
            startup_timer.wait.eq(1),
            If(startup_timer.done, NextState("RESET_GTX"))
        )
        startup_fsm.act("RESET_GTX",
            self.debug.eq(1),
            gtXxreset.eq(1),
            NextState("WAIT_CPLL")
        )
        startup_fsm.act("WAIT_CPLL",
            self.debug.eq(2),
            gtXxreset.eq(1),
            If(cplllock, NextState("RELEASE_RESET"))
        )
        # Release GTX reset and wait for GTX resetdone
        # (from UG476, GTX is reset on falling edge
        # of gtXxreset)
        if rx:
            startup_fsm.act("RELEASE_RESET",
                self.debug.eq(3),
                Xxuserrdy.eq(1),
                cdr_stable_timer.wait.eq(1),
                If(Xxresetdone & cdr_stable_timer.done, NextState("ALIGN"))
            )
        else:
            startup_fsm.act("RELEASE_RESET",
                self.debug.eq(3),
                Xxuserrdy.eq(1),
                If(Xxresetdone, NextState("ALIGN"))
            )
        # Start delay alignment (pulse)
        startup_fsm.act("ALIGN",
            self.debug.eq(4),
            Xxuserrdy.eq(1),
            Xxdlysreset.eq(1),
            NextState("WAIT_ALIGN")
        )
        # Wait for delay alignment
        startup_fsm.act("WAIT_ALIGN",
            self.debug.eq(5),
            Xxuserrdy.eq(1),
			Xxdlysreset.eq(1),
            If(Xxdlysresetdone, NextState("WAIT_FIRST_ALIGN_DONE"))
        )
        # Wait 2 rising edges of Xxphaligndone
        # (from UG476 in buffer bypass config)
        startup_fsm.act("WAIT_FIRST_ALIGN_DONE",
            self.debug.eq(6),
            Xxuserrdy.eq(1),
            If(Xxphaligndone_rising, NextState("WAIT_SECOND_ALIGN_DONE"))
        )
        startup_fsm.act("WAIT_SECOND_ALIGN_DONE",
            self.debug.eq(7),
            Xxuserrdy.eq(1),
            If(Xxphaligndone_rising, NextState("READY"))
        )
        startup_fsm.act("READY",
            self.debug.eq(8),
            Xxuserrdy.eq(1),
            self.done.eq(1)
        )
