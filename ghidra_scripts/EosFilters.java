// Label the voice filter classes (registry at 0x67F98, method tables 0x687DC/0x6884C..0x68BF0).
//@category EOS

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.PointerDataType;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class EosFilters extends GhidraScript {
    // method-table slot names (slot 0/1 are zero, slot 2 = destructor)
    static final String[] SLOT = {"rtti0", "rtti1", "dtor", "type", "getName", "computeFrames",
            "packQ", "formatParam", "numParams", "paramRange", "paramFlags"};

    // {method table, short name}, in registry (menu) order
    static final Object[][] CLS = {
        {0x68878, "LP2"}, {0x688a4, "LP4"}, {0x688d0, "LP6"}, {0x688fc, "HP2"}, {0x68928, "HP4"},
        {0x689d8, "BP2"}, {0x68a04, "BP4"}, {0x68a30, "ContraryBP"}, {0x68954, "SweptEQ1"},
        {0x68980, "SweptEQ2to1"}, {0x689ac, "SweptEQ3to1"}, {0x68a5c, "Phaser1"}, {0x68a88, "Phaser2"},
        {0x68ab4, "BatPhaser"}, {0x68ae0, "FlangerLite"}, {0x68b0c, "VocalAhAyEe"}, {0x68b38, "VocalOoAh"},
        {0x687dc, "DualEQMorph"}, {0x68b64, "TwoEQLowpassMorph"}, {0x68b94, "TwoEQMorphExpr"},
        {0x68bc4, "PeakShelfMorph"}, {0x6884c, "FilterBase"},
    };

    @Override
    public void run() throws Exception {
        createLabel(toAddr(0x67f98), "FilterRegistry_ctor", true);
        mkFunc(0x67f98, "FilterRegistry_ctor");
        createLabel(toAddr(0x6871c), "filt_tab_gainOffset16", true);
        createLabel(toAddr(0x6875c), "filt_tab_resSection16", true);
        createLabel(toAddr(0x6879c), "filt_tab_resGain16", true);
        for (Object[] c : CLS) {
            Address vt = toAddr((Integer) c[0]);
            String cls = (String) c[1];
            createLabel(vt, "vtbl_Filter_" + cls, true);
            for (int k = 0; k < SLOT.length; k++) {
                Address a = vt.add(4 * k);
                clearListing(a, a.add(3));
                createData(a, PointerDataType.dataType);
                long tgt = getInt(a) & 0xffffffffL;
                if (k < 3 || tgt < 0x20000) continue;
                // shared base-class methods keep a Base name
                Function f = getFunctionAt(toAddr(tgt));
                String nm = "Filter_" + cls + "_" + SLOT[k];
                if (f != null && f.getName().startsWith("Filter_") && !f.getName().startsWith("Filter_" + cls))
                    nm = "FilterShared_" + SLOT[k] + "_" + Long.toHexString(tgt);
                mkFunc(tgt, nm);
            }
        }
    }

    void mkFunc(long addr, String name) throws Exception {
        Address a = toAddr(addr);
        if (getInstructionAt(a) == null) disassemble(a);
        Function f = getFunctionAt(a);
        if (f == null) f = createFunction(a, name);
        if (f != null) f.setName(name, SourceType.USER_DEFINED);
    }
}
