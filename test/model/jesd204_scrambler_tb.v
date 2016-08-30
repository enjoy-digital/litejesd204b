`timescale 1ns/1ps

module jesd204_scrambler_tb();

reg clk;
initial clk = 1'b0;
always #2.5 clk = ~clk;

wire [31:0] data_in;
wire [31:0] data_out;

assign data_in = 1'b0;

jesd204_scrambler dut (
    .clk(clk),
    .enable(1'b1),
    .data_in(data_in),
    .data_out(data_out)
);

endmodule
