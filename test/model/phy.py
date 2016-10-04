# pseudo random binary sequence
class PRBSGenerator:
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


class PRBS7Generator(PRBSGenerator):
    def __init__(self):
        PRBSGenerator.__init__(self, n_state=7,  taps=[5, 6])


class PRBS15Generator(PRBSGenerator):
    def __init__(self):
        PRBSGenerator.__init__(self, n_state=15,  taps=[13, 14])


class PRBS31Generator(PRBSGenerator):
    def __init__(self):
        PRBSGenerator.__init__(self, n_state=31,  taps=[27, 30])
