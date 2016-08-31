from litejesd204b.common import *


class PRBS:
    def __init__(self, n_state=23, taps=[17, 22]):
        self.n_state = n_state
        self.taps = taps
        self.state = 1

    def getbit(self):
        feedback = 0
        for tap in self.taps:
            feedback = feedback ^ (self.state >> tap) & 0x1
        self.state = (self.state << 1) & (2**self.n_state-1) | feedback
        return feedback

    def getbits(self, n):
        v = 0
        for i in range(n):
            v <<= 1
            v |= self.getbit()
        return v
