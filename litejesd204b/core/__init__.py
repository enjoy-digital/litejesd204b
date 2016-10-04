from litex.gen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litejesd204b.common import *
from litejesd204b.core.transport import LiteJESD204BTransportTX
from litejesd204b.core.link import LiteJESD204BLinkTX

#TODO:
# - expose controls signals or connect to CSRs?
# - use elastic buffers between transport and links instead of async fifos
# - remove flow control (at least when uneeded)

class LiteJESD204BCoreTX(Module, AutoCSR):
    def __init__(self, phys, jesd_settings, converter_data_width):
        self.phy_enable = CSRStorage(len(phys))

        # # #

        # clocking
        self.clock_domains.cd_tx = ClockDomain()
        self.comb += [
            # clock of first phy as core clock
            self.cd_tx.clk.eq(phys[0].gtx.cd_tx.clk),
            # hold core in reset until all phy are readys
            self.cd_tx.rst.eq(phys[0].gtx.cd_tx.rst), # FIXME
        ]

        # transport layer
        transport = LiteJESD204BTransportTX(jesd_settings.transport,
                                            jesd_settings.phy,
                                            converter_data_width)
        transport = ClockDomainsRenamer("tx")(transport)
        self.submodules.transport = transport

        # cdc
        self.cdcs = cdcs = []
        for i, phy in enumerate(phys):
            cdc = stream.AsyncFIFO(data_layout(len(phy.data)), 8)
            cdc = ClockDomainsRenamer({"write": "tx", "read": phy.gtx.cd_tx.name})(cdc)
            cdcs.append(cdc)
            self.submodules += cdc

        # link layer
        self.links = links = []
        for i, phy in enumerate(phys):
            jesd_settings.lid = i
            link = LiteJESD204BLinkTX(len(phy.data), jesd_settings)
            link = ClockDomainsRenamer(phy.gtx.cd_tx.name)(link)
            links.append(link)
            self.submodules += link

        # connect modules together
        self.comb += transport.source.ready.eq(1) # FIXME (remove flow control?)
        for i, (link, cdc) in enumerate(zip(links, cdcs)):
            self.comb += [
                cdc.sink.valid.eq(transport.source.valid),
                cdc.sink.data.eq(getattr(transport.source, "data"+str(i))),
                cdc.source.connect(link.sink),
                phys[i].data.eq(link.source.data),
                phys[i].ctrl.eq(link.source.ctrl),
                link.source.ready.eq(1)
            ]

        # registers
        for i, phy in enumerate(phys):
            self.comb += phy.gtx.gtx_init.restart.eq(~self.phy_enable.storage[i])
