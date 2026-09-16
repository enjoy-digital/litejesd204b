#
# This file is part of LiteJESD204B
#
# Copyright (c) 2026 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *

# JESD204C (64b66b) link layer.
#
# Each link beat is one 66-bit block: 64 bits of payload and a 2-bit sync header. The sync headers
# convey, one bit per block, a 32-bit sync word per multiblock (32 blocks): the end-of-multiblock
# sequence (00001), the CRC-12 of the previous multiblock, the command channel bits and the
# end-of-extended-multiblock (EoEMB) marker. There is no CGS/ILAS/SYNC~: lane alignment comes from
# sync header lock (per lane, in the PHY RX clock domain) and extended multiblock lock (in the link
# clock domain), with deterministic latency provided by the LEMC counter (LMFC equivalent).
#
# The scrambler, CRC and sync word definitions follow JESD204C with the same formulation as ADI's
# open source JESD204 HDL (interoperability reference).

# Layout -------------------------------------------------------------------------------------------

def link_204c_layout():
    return [
        ("data",   64),
        ("header",  2),
    ]

# Helpers ------------------------------------------------------------------------------------------

def reverse_octets(signal):
    """Octets Reorder (first octet <-> most significant octet)"""
    assert len(signal) == 64
    return Cat(*reversed([signal[8*i:8*(i+1)] for i in range(8)]))

# Scrambling ---------------------------------------------------------------------------------------

class Scrambler64b66b(Module):
    """Scrambler/Descrambler
    cf JESD204C 64b66b self-synchronous scrambling (x^58 + x^39 + 1)
    """
    def __init__(self, descramble=False):
        self.enable = Signal(reset=1)
        self.sink   = sink   = Record([("data", 64)])
        self.source = source = Record([("data", 64)])
        self.latency = 0

        # # #

        # 64-bit parallel implementation, most significant bit processed first: the output is
        # combinational (latency 0) and the 58-bit state is registered. The descrambler is
        # self-synchronizing, no seed/reset coordination is needed.
        #
        # full = {state, word} with word = feedback (scrambler) or data_in (descrambler):
        # feedback[j] = full[58+j] ^ full[39+j] (j < 25) ^ data_in[j]. The registered state is
        # pre-folded (state <= full[57:0] ^ full[38:0] << 19) so that the single full[58+j] tap also
        # covers the x^39 term for j >= 25.
        state    = Signal(58, reset=(1 << 57))
        feedback = Signal(64)
        full     = Signal(64 + 58)

        self.comb += [
            full.eq(Cat(sink.data if descramble else feedback, state)),
            feedback.eq(full[58:122] ^ Cat(full[39:64], C(0, 39)) ^ sink.data),
            If(self.enable,
                source.data.eq(feedback),
            ).Else(
                source.data.eq(sink.data),
            )
        ]
        self.sync += state.eq(full[0:58] ^ Cat(C(0, 19), full[0:39]))


class Descrambler64b66b(Scrambler64b66b):
    def __init__(self):
        Scrambler64b66b.__init__(self, descramble=True)

# CRC-12 -------------------------------------------------------------------------------------------

class CRC12(Module):
    """CRC-12
    cf JESD204C sync word (CRC-12 mode)
    """
    def __init__(self):
        self.init  = Signal()
        self.data  = Signal(64)
        self.value = Signal(12)

        # # #

        # 64 bits per cycle, computed over the scrambled payload. init restarts the accumulation
        # with the current cycle's data; value (registered) then holds the CRC of the completed span
        # on the same cycle init is asserted for the next span.
        #
        # full = {init ? 0 : state, feedback} with feedback[j] = data[j] ^ full[12+j] ^ full[11+j]
        # ^ full[10+j] ^ full[9+j] ^ full[4+j] ^ full[3+j] (taps beyond the 64-bit word excluded)
        # and state <= full[11:0] ^ full[10:0] << 1 ^ full[9:0] << 2 ^ full[8:0] << 3
        # ^ full[3:0] << 8 ^ full[2:0] << 9.
        state    = Signal(12)
        feedback = Signal(64)
        full     = Signal(64 + 12)

        self.comb += [
            full.eq(Cat(feedback, Mux(self.init, 0, state))),
            feedback.eq(self.data ^
                full[12:76] ^
                Cat(full[11:64], C(0, 11)) ^
                Cat(full[10:64], C(0, 10)) ^
                Cat(full[ 9:64], C(0,  9)) ^
                Cat(full[ 4:64], C(0,  4)) ^
                Cat(full[ 3:64], C(0,  3))
            ),
            self.value.eq(state),
        ]
        self.sync += state.eq(
            full[0:12] ^
            Cat(C(0, 1), full[0:11]) ^
            Cat(C(0, 2), full[0:10]) ^
            Cat(C(0, 3), full[0: 9]) ^
            Cat(C(0, 8), full[0: 4]) ^
            Cat(C(0, 9), full[0: 3])
        )

# Sync Word ----------------------------------------------------------------------------------------

class SyncWordTX(Module):
    """Sync Word Generator
    cf JESD204C sync header stream (CRC-12 mode)
    """
    def __init__(self):
        self.mb_start = Signal()      # First block of a multiblock.
        self.eoemb    = Signal()      # Current multiblock is the last of the EMB.
        self.crc12    = Signal(12)    # CRC of the previous multiblock.
        self.cmd      = Signal(7)     # Command channel bits (0 when unused).
        self.header   = Signal(2)

        # # #

        # The 32-bit sync word is loaded on mb_start (first block of a multiblock) and shifted out
        # MSB first, one bit per block, encoded in the sync header as {~bit, bit} (sync bit 1 ->
        # header 0b01, sync bit 0 -> header 0b10).
        sync_word = Signal(32)
        self.sync += [
            If(self.mb_start,
                sync_word.eq(Cat(
                    # LSB first.
                    C(0b00001, 5),                   # [4:0]   EoMB sequence.
                    self.cmd[0:3],                   # [7:5]   cmd[2:0].
                    C(1, 1),                         # [8]     pilot.
                    self.eoemb,                      # [9]     EoEMB.
                    C(1, 1),                         # [10]    pilot.
                    self.cmd[3],                     # [11]    cmd[3].
                    C(1, 1),                         # [12]    pilot.
                    self.cmd[4:7],                   # [15:13] cmd[6:4].
                    C(1, 1),                         # [16]    pilot.
                    self.crc12[0:3],                 # [19:17] crc[2:0].
                    C(1, 1),                         # [20]    pilot.
                    self.crc12[3:6],                 # [23:21] crc[5:3].
                    C(1, 1),                         # [24]    pilot.
                    self.crc12[6:9],                 # [27:25] crc[8:6].
                    C(1, 1),                         # [28]    pilot.
                    self.crc12[9:12],                # [31:29] crc[11:9].
                )),
            ).Else(
                sync_word.eq(Cat(C(0, 1), sync_word[:31])), # Shift MSB first.
            )
        ]
        self.comb += self.header.eq(Cat(sync_word[31], ~sync_word[31])) # {~bit, bit}.


class SyncWordRX(Module):
    """Sync Word Receiver
    cf JESD204C sync header stream (CRC-12 mode) / extended multiblock alignment
    """
    def __init__(self, beats_per_emb, thresh_emb_err=8):
        self.sh_lock     = Signal()
        self.header      = Signal(2)
        self.emb_lock    = Signal()
        self.valid_eomb  = Signal()
        self.valid_eoemb = Signal()
        self.mid_emb     = Signal() # Mid extended multiblock position strobe.
        self.crc12       = Signal(12)
        self.cmd         = Signal(7)
        self.state       = Signal(2)        # 0=INIT, 1=HUNT, 2=LOCK (diagnostic).
        self.eomb_seen   = Signal()         # Sticky: an EoMB was ever detected (diagnostic).

        # # #

        header_bit = Signal()
        sync_word  = Signal(32)
        eomb       = Signal()
        eoemb      = Signal()
        sh_count   = Signal(max=beats_per_emb)

        self.comb += header_bit.eq(self.header == 0b01)
        self.sync += sync_word.eq(Cat(header_bit, sync_word[:31]))

        self.comb += [
            self.crc12.eq(Cat(
                sync_word[17:20],  # crc[2:0]
                sync_word[21:24],  # crc[5:3]
                sync_word[25:28],  # crc[8:6]
                sync_word[29:32],  # crc[11:9]
            )),
            self.cmd.eq(Cat(sync_word[5:8], sync_word[11], sync_word[13:16])),
            eomb.eq(sync_word[0:5] == 0b00001),
            eoemb.eq(sync_word[9] & eomb),
            self.mid_emb.eq(sh_count == (beats_per_emb//2)),
        ]

        invalid_eomb  = Signal()
        invalid_eoemb = Signal()
        emb_vcount    = Signal(2)
        emb_icount    = Signal(max=max(thresh_emb_err+1, 2))

        self.comb += [
            invalid_eoemb.eq((sh_count == 0) & ~eoemb),
            invalid_eomb.eq((sh_count[0:5] == 0) & ~eomb),
        ]

        # Sticky EoMB-seen diagnostic.
        self.sync += [
            If(eomb,
                self.eomb_seen.eq(1),
            )
        ]

        # EMB lock: INIT -> (EoEMB seen) HUNT -> (4 consecutive EoEMB at the expected extended
        # multiblock spacing) LOCK. A mis-positioned EoMB/EoEMB restarts the hunt; in LOCK an error
        # counter (threshold thresh_emb_err) drops the lock. Losing sync header lock forces INIT.
        self.submodules.fsm = fsm = FSM(reset_state="INIT")
        fsm.act("INIT",
            self.state.eq(0),
            If(eoemb & self.sh_lock,
                NextValue(emb_vcount, 0),
                NextValue(emb_icount, 0),
                NextState("HUNT"),
            )
        )
        fsm.act("HUNT",
            self.state.eq(1),
            If(~self.sh_lock | invalid_eomb | invalid_eoemb,
                NextState("INIT"),
            ).Elif((sh_count == 0) & eoemb,
                NextValue(emb_vcount, emb_vcount + 1),
                If(emb_vcount == 2,
                    NextState("LOCK"),
                ),
            )
        )
        fsm.act("LOCK",
            self.state.eq(2),
            self.emb_lock.eq(1),
            self.valid_eomb.eq(eomb & (sh_count[0:5] == 0)),
            self.valid_eoemb.eq(eoemb & (sh_count == 0)),
            If(~self.sh_lock | (emb_icount == thresh_emb_err),
                NextState("INIT"),
            ).Elif((sh_count == 0) & eoemb,
                NextValue(emb_icount, 0),
            ).Elif(invalid_eomb | invalid_eoemb,
                NextValue(emb_icount, emb_icount + 1),
            )
        )
        # Block counter, modulo extended multiblock (single driver). While hunting for the first
        # EoEMB (INIT) it is parked at 1, so that the first block after the INIT->HUNT transition
        # (the block following the triggering EoEMB) is sh_count==1 and the next EoEMB lands exactly
        # at sh_count==0 after a full extended-multiblock wrap.
        self.sync += [
            If(fsm.ongoing("INIT"),
                sh_count.eq(1),
            ).Elif(sh_count == (beats_per_emb - 1),
                sh_count.eq(0),
            ).Else(
                sh_count.eq(sh_count + 1),
            )
        ]

# Block Synchronization (PHY RX clock domain) ------------------------------------------------------

class BlockSync(Module):
    """Block Synchronization
    cf JESD204C sync header lock (drives the PHY RX gearbox slip)
    """
    def __init__(self, slip_latency=32, thresh_sh_err=16):
        self.header    = Signal(2)
        self.slip      = Signal()
        self.lock      = Signal()
        self.sh_errors = Signal(16) # Sticky, saturating.

        # # #

        valid_header = Signal()
        vcount       = Signal(7)
        icount       = Signal(max=thresh_sh_err+1)
        wait_count   = Signal(max=slip_latency)

        self.comb += valid_header.eq(self.header[0] ^ self.header[1])

        # HUNT: count consecutive valid sync headers (01 or 10); an invalid header pulses slip (one
        # bit position) and masks header evaluation while the gearbox applies it (SLIP). Lock after
        # 64 consecutive valid headers; in LOCK, thresh_sh_err consecutive invalid headers drop it.
        self.submodules.fsm = fsm = FSM(reset_state="HUNT")
        fsm.act("HUNT",
            If(valid_header,
                NextValue(vcount, vcount + 1),
                If(vcount == 63,
                    NextState("LOCK"),
                ),
            ).Else(
                self.slip.eq(1),
                NextValue(vcount, 0),
                NextValue(wait_count, 0),
                NextState("SLIP"),
            )
        )
        fsm.act("SLIP",
            # Mask header evaluation while the gearbox applies the slip.
            NextValue(wait_count, wait_count + 1),
            If(wait_count == (slip_latency - 1),
                NextState("HUNT"),
            )
        )
        fsm.act("LOCK",
            self.lock.eq(1),
            If(valid_header,
                NextValue(icount, 0),
            ).Else(
                NextValue(icount, icount + 1),
                If(self.sh_errors != (2**len(self.sh_errors) - 1),
                    NextValue(self.sh_errors, self.sh_errors + 1),
                ),
                If(icount == (thresh_sh_err - 1),
                    NextValue(vcount, 0),
                    NextValue(icount, 0),
                    NextState("HUNT"),
                ),
            )
        )

# Link TX ------------------------------------------------------------------------------------------

@ResetInserter()
class LiteJESD204CLinkTX(Module):
    """Link TX layer
    inputs:
    - jesd_settings: JESD204C settings
    """
    def __init__(self, jesd_settings):
        self.lemc_zero = Signal() # LEMC boundary strobe (jesd domain).
        self.ready     = Signal()

        self.sink   = sink   = Record([("data", 64)])
        self.source = source = Record(link_204c_layout())

        # # #

        e = jesd_settings.e

        # Datapath: octet reorder (MSB first) -> scrambler -> 2 register stages, with the CRC-12
        # computed over the scrambled data and the sync word generator aligned to the delayed
        # multiblock boundary, so that sync word bit 31 accompanies block 0 of each multiblock on
        # the PHY interface.

        # Block/multiblock counters, slaved to LEMC: they free run and (re)align on each lemc_zero
        # strobe, so alignment is acquired on the first LEMC boundary after reset and ready is
        # asserted from that point.
        blk      = Signal(5)
        mb       = Signal(max=max(e, 2))
        mb_start = Signal()
        eoemb    = Signal()
        self.comb += [
            mb_start.eq(blk == 0),
            eoemb.eq(mb == (e - 1)),
        ]
        self.sync += [
            If(self.lemc_zero,
                blk.eq(1),
                mb.eq(0),
                self.ready.eq(1),
            ).Else(
                blk.eq(blk + 1),
                If(blk == 31,
                    If(eoemb,
                        mb.eq(0),
                    ).Else(
                        mb.eq(mb + 1),
                    ),
                ),
            )
        ]

        # Scrambler (combinational output).
        self.submodules.scrambler = scrambler = Scrambler64b66b()
        self.comb += [
            scrambler.enable.eq(int(jesd_settings.scrambling)),
            scrambler.sink.data.eq(reverse_octets(sink.data)),
        ]

        # Datapath registers (scrambled -> source) and delayed strobes.
        scrambled  = Signal(64)
        mb_start_d = Signal()
        eoemb_d    = Signal()
        self.sync += [
            scrambled.eq(scrambler.source.data),
            source.data.eq(scrambled),
            mb_start_d.eq(mb_start),
            eoemb_d.eq(eoemb),
        ]

        # CRC-12 over the scrambled data, restarted at each (delayed) multiblock start.
        self.submodules.crc = crc = CRC12()
        self.comb += [
            crc.data.eq(scrambled),
            crc.init.eq(mb_start_d),
        ]

        # Sync word generation, aligned with the delayed datapath.
        self.submodules.sync_word = sync_word = SyncWordTX()
        self.comb += [
            sync_word.mb_start.eq(mb_start_d),
            sync_word.eoemb.eq(eoemb_d),
            sync_word.crc12.eq(crc.value),
            sync_word.cmd.eq(0),
            source.header.eq(sync_word.header),
        ]

# Link RX ------------------------------------------------------------------------------------------

@ResetInserter()
class LiteJESD204CLinkRX(Module):
    """Link RX layer
    inputs:
    - jesd_settings: JESD204C settings
    """
    def __init__(self, jesd_settings):
        self.sh_lock     = Signal() # Sync header lock (from BlockSync, CDC'd).
        self.ready       = Signal()
        self.frame_start = Signal()
        self.mid_frame   = Signal()
        self.crc_error   = Signal()

        self.sink   = sink   = Record(link_204c_layout())
        self.source = source = Record([("data", 64)])

        # # #

        e = jesd_settings.e

        # Datapath: sync header stream decoding (EMB lock), CRC-12 checking over the scrambled
        # payload, descrambling and octet reordering. frame_start strobes with the first source beat
        # of each extended multiblock (used to start the skew FIFOs); ready is the EMB lock.

        # Sync word receiver / EMB lock.
        self.submodules.sync_word = sync_word = SyncWordRX(beats_per_emb=e*32)
        self.comb += [
            sync_word.sh_lock.eq(self.sh_lock),
            sync_word.header.eq(sink.header),
            self.ready.eq(sync_word.emb_lock),
            self.mid_frame.eq(sync_word.mid_emb & sync_word.emb_lock),
        ]

        # CRC-12 over the received (scrambled) data.
        self.submodules.crc = crc = CRC12()
        crc_prev = Signal(12)
        crc_rdy  = Signal(2)
        self.comb += [
            crc.data.eq(sink.data),
            crc.init.eq(sync_word.valid_eomb),
        ]
        self.sync += [
            If(~sync_word.emb_lock,
                crc_rdy.eq(0),
            ).Elif(sync_word.valid_eomb,
                crc_prev.eq(crc.value),
                If(crc_rdy != 3,
                    crc_rdy.eq(crc_rdy + 1),
                ),
            )
        ]
        # CRC of multiblock N is conveyed in the sync word of multiblock N+1:
        # compare the previously latched computed CRC with the newly received one.
        self.comb += self.crc_error.eq(
            (crc_rdy == 3) & sync_word.valid_eomb & (crc_prev != sync_word.crc12)
        )

        # Descrambler (combinational output) + register + octet reorder.
        self.submodules.descrambler = descrambler = Descrambler64b66b()
        descrambled = Signal(64)
        self.comb += [
            descrambler.enable.eq(int(jesd_settings.scrambling)),
            descrambler.sink.data.eq(sink.data),
        ]
        self.sync += descrambled.eq(descrambler.source.data)
        self.comb += source.data.eq(reverse_octets(descrambled))

        # First source beat of each extended multiblock: valid_eoemb strobes when block 0 of the new
        # EMB is at the sink; the datapath is delayed by one cycle, so that block is at the source
        # one cycle later.
        self.sync += self.frame_start.eq(sync_word.valid_eoemb)
