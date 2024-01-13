#![allow(non_upper_case_globals)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![allow(dead_code)]

include!(concat!(env!("OUT_DIR"), "/bindings.rs"));

#[inline]
pub(crate) fn lean_is_scalar(o: *mut lean_object) -> bool {
    (o as usize) & 1 == 1
}

#[inline]
pub(crate) unsafe fn lean_dec_ref(o: *mut lean_object) {
    if (*o).m_rc > 1 {
        (*o).m_rc -= 1;
    } else if (*o).m_rc != 0 {
        lean_dec_ref_cold(o);
    }
}

#[inline]
pub(crate) unsafe fn lean_dec(o: *mut lean_object) {
    if !lean_is_scalar(o) {
        lean_dec_ref(o);
    }
}

#[inline]
pub(crate) fn lean_box(n: usize) -> *mut lean_object {
    ((n << 1) | 1) as *mut lean_object
}

#[inline]
pub(crate) fn lean_unbox(o: *mut lean_object) -> usize {
    (o as usize) >> 1
}

#[inline]
pub(crate) fn lean_io_mk_world() -> *mut lean_object {
    lean_box(0)
}

#[inline]
pub(crate) unsafe fn lean_io_result_is_ok(o: *mut lean_object) -> bool {
    (*o).m_tag() == 0
}

#[inline]
pub(crate) unsafe fn lean_io_result_is_error(o: *mut lean_object) -> bool {
    (*o).m_tag() == 1
}
