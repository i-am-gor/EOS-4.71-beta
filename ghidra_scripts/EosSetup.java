// Pre-analysis setup for E-mu EOS 4.70 (EIV Ultra, MCF5206e).
// Image is loaded raw at 0x20000 (flash, CS0). Run as -preScript.
//@category EOS

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.mem.*;
import ghidra.program.model.symbol.SourceType;

public class EosSetup extends GhidraScript {

    static final String[] VEC = {
        "SSP", "Reset", "AccessError", "AddressError", "IllegalInsn", "DivideByZero", "v6", "v7",
        "PrivilegeViolation", "Trace", "LineA", "LineF", "DebugInterrupt", "v13", "FormatError", "UninitInt",
    };

    // MCF5206e SIM register offsets from MBAR
    static final Object[][] MBAR_REGS = {
        {0x003, "SIMR", 1}, {0x014, "ICR1", 1}, {0x015, "ICR2", 1}, {0x016, "ICR3", 1}, {0x017, "ICR4", 1},
        {0x018, "ICR5", 1}, {0x019, "ICR6", 1}, {0x01a, "ICR7", 1}, {0x01b, "ICR8", 1}, {0x01c, "ICR9", 1},
        {0x01d, "ICR10", 1}, {0x01e, "ICR11", 1}, {0x01f, "ICR12", 1}, {0x020, "ICR13", 1},
        {0x036, "IMR", 2}, {0x03a, "IPR", 2}, {0x040, "RSR", 1}, {0x041, "SYPCR", 1}, {0x042, "SWIVR", 1},
        {0x043, "SWSR", 1}, {0x046, "DCRR", 2}, {0x04a, "DCTR", 2}, {0x04c, "DCAR0", 2}, {0x050, "DCMR0", 4},
        {0x057, "DCCR0", 1}, {0x058, "DCAR1", 2}, {0x05c, "DCMR1", 4}, {0x063, "DCCR1", 1},
        {0x0c2, "DMCR", 2}, {0x0ca, "PAR", 2},
        {0x100, "TMR1", 2}, {0x104, "TRR1", 2}, {0x108, "TCR1", 2}, {0x10c, "TCN1", 2}, {0x111, "TER1", 1},
        {0x120, "TMR2", 2}, {0x124, "TRR2", 2}, {0x128, "TCR2", 2}, {0x12c, "TCN2", 2}, {0x131, "TER2", 1},
        {0x1c5, "PPDDR", 1}, {0x1c9, "PPDAT", 1},
        {0x1e0, "MADR", 1}, {0x1e4, "MFDR", 1}, {0x1e8, "MBCR", 1}, {0x1ec, "MBSR", 1}, {0x1f0, "MBDR", 1},
        {0x200, "DMA0_SAR", 4}, {0x204, "DMA0_DAR", 4}, {0x208, "DMA0_DCR", 2}, {0x20c, "DMA0_BCR", 2},
        {0x210, "DMA0_DSR", 1}, {0x214, "DMA0_DIVR", 1},
        {0x240, "DMA1_SAR", 4}, {0x244, "DMA1_DAR", 4}, {0x248, "DMA1_DCR", 2}, {0x24c, "DMA1_BCR", 2},
        {0x250, "DMA1_DSR", 1}, {0x254, "DMA1_DIVR", 1},
    };

    static final String[] UART = {"UMR", "USR_UCSR", "UCR", "URB_UTB", "UIPCR_UACR", "UISR_UIMR", "UBG1", "UBG2"};

    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        int tx = currentProgram.startTransaction("EOS setup");
        try {
            MemoryBlock flash = mem.getBlock(toAddr(0x20000));
            flash.setName("FLASH_EOS");
            flash.setWrite(false);

            mkBlock("FLASH_BOOT", 0x00000000L, 0x20000, false);       // PL01 boot loader (not in this image)
            mkBlock("DRAM", 0x10000000L, 0x7fe000, false);             // OS DRAM, VBR=0x10000000
            mkBlock("SRAM", 0x107fe000L, 0x2000, false);               // RAMBAR on-chip 8K
            mkBlock("MBAR", 0x20000000L, 0x400, true);                 // MCF5206e SIM
            // Chip-select windows from startup CSARn writes (sizes provisional)
            long[] cs = {0x02000000L, 0x03000000L, 0x04000000L, 0x05000000L, 0x06000000L, 0x08000000L};
            for (long a : cs) mkBlock(String.format("CS_%08X", a), a, 0x100000, true);

            for (Object[] r : MBAR_REGS) mbar((Integer) r[0], (String) r[1], (Integer) r[2]);
            for (int u = 0; u < 2; u++)
                for (int i = 0; i < UART.length; i++)
                    mbar(0x140 + u * 0x40 + i * 4, "UART" + (u + 1) + "_" + UART[i], 1);

            // Image header
            Address h = toAddr(0x20000);
            createLabel(h, "eos_image_header", true);
            createDWord(h); setEOLComment(h, "magic 0x76543210 (0x76543211 on floppy = Lz77)");
            createDWord(h.add(4)); setEOLComment(h.add(4), "byte-sum of first len bytes");
            createDWord(h.add(8)); setEOLComment(h.add(8), "~checksum");
            createDWord(h.add(0xc)); setEOLComment(h.add(0xc), "entry point");
            createDWord(h.add(0x10)); setEOLComment(h.add(0x10), "image length incl. header");
            createAsciiString(h.add(0x18));

            // Vector table at 0x20200
            Address vt = toAddr(0x20200);
            createLabel(vt, "vector_table", true);
            for (int i = 0; i < 256; i++) {
                Address a = vt.add(i * 4);
                clearListing(a, a.add(3));
                createData(a, PointerDataType.dataType);
                if (i == 0) continue;
                long tgt = getInt(a) & 0xffffffffL;
                if (tgt < 0x20000 || tgt >= 0x20000 + flash.getSize()) continue;
                Address t = toAddr(tgt);
                String nm = i < VEC.length ? "exc_" + VEC[i]
                          : (i >= 24 && i < 32) ? "autovec_irq" + (i - 24)
                          : (i >= 32 && i < 48) ? "trap_" + (i - 32) : "vec_" + i;
                if (getSymbolAt(t) == null || getSymbolAt(t).getSource() == SourceType.DEFAULT)
                    createLabel(t, nm, true);
                disassemble(t);
                if (getFunctionAt(t) == null) createFunction(t, null);
            }
            createLabel(toAddr(0x20602), "reset_entry", true);
        } finally {
            currentProgram.endTransaction(tx, true);
        }
    }

    void mkBlock(String name, long start, long len, boolean vol) throws Exception {
        Address a = toAddr(start);
        if (currentProgram.getMemory().getBlock(a) != null) return;
        MemoryBlock b = currentProgram.getMemory().createUninitializedBlock(name, a, len, false);
        b.setRead(true); b.setWrite(true); b.setExecute(!vol);
        b.setVolatile(vol);
    }

    void mbar(int off, String name, int size) throws Exception {
        Address a = toAddr(0x20000000L + off);
        createLabel(a, "MBAR_" + name, true);
        DataType dt = size == 1 ? ByteDataType.dataType : size == 2 ? WordDataType.dataType : DWordDataType.dataType;
        try { createData(a, dt); } catch (Exception e) { /* overlapping */ }
    }
}
