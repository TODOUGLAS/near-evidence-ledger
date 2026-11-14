//! The verdict rule, in integer (micro-unit) arithmetic. Mirrors `ledger/claims.py::verdict_fp` exactly;
//! `tests/verdict_vectors.json` is generated from the Python side and checked here.
use near_sdk::near;

#[near(serializers = [json, borsh])]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Verdict {
    #[serde(rename = "SUPPORTED")]
    Supported,
    #[serde(rename = "REFUTED")]
    Refuted,
    #[serde(rename = "INCONCLUSIVE")]
    Inconclusive,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Comparator {
    #[serde(rename = ">=")]
    Ge,
    #[serde(rename = "<=")]
    Le,
}

fn passes(x: i64, c: Comparator, thr: i64) -> bool {
    match c {
        Comparator::Ge => x >= thr,
        Comparator::Le => x <= thr,
    }
}

/// Values are fixed-point with 6 decimals (micro units).
///  * with a 90% interval: SUPPORTED if the whole interval passes, REFUTED if none of it does, else INCONCLUSIVE;
///  * without an interval: INCONCLUSIVE within +/-5% (relative) of the threshold, else decided by the point value.
pub fn evaluate(value: i64, c: Comparator, thr: i64, ci: Option<(i64, i64)>) -> Verdict {
    if let Some((lo, hi)) = ci {
        let (a, b) = (passes(lo, c, thr), passes(hi, c, thr));
        return match (a, b) {
            (true, true) => Verdict::Supported,
            (false, false) => Verdict::Refuted,
            _ => Verdict::Inconclusive,
        };
    }
    let diff = (value as i128 - thr as i128).abs() * 100;
    if diff <= 5 * (thr as i128).abs() {
        return Verdict::Inconclusive;
    }
    if passes(value, c, thr) {
        Verdict::Supported
    } else {
        Verdict::Refuted
    }
}
