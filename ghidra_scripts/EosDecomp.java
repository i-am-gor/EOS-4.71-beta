// Decompile functions to C. Args: outFile, then either name prefixes ("Filter") or hex addresses ("0x67f98").
//@category EOS

import ghidra.app.decompiler.*;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import java.io.*;
import java.util.*;

public class EosDecomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        Set<Function> todo = new LinkedHashSet<>();
        for (int i = 1; i < args.length; i++) {
            String a = args[i];
            if (a.startsWith("0x")) {
                Function f = getFunctionContaining(toAddr(Long.parseLong(a.substring(2), 16)));
                if (f == null) f = createFunction(toAddr(Long.parseLong(a.substring(2), 16)), null);
                if (f != null) todo.add(f);
            } else {
                for (Function f : currentProgram.getFunctionManager().getFunctions(true))
                    if (f.getName().startsWith(a)) todo.add(f);
            }
        }
        try (PrintWriter w = new PrintWriter(new File(args[0]))) {
            for (Function f : todo) {
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                w.printf("// ===== %s @ %s =====%n", f.getName(), f.getEntryPoint());
                w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// FAILED " + r.getErrorMessage());
            }
        }
        println("EOSDECOMP " + todo.size() + " functions -> " + args[0]);
    }
}
