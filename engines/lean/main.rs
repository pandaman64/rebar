use std::{ffi::CString, process::exit, ptr::null_mut};

use anyhow::Context;
use ffi::{
    lean_ctor_get, lean_dec, lean_io_mk_world, lean_io_result_is_ok,
    lean_io_result_show_error, lean_obj_tag, lean_object,
};
use lexopt::Arg;

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
    fn lean_regex_compile(r: *mut lean_object, // Regex
    ) -> *mut lean_object; // NFA
    fn lean_regex_nfa_matches(
        nfa: *mut lean_object, // NFA
        s: *mut lean_object,   // string
    ) -> *mut lean_object; // NFA.Matches
    fn lean_regex_nfa_matches_next(
        this: *mut lean_object, // NFA.Matches
    ) -> *mut lean_object; // Option ((Pos × Pos) × NFA.Matches)
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

unsafe fn unpack_option(opt: *mut lean_object) -> Option<*mut lean_object> {
    if lean_obj_tag(opt) == 0 {
        // None
        lean_dec(opt);
        None
    } else {
        // Some
        let v = lean_ctor_get(opt, 0);
        lean_inc(v);
        lean_dec(opt);
        Some(v)
    }
}

unsafe fn unpack_pair(
    pair: *mut lean_object,
) -> (*mut lean_object, *mut lean_object) {
    let fst = lean_ctor_get(pair, 0);
    let snd = lean_ctor_get(pair, 1);
    lean_inc(fst);
    lean_inc(snd);
    lean_dec(pair);
    (fst, snd)
}

// A wrapper around Regex.NFA.Matches
#[derive(Debug)]
struct Matches {
    obj: *mut lean_object,
}

impl Matches {
    fn new(nfa: *mut lean_object, haystack: *mut lean_object) -> Self {
        unsafe {
            let obj = lean_regex_nfa_matches(nfa, haystack);
            Self { obj }
        }
    }
}

impl Drop for Matches {
    fn drop(&mut self) {
        unsafe {
            if !self.obj.is_null() {
                lean_dec(self.obj);
            }
        }
    }
}

impl Iterator for Matches {
    type Item = (usize, usize);

    fn next(&mut self) -> Option<Self::Item> {
        unsafe {
            if self.obj.is_null() {
                None
            } else {
                let m = lean_regex_nfa_matches_next(self.obj);
                match unpack_option(m) {
                    Some(m) => {
                        let (pos, obj) = unpack_pair(m);
                        let (start, end) = unpack_pair(pos);
                        // NOTE: this assumes the match is smaller than SIZE_MAX >> 1, which should always be the case
                        let start = lean_unbox(start);
                        let end = lean_unbox(end);
                        self.obj = obj;
                        Some((start, end))
                    }
                    None => {
                        self.obj = null_mut();
                        None
                    }
                }
            }
        }
    }
}

unsafe fn compile_regex_to_nfa(
    pattern: &str,
) -> anyhow::Result<*mut lean_object> {
    let pattern =
        CString::new(pattern).context("The input contains a nul byte")?;
    let pattern = ffi::lean_mk_string(pattern.as_ptr());
    let regex = lean_regex_parse_or_panic(pattern);
    let nfa = lean_regex_compile(regex);
    Ok(nfa)
}

unsafe fn model_count(
    b: &klv::Benchmark,
    nfa: *mut lean_object,
) -> anyhow::Result<Vec<timer::Sample>> {
    let haystack =
        CString::new(&*b.haystack).context("The input contains a nul byte")?;
    let haystack = ffi::lean_mk_string(haystack.as_ptr());
    timer::run(b, move || {
        lean_inc(nfa);
        lean_inc(haystack);
        let matches = Matches::new(nfa, haystack);
        Ok(matches.count())
    })
}

unsafe fn model_count_spans(
    b: &klv::Benchmark,
    nfa: *mut lean_object,
) -> anyhow::Result<Vec<timer::Sample>> {
    let haystack =
        CString::new(&*b.haystack).context("The input contains a nul byte")?;
    let haystack = ffi::lean_mk_string(haystack.as_ptr());
    timer::run(b, move || {
        lean_inc(nfa);
        lean_inc(haystack);
        let matches = Matches::new(nfa, haystack);
        Ok(matches.map(|(start, end)| end - start).sum())
    })
}

fn main() -> anyhow::Result<()> {
    let mut p = lexopt::Parser::from_env();
    let mut version = false;
    while let Some(arg) = p.next()? {
        match arg {
            Arg::Short('v') | Arg::Long("version") => {
                version = true;
            }
            _ => return Err(arg.unexpected().into()),
        }
    }
    if version {
        println!(
            "{}-{}",
            env!("CARGO_PKG_VERSION"),
            env!("LEAN_REGEX_VERSION")
        );
        return Ok(());
    }
    let b = klv::Benchmark::read(std::io::stdin())
        .context("failed to read KLV data from <stdin>")?;

    unsafe {
        initialize();
        let samples = match b.model.as_str() {
            "count" => model_count(&b, compile_regex_to_nfa(b.regex.one()?)?)?,
            "count-spans" => {
                model_count_spans(&b, compile_regex_to_nfa(b.regex.one()?)?)?
            }
            _ => anyhow::bail!("unrecognized benchmark model '{}'", b.model),
        };
        for s in samples.iter() {
            println!("{},{}", s.duration.as_nanos(), s.count);
        }
    }

    Ok(())
}
