from litex.gen import *

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

from litejesd204b.common import *
from litejesd204b.core.transport import LiteJESD204BTransportTX
from litejesd204b.core.link import LiteJESD204BLinkTX

#TODO:
# - use jesd_tx_0 clock domain for transport
# - use elastic buffers between transport and links instead of async fifos


class LiteJESD204BCoreTX(Module, AutoCSR):
    def __init__(self, phys, jesd_settings, converter_data_width):
        # transport
        transport = LiteJESD204BTransportTX(jesd_settings.transport,
                                            jesd_settings.phy,
                                            converter_data_width)
        self.submodules += transport

        # link
        for l, phy in enumerate(phys):
            jesd_settings.phy.lid = l
            
            # clock domain crossing (TODO: replace with elastic buffer)
            cdc = stream.AsyncFIFO([("data", phy.data_width)], 8)
            cdc = ClockDomainsRenamer({"write": "sys", "read": phy.cd})(cdc)
            self.submodules += cdc
            
            # link layer
            link = LiteJESD204BLinkTX(phy.data_width, jesd_settings)
            link = ClockDomainsRenamer({"link_tx": phy.cd})(link)
            setattr(self.submodules, "link"+str(l), link)

            # connect transport --> link --> phy
            self.comb += [
                cdc.sink.valid.eq(transport.source.valid),
                transport.source.ready.eq(cdc.sink.ready),
                cdc.sink.data.eq(getattr(transport.source, "data"+str(l))),
                cdc.source.connect(link.sink),
                link.source.connect(phy.sink, omit=["frame_last", "multiframe_last"])
            ]
