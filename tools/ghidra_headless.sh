#!/bin/bash
# Run Ghidra headless with Homebrew's JDK 21.
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
exec /opt/homebrew/Cellar/ghidra/12.1.4/libexec/support/analyzeHeadless "$@"
