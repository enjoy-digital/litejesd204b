module jesd204_scrambler (
    input clk,
 
    input enable,
 
    input [31:0] data_in,
    output [31:0] data_out
);
 
parameter DESCRAMBLE = 0;
 
reg [14:0] state = 'h7fff;
wire [31:0] feedback;
 
wire [31:0] swizzle_in = {data_in[7:0],data_in[15:8],data_in[23:16],data_in[31:24]};
assign data_out = {swizzle_out[7:0],swizzle_out[15:8],swizzle_out[23:16],swizzle_out[31:24]};
 
reg [31:0] swizzle_out = 'h00;
 
wire [31+15:0] full = {state,DESCRAMBLE ? swizzle_in : feedback};
 
assign feedback = full[31+15:15] ^ full[31+14:14] ^ swizzle_in;
 
always @(posedge clk) begin
    if (enable == 1'b0) begin
        swizzle_out <= swizzle_in;
    end else begin
        swizzle_out <= feedback;
    end
end
 
always @(posedge clk) begin
    state <= full[14:0];
end
 
endmodule