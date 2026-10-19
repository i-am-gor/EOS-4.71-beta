// Post-analysis report: function list, string xrefs, MBAR/peripheral access summary.
// Writes into the directory given as first script arg.
//@category EOS

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class EosReport extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = getScriptArgs().length > 0 ? getScriptArgs()[0] : ".";
        Listing lst = currentProgram.getListing();
        ReferenceManager rm = currentProgram.getReferenceManager();

        try (PrintWriter w = new PrintWriter(new File(outDir, "functions.tsv"))) {
            w.println("entry\tname\tsize\tcallers\tcallees");
            for (Function f : lst.getFunctions(true)) {
                w.printf("%s\t%s\t%d\t%d\t%d%n", f.getEntryPoint(), f.getName(), f.getBody().getNumAddresses(),
                        f.getCallingFunctions(monitor).size(), f.getCalledFunctions(monitor).size());
            }
        }

        try (PrintWriter w = new PrintWriter(new File(outDir, "strings_xrefs.tsv"))) {
            w.println("addr\tstring\treferencing_functions");
            for (Data d : lst.getDefinedData(true)) {
                if (!d.hasStringValue()) continue;
                Set<String> fns = new TreeSet<>();
                for (Reference r : rm.getReferencesTo(d.getAddress())) {
                    Function f = getFunctionContaining(r.getFromAddress());
                    fns.add(f == null ? r.getFromAddress().toString() : f.getName());
                }
                String s = String.valueOf(d.getValue()).replace("\t", "\\t").replace("\n", "\\n");
                w.printf("%s\t%s\t%s%n", d.getAddress(), s, String.join(",", fns));
            }
        }

        // Accesses to non-RAM, non-flash address space (peripherals)
        TreeMap<Long, Integer> hits = new TreeMap<>();
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (!b.isVolatile()) continue;
            AddressIterator it = rm.getReferenceDestinationIterator(new AddressSet(b.getStart(), b.getEnd()), true);
            while (it.hasNext()) {
                Address a = it.next();
                hits.merge(a.getOffset(), rm.getReferenceCountTo(a), Integer::sum);
            }
        }
        try (PrintWriter w = new PrintWriter(new File(outDir, "io_refs.tsv"))) {
            w.println("addr\tlabel\trefs");
            for (Map.Entry<Long, Integer> e : hits.entrySet()) {
                Address a = toAddr(e.getKey());
                Symbol s = getSymbolAt(a);
                w.printf("%08x\t%s\t%d%n", e.getKey(), s == null ? "" : s.getName(), e.getValue());
            }
        }
        int n = currentProgram.getFunctionManager().getFunctionCount();
        println("EOSREPORT functions=" + n + " io_addrs=" + hits.size());
    }
}
