use super::*;
use near_sdk::test_utils::{get_logs, VMContextBuilder};
use near_sdk::testing_env;

const H1: &str = "1111111111111111111111111111111111111111111111111111111111111111";
const H2: &str = "2222222222222222222222222222222222222222222222222222222222222222";
const H3: &str = "3333333333333333333333333333333333333333333333333333333333333333";
const H4: &str = "4444444444444444444444444444444444444444444444444444444444444444";
const H5: &str = "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd";
const WEEK_MS: u64 = 7 * 24 * 3600 * 1000;
const T0_MS: u64 = 1_800_000_000_000;

fn ctx(who: &str, ts_ms: u64, deposit_near: f64) {
    let mut b = VMContextBuilder::new();
    b.predecessor_account_id(who.parse().unwrap())
        .signer_account_id(who.parse().unwrap())
        .block_timestamp(ts_ms * 1_000_000)
        .attached_deposit(NearToken::from_millinear((deposit_near * 1000.0) as u128));
    testing_env!(b.build());
}
fn fresh() -> Registry {
    ctx("pub.testnet", T0_MS, 0.0);
    Registry::new()
}
fn run_in(results: &str) -> RunIn {
    RunIn {
        spec_hash: H1.into(),
        snapshot_hash: H2.into(),
        code_hash: H3.into(),
        results_hash: results.into(),
        data_through: "2026-11-08".into(),
        backtest_cov80_bp: 7800,
        backtest_cov95_bp: 9200,
        note: "test".into(),
    }
}
fn v(
    id: &str,
    c: Comparator,
    thr: f64,
    val: f64,
    ci: Option<(f64, f64)>,
    verdict: Verdict,
) -> VerdictIn {
    let m = |x: f64| (x * 1e6).round() as i64;
    VerdictIn {
        claim_id: id.into(),
        comparator: c,
        threshold: m(thr),
        value: m(val),
        ci_lo: ci.map(|c| m(c.0)),
        ci_hi: ci.map(|c| m(c.1)),
        verdict,
    }
}
fn sample() -> Vec<VerdictIn> {
    vec![
        v(
            "C1",
            Comparator::Ge,
            1.0,
            0.15,
            Some((0.14, 0.19)),
            Verdict::Refuted,
        ),
        v(
            "C4",
            Comparator::Ge,
            1.0,
            1.54,
            Some((1.42, 1.75)),
            Verdict::Supported,
        ),
        v(
            "C7",
            Comparator::Ge,
            10.0,
            10.0,
            None,
            Verdict::Inconclusive,
        ),
    ]
}
fn publish(c: &mut Registry) -> u64 {
    ctx("pub.testnet", T0_MS, 1.0);
    c.publish_run(run_in(H4), sample())
}

#[test]
fn verdict_rule_basic() {
    let m = |x: f64| (x * 1e6).round() as i64;
    let ge = Comparator::Ge;
    assert_eq!(
        evaluate(m(2.0), ge, m(1.0), Some((m(1.5), m(2.5)))),
        Verdict::Supported
    );
    assert_eq!(
        evaluate(m(0.5), ge, m(1.0), Some((m(0.1), m(0.9)))),
        Verdict::Refuted
    );
    assert_eq!(
        evaluate(m(1.0), ge, m(1.0), Some((m(0.9), m(1.1)))),
        Verdict::Inconclusive
    );
    // no interval: inside +-5% => inconclusive; outside => decided by the point
    assert_eq!(evaluate(m(10.0), ge, m(10.0), None), Verdict::Inconclusive);
    assert_eq!(evaluate(m(10.4), ge, m(10.0), None), Verdict::Inconclusive);
    assert_eq!(evaluate(m(10.6), ge, m(10.0), None), Verdict::Supported);
    assert_eq!(evaluate(m(9.4), ge, m(10.0), None), Verdict::Refuted);
    assert_eq!(
        evaluate(m(2.5), Comparator::Le, m(5.0), None),
        Verdict::Supported
    );
    assert_eq!(
        evaluate(m(5.5), Comparator::Le, m(5.0), None),
        Verdict::Refuted
    );
}

#[test]
fn verdict_rule_matches_python_vectors() {
    let raw = include_str!("../tests/verdict_vectors.json");
    let cases: Vec<near_sdk::serde_json::Value> = near_sdk::serde_json::from_str(raw).unwrap();
    assert!(cases.len() >= 400);
    for c in cases {
        let value = c["value"].as_i64().unwrap();
        let thr = c["threshold"].as_i64().unwrap();
        let cmp = if c["comparator"] == ">=" {
            Comparator::Ge
        } else {
            Comparator::Le
        };
        let ci = if c["ci"].is_null() {
            None
        } else {
            Some((c["ci"][0].as_i64().unwrap(), c["ci"][1].as_i64().unwrap()))
        };
        let want = match c["verdict"].as_str().unwrap() {
            "SUPPORTED" => Verdict::Supported,
            "REFUTED" => Verdict::Refuted,
            _ => Verdict::Inconclusive,
        };
        assert_eq!(evaluate(value, cmp, thr, ci), want, "case {c}");
    }
}

#[test]
fn publish_and_read_back() {
    let mut c = fresh();
    let id = publish(&mut c);
    assert_eq!(id, 0);
    assert_eq!(c.run_count(), 1);
    let r = c.get_run(0).unwrap();
    assert_eq!(r.attester.as_str(), "pub.testnet");
    assert_eq!(r.verdicts.len(), 3);
    assert_eq!(r.meta.snapshot_hash, H2);
    assert!(get_logs().iter().any(|l| l.contains("run_published")));
    assert_eq!(c.list_runs(None, None).len(), 1);
}

#[test]
#[should_panic(expected = "E_VERDICT")]
fn publish_rejects_contradicting_verdict() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    let mut s = sample();
    s[0].verdict = Verdict::Supported; // C1 interval [0.14,0.19] fails >= 1.0
    c.publish_run(run_in(H4), s);
}

#[test]
#[should_panic(expected = "E_DUP")]
fn publish_rejects_exact_duplicate() {
    let mut c = fresh();
    publish(&mut c);
    publish(&mut c);
}

#[test]
fn same_results_by_other_attester_is_allowed() {
    let mut c = fresh();
    publish(&mut c);
    ctx("other.testnet", T0_MS + 1, 1.0);
    assert_eq!(c.publish_run(run_in(H4), sample()), 1);
    assert_eq!(c.get_run(1).unwrap().attester.as_str(), "other.testnet");
}

#[test]
#[should_panic(expected = "E_HASH")]
fn publish_rejects_bad_hash() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    let mut r = run_in(H4);
    r.snapshot_hash = "XYZ".into();
    c.publish_run(r, sample());
}

#[test]
#[should_panic(expected = "E_DEPOSIT")]
fn publish_requires_storage_deposit() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 0.0);
    c.publish_run(run_in(H4), sample());
}

#[test]
#[should_panic(expected = "E_CI")]
fn half_interval_rejected() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    let mut s = sample();
    s[0].ci_hi = None;
    c.publish_run(run_in(H4), s);
}

#[test]
fn challenge_flips_and_is_recorded() {
    let mut c = fresh();
    publish(&mut c);
    ctx("chal.testnet", T0_MS + 5, 1.0);
    let m = |x: f64| (x * 1e6).round() as i64;
    // other data says C1 interval is [1.05, 1.3]: SUPPORTED, flips REFUTED
    let id = c.challenge(
        0,
        "C1".into(),
        H5.into(),
        m(1.1),
        Some(m(1.05)),
        Some(m(1.3)),
        None,
        "alt provider".into(),
    );
    assert_eq!(id, 0);
    let ch = c.get_challenges(0);
    assert_eq!(ch.len(), 1);
    assert!(ch[0].flips);
    assert_eq!(ch[0].alt_verdict, Verdict::Supported);
    assert_eq!(ch[0].challenger.as_str(), "chal.testnet");
    // a challenge that agrees does not flip
    let _ = c.challenge(
        0,
        "C4".into(),
        H5.into(),
        m(1.6),
        Some(m(1.4)),
        Some(m(1.8)),
        None,
        "agree".into(),
    );
    assert!(!c.get_challenges(0)[1].flips);
    // threshold challenge: C4 with threshold 1.8 -> interval partly below => INCONCLUSIVE, flips
    let _ = c.challenge(
        0,
        "C4".into(),
        H2.into(),
        m(1.54),
        Some(m(1.42)),
        Some(m(1.75)),
        Some(m(1.6)),
        "harder bar".into(),
    );
    assert!(c.get_challenges(0)[2].flips);
    assert_eq!(c.get_challenges(0)[2].alt_verdict, Verdict::Inconclusive);
}

#[test]
#[should_panic(expected = "E_CLAIM")]
fn challenge_unknown_claim() {
    let mut c = fresh();
    publish(&mut c);
    ctx("chal.testnet", T0_MS + 5, 1.0);
    c.challenge(0, "C9".into(), H5.into(), 1, None, None, None, "x".into());
}

#[test]
#[should_panic(expected = "E_RUN")]
fn challenge_unknown_run() {
    let mut c = fresh();
    ctx("chal.testnet", T0_MS + 5, 1.0);
    c.challenge(7, "C1".into(), H5.into(), 1, None, None, None, "x".into());
}

fn pred(metric: &str, week: &str, end: u64, lo: i64, point: i64, hi: i64) -> PredictionIn {
    PredictionIn {
        metric: metric.into(),
        origin_week: "2026-11-08".into(),
        target_week: week.into(),
        target_end_ms: U64(end),
        level_bp: 8000,
        point,
        lo,
        hi,
        snapshot_hash: H2.into(),
        method: "conformal-h1".into(),
    }
}

#[test]
fn prediction_lifecycle_and_scoreboard() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    let end = T0_MS + WEEK_MS;
    let a = c.register_prediction(pred(
        "active_accounts",
        "2026-11-15",
        end,
        60_000,
        70_000,
        80_000,
    ));
    let b = c.register_prediction(pred("weekly_txns", "2026-11-15", end, 1_000, 2_000, 3_000));
    assert_eq!((a, b), (0, 1));
    assert_eq!(c.prediction_count(), 2);
    ctx("anyone.testnet", end + 1000, 1.0);
    assert!(c.resolve(0, 71_000, H5.into())); // hit
    assert!(!c.resolve(1, 9_999, H5.into())); // miss
    let s = c.scoreboard("pub.testnet".parse().unwrap());
    assert_eq!(
        (
            s.predictions,
            s.resolved,
            s.hits,
            s.hit_rate_bp,
            s.mean_level_bp
        ),
        (2, 2, 1, 5000, 8000)
    );
    // a conflicting second observation is a visible dispute, never an overwrite
    ctx("anyone2.testnet", end + 2000, 1.0);
    c.resolve(0, 50_000, H4.into());
    let p = c.get_prediction(0).unwrap();
    assert_eq!(p.resolution.as_ref().unwrap().observed, 71_000);
    assert_eq!(p.disputes.len(), 1);
    let sb = c.scoreboard("pub.testnet".parse().unwrap());
    assert_eq!((sb.disputed, sb.hits, sb.hits_strict), (1, 1, 0)); // first observation hit, the dispute missed
}

#[test]
#[should_panic(expected = "E_TIME: target week has not ended")]
fn resolve_before_end_rejected() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    c.register_prediction(pred("m", "w", T0_MS + WEEK_MS, 1, 2, 3));
    ctx("pub.testnet", T0_MS + 10, 1.0);
    c.resolve(0, 2, H5.into());
}

#[test]
#[should_panic(expected = "E_TIME: target week must end in the future")]
fn no_backdating() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    c.register_prediction(pred("m", "w", T0_MS - 1, 1, 2, 3));
}

#[test]
#[should_panic(expected = "E_RANGE")]
fn prediction_bad_interval() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    c.register_prediction(pred("m", "w", T0_MS + WEEK_MS, 5, 2, 3));
}

#[test]
#[should_panic(expected = "E_DUP")]
fn prediction_duplicate_rejected() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    c.register_prediction(pred("m", "w", T0_MS + WEEK_MS, 1, 2, 3));
    c.register_prediction(pred("m", "w", T0_MS + WEEK_MS, 1, 2, 3));
}

#[test]
fn evaluate_view_and_info() {
    let c = fresh();
    assert_eq!(
        c.evaluate_verdict(
            2_000_000,
            Comparator::Ge,
            1_000_000,
            Some(1_500_000),
            Some(2_500_000)
        ),
        Verdict::Supported
    );
    assert_eq!(c.info()["runs"], 0);
    assert!(c.list_runs(Some(5), Some(5)).is_empty());
    assert!(c.get_challenges(3).is_empty());
}

#[test]
fn batch_predictions() {
    let mut c = fresh();
    ctx("pub.testnet", T0_MS, 1.0);
    let end = T0_MS + WEEK_MS;
    let ids = c.register_predictions(vec![
        pred("a", "w1", end, 1, 2, 3),
        pred("b", "w1", end, 1, 2, 3),
    ]);
    assert_eq!(ids, vec![0, 1]);
    assert_eq!(c.list_predictions(None, None).len(), 2);
}
