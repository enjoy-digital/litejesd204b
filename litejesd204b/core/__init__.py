from litex.gen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litejesd204b.common import *
from litejesd204b.core.transport import LiteJESD204BTransportTX
from litejesd204b.core.link import LiteJESD204BLinkTX

#TODO:
# - expose controls signals or connect to CSRs?
# - use elastic buffers between transport and links instead of async fifos

class LiteJESD204BCoreTX(Module):
    def __init__(self, phys, jesd_settings, converter_data_width):
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
        self.submodules += transport

        # cdc
        cdcs = []
        for i, phy in enumerate(phys):
            cdc = stream.AsyncFIFO(data_layout(phy.data_width), 8)
            cdc = ClockDomainsRenamer({"write": "tx", "read": phy.cd})(cdc)
            cdcs.append(cdc)
            self.submodules += cdc

        # link layer
        links = []
        for i, phy in enumerate(phys):
            jesd_settings.phy.lid = i
            link = LiteJESD204BLinkTX(phy.data_width, jesd_settings)
            link = ClockDomainsRenamer(phy.cd)(link)
            links.append(link)
            self.submodules += link

        # connect modules together
        self.comb += transport.source.ready.eq(1) # FIXME (remove flow control?)
        for i, (link, cdc) in enumerate(zip(links, cdcs)):
            self.comb += [
                cdc.sink.valid.eq(transport.source.valid),
                cdc.sink.data.eq(getattr(transport.source, "data"+str(i))),
                cdc.source.connect(link.sink),
                link.source.connect(phy.sink, omit=["frame_last",
                                                    "multiframe_last"])
            ]
