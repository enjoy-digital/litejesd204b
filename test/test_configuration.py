from litejesd204b.common import *

phy_settings = LiteJESD204BPhysicalSettings(l=4, m=4, n=12, np=16)
transport_settings = LiteJESD204BTransportSettings(f=2, s=1, k=16, cs=1)
global_settings = LiteJESD204BSettings(phy_settings,
	                                   transport_settings,
	                                   did=0x5, bid=0xa)

print(global_settings.get_configuration_data())