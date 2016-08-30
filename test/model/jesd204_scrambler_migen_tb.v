`timescale 1ns/1ps

module jesd204_scrambler_migen_tb();

reg clk;
initial clk = 1'b0;
always #2.5 clk = ~clk;

wire [31:0] data_in;
wire [31:0] data_out;

assign data_in = 1'b0;

top dut (
    .sys_clk(clk),
    .sys_rst(1'b0),
    .enable(1'b1),
    .data_in(data_in),
    .data_out(data_out)
);

endmodule
