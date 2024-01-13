use std::process::exit;

use ffi::{
    lean_dec, lean_io_mk_world, lean_io_result_is_ok,
    lean_io_result_show_error, lean_object,
};

use crate::ffi::{lean_inc, lean_unbox};

mod ffi;

extern "C" {
    fn lean_initialize_runtime_module();
    fn lean_initialize();
    fn lean_io_mark_end_initialization();

    fn initialize_Regex(
        builtin: u8,
        world: *mut lean_object,
    ) -> *mut lean_object;

    fn lean_regex_parse_or_panic(
        input: *mut lean_object, // string
    ) -> *mut lean_object; // Regex
    fn lean_regex_nfa_compile_regex(
        r: *mut lean_object, // Regex
    ) -> *mut lean_object; // NFA
    fn lean_regex_nfa_match(
        nfa: *mut lean_object,      // NFA
        inBounds: *mut lean_object, // always lean_box(0)
        input: *mut lean_object,    // string
    ) -> *mut lean_object; // should be a boxed bool
}

unsafe fn initialize() {
    // use same default as for Lean executables
    let builtin: u8 = 1;

    lean_initialize_runtime_module();
    lean_initialize();

    // TODO: this is failing due to missing Mathlib lib at the link step.
    // I'll remove Mathlib dependency from core.
    let res = initialize_Regex(builtin, lean_io_mk_world());
    if lean_io_result_is_ok(res) {
        lean_dec(res);
    } else {
        lean_io_result_show_error(res);
        lean_dec(res);
        exit(1);
    }
    lean_io_mark_end_initialization();
}

fn main() {
    unsafe {
        initialize();
        let regex = ffi::lean_mk_string("Hello|world\0".as_ptr().cast());
        let regex = lean_regex_parse_or_panic(regex);
        let nfa = lean_regex_nfa_compile_regex(regex);

        let s = ffi::lean_mk_string("Hello\0".as_ptr().cast());
        lean_inc(nfa);
        let res = lean_regex_nfa_match(nfa, ffi::lean_box(0), s);
        assert_eq!(lean_unbox(res), 1);

        let s = ffi::lean_mk_string("こんにちは\0".as_ptr().cast());
        let res = lean_regex_nfa_match(nfa, ffi::lean_box(0), s);
        assert_eq!(lean_unbox(res), 0);
    }
}
