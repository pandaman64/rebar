use std::{env::current_dir, fs, path::PathBuf, process::Command};

// See https://github.com/LemonHX/lean4-rs/blob/d2064357140a31fab564058d83b95b5bb04940be/lean4-sys/build.rs

fn main() {
    println!("cargo:rerun-if-changed=main");

    let out_dir = PathBuf::from(std::env::var_os("OUT_DIR").unwrap());

    let lean_output = Command::new("lean")
        .arg("--print-prefix")
        .output()
        .expect("Failed to execute lean --print-prefix");
    if !lean_output.status.success() {
        panic!(
            "lean --print-prefix failed with status {}\n{}",
            lean_output.status,
            String::from_utf8_lossy(&lean_output.stderr)
        );
    }
    let lean_prefix = String::from_utf8(lean_output.stdout)
        .expect("Lean prefix is not valid UTF-8");
    let lean_prefix = PathBuf::from(lean_prefix.trim());

    // build static lib
    let lean_regix_dir =
        current_dir().expect("Failed to get current dir").join("main");
    let build_output = Command::new("lake")
        .args(["build", "Regex:static"])
        .current_dir(&lean_regix_dir)
        .output()
        .expect("Failed to execute lake build Regex:static");
    if !build_output.status.success() {
        panic!(
            "lake build Regex:staticlib failed with status {}\n{}\n{}",
            build_output.status,
            String::from_utf8_lossy(&build_output.stdout),
            String::from_utf8_lossy(&build_output.stderr),
        );
    }
    fs::copy(
        lean_regix_dir.join(".lake/build/lib/libRegex.a"),
        out_dir.join("libRegex.a"),
    )
    .expect("Failed to copy libRegex.a");

    // is it a good idea to add OUT_DIR to the library search path?
    println!("cargo:rustc-link-search=native={}", out_dir.display());
    println!("cargo:rustc-link-lib=static=Regex");

    // link to Lean shared library (assumes Linux)
    let lean_lib_dir = lean_prefix.join("lib/lean");
    println!("cargo:rustc-link-search=native={}", lean_lib_dir.display());
    println!("cargo:rustc-link-lib=dylib=leanshared");
    println!("cargo:rustc-link-arg=-Wl,-rpath,{}", lean_lib_dir.display());

    // generate bindings
    let bindings = bindgen::Builder::default()
        .header(lean_prefix.join("include/lean/lean.h").to_str().unwrap())
        .clang_arg(format!("-I{}", lean_prefix.join("include").display()))
        .allowlist_item("(lean|Lean|LEAN).*")
        .use_core()
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .generate()
        .expect("Unable to generate bindings");

    bindings
        .write_to_file(out_dir.join("bindings.rs"))
        .expect("Couldn't write bindings!");
}
