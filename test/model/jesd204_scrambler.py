from litejesd204b.core.link import LiteJESD204BScrambler
from litex.gen.fhdl import verilog

scrambler = LiteJESD204BScrambler()
ios = {scrambler.enable,
       scrambler.data_in,
       scrambler.data_out}
print(verilog.convert(scrambler, ios))
