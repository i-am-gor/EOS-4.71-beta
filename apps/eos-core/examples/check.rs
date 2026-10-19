//! Command-line check: EOS470.EXE -> 4.71-beta (or 4.70) -> .syx, verified by the loader simulation.
//! usage: check EOS470.EXE OUT.syx [--original]
fn main() {
    let a: Vec<String> = std::env::args().collect();
    let data = std::fs::read(&a[1]).expect("read input");
    let beta = !a.iter().any(|x| x == "--original");
    let (img, name) = eos_core::build_image(&data, beta).unwrap_or_else(|e| panic!("{e}"));
    let msgs = eos_core::filedump::messages_for_image(&img).unwrap_or_else(|e| panic!("{e}"));
    std::fs::write(&a[2], eos_core::filedump::to_syx(&msgs)).expect("write");
    println!("{}: '{}', {} messages, checksum {:08x}", a[2], name, msgs.len(), eos_core::image::csum(&img));
}
