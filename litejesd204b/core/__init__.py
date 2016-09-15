from litex.gen import *

from litex.soc.interconnect.csr import *

from litejesd204b.common import *
from litejesd204b.core.transport import LiteJESD204BTransportTX
from litejesd204b.core.link import LiteJESD204BLinkTX


class LiteJESD204BCoreTX(Module, AutoCSR):
	def __init__(self, transport_settings, physical_settings, converter_data_width):
		# compute parameters
		nlanes = physical_settings.l

		# transport
		self.submodules.transport = LiteJESD204BTransportTX(transport_settings,
			                                                physical_settings,
			                                                converter_data_width)

		# link
		for l in range(nlanes):
			link = LiteJESD204BLinkTX(32)
			setattr(self.submodules, "link"+str(l), link)
