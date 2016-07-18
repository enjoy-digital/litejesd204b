CTRL_START = (1 << 0)
STATUS_DONE = (1 << 0)

class AD9154SPI():
    def __init__(self, regs):
        self.regs = regs

    def write(self, addr, byte):
        cmd = (0 << 15) | (addr & 0x7ff)
        val = (cmd << 8) | (byte & 0xff)
        self.regs.ad9154_spi_mosi.write(val)
        self.regs.ad9154_spi_length.write(24)
        self.regs.ad9154_spi_ctrl.write(CTRL_START)
        while not (self.regs.ad9154_spi_status.read() & STATUS_DONE):
            pass

    def read(self, addr):
        cmd = (1 << 15) | (addr & 0x7ff)
        val = (cmd << 8)
        self.regs.ad9154_spi_mosi.write(val)
        self.regs.ad9154_spi_length.write(24)
        self.regs.ad9154_spi_ctrl.write(CTRL_START)
        while not (self.regs.ad9154_spi_status.read() & STATUS_DONE):
            pass
        return (self.regs.ad9154_spi_miso.read() & 0xff)
