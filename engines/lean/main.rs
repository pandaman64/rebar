use std::process::exit;

use ffi::{lean_string_object, lean_object, lean_io_mk_world, lean_dec, lean_io_result_show_error, lean_io_result_is_ok};

mod ffi;

extern "C" {
    fn lean_initialize_runtime_module();
    fn lean_initialize();
    fn lean_io_mark_end_initialization();

    fn initialize_Regex(builtin: u8, world: *mut lean_object) -> *mut lean_object;
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
        let s = ffi::lean_mk_string(b"Hello, world!\0".as_ptr().cast());
        let s: *mut lean_string_object = s.cast();
        let s = (*s).m_data.as_slice((*s).m_size);
        println!("{:?}", s);
    }
}
