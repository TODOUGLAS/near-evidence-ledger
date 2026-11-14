//! Evidence Ledger registry (NEAR testnet).
//!
//! What it stores, and why a contract is the right tool:
//!  * **Runs**: a publisher commits, in ONE transaction, to (spec_hash, snapshot_hash, code_hash, results_hash) plus
//!    the eight claim verdicts with values, 90% intervals and thresholds. Anyone can re-run the open-source pipeline on
//!    the same frozen snapshot and compare (`ledger verify`).
//!  * **The verdict rule runs on-chain**: `publish_run` and `challenge` recompute the verdict from the numbers they
//!    carry and abort when a published verdict contradicts its own value/interval/threshold.
//!  * **Challenges**: permissionless. A challenger posts a different snapshot hash / value / interval / threshold; the
//!    contract computes the alternative verdict and records whether it flips the original.
//!  * **Pre-registered forecasts**: a conformal interval for a future week is committed before the data exists, and can
//!    be resolved after the target week ends. `scoreboard` is the public hit-rate record.
//!
//! The contract does not fetch data and cannot know whether a snapshot hash is "the true data": it makes claims
//! commit-able, comparable and disputable. It is not an oracle. See README, "Honest limits".
//! Storage is paid by the caller (attached deposit, excess refunded).

mod rule;
#[cfg(test)]
mod tests;

use near_sdk::json_types::U64;
use near_sdk::serde_json::json;
use near_sdk::store::{LookupMap, LookupSet, Vector};
use near_sdk::{
    env, near, require, AccountId, BorshStorageKey, NearToken, PanicOnDefault, Promise,
};

pub use rule::{evaluate, Comparator, Verdict};

pub const VERSION: &str = "evidence-ledger 0.1.1";
const MAX_VERDICTS: usize = 32;
const MAX_TEXT: usize = 280;
const MAX_CHALLENGES_PER_RUN: usize = 100;
const MAX_DISPUTES: usize = 5;
const MAX_HORIZON_MS: u64 = 400 * 24 * 3600 * 1000;

#[derive(BorshStorageKey)]
#[near]
enum Key {
    Runs,
    RunDedup,
    Challenges,
    RunChallenges,
    Predictions,
    PredDedup,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug)]
pub struct VerdictIn {
    pub claim_id: String,
    pub comparator: Comparator,
    /// fixed point, 6 decimals
    pub threshold: i64,
    pub value: i64,
    pub ci_lo: Option<i64>,
    pub ci_hi: Option<i64>,
    pub verdict: Verdict,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug)]
pub struct RunIn {
    pub spec_hash: String,
    pub snapshot_hash: String,
    pub code_hash: String,
    pub results_hash: String,
    /// last complete data week, e.g. "2026-11-08"
    pub data_through: String,
    pub backtest_cov80_bp: u32,
    pub backtest_cov95_bp: u32,
    pub note: String,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug)]
pub struct Run {
    pub id: u64,
    pub attester: AccountId,
    pub ts_ms: u64,
    pub height: u64,
    pub meta: RunIn,
    pub verdicts: Vec<VerdictIn>,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug)]
pub struct Challenge {
    pub id: u64,
    pub run_id: u64,
    pub claim_id: String,
    pub challenger: AccountId,
    pub ts_ms: u64,
    pub alt_snapshot_hash: String,
    pub alt_value: i64,
    pub alt_ci_lo: Option<i64>,
    pub alt_ci_hi: Option<i64>,
    pub alt_threshold: i64,
    /// computed by the contract with the same rule
    pub alt_verdict: Verdict,
    pub flips: bool,
    pub evidence: String,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug)]
pub struct PredictionIn {
    pub metric: String,
    pub origin_week: String,
    pub target_week: String,
    /// end of the target week, unix ms; resolution is allowed only after it
    pub target_end_ms: U64,
    /// nominal coverage in basis points, e.g. 8000 = 80%
    pub level_bp: u32,
    pub point: i64,
    pub lo: i64,
    pub hi: i64,
    pub snapshot_hash: String,
    pub method: String,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug)]
pub struct Resolution {
    pub resolver: AccountId,
    pub ts_ms: u64,
    pub observed: i64,
    pub source_hash: String,
    pub hit: bool,
}

#[near(serializers = [json, borsh])]
#[derive(Clone, Debug)]
pub struct Prediction {
    pub id: u64,
    pub attester: AccountId,
    pub ts_ms: u64,
    pub body: PredictionIn,
    pub resolution: Option<Resolution>,
    /// later, different observations submitted for the same prediction (the record stays visible)
    pub disputes: Vec<Resolution>,
}

#[near(serializers = [json])]
pub struct Score {
    pub predictions: u64,
    pub resolved: u64,
    /// hits by the FIRST recorded observation (whoever resolved first)
    pub hits: u64,
    /// hits where EVERY recorded observation (first and disputes) is inside the interval: the strict count
    pub hits_strict: u64,
    pub disputed: u64,
    /// hits / resolved in basis points (0 when nothing is resolved)
    pub hit_rate_bp: u64,
    /// mean nominal level of the resolved predictions, basis points
    pub mean_level_bp: u64,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct Registry {
    runs: Vector<Run>,
    run_dedup: LookupSet<Vec<u8>>,
    challenges: Vector<Challenge>,
    run_challenges: LookupMap<u64, Vec<u64>>,
    predictions: Vector<Prediction>,
    pred_dedup: LookupSet<Vec<u8>>,
}

fn is_hash(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn check_hash(name: &str, s: &str) {
    require!(
        is_hash(s),
        format!("E_HASH: {name} must be 64 lowercase hex chars")
    );
}
fn check_text(name: &str, s: &str, max: usize) {
    require!(
        s.len() <= max,
        format!("E_TEXT: {name} longer than {max} bytes")
    );
}
fn ci_pair(lo: Option<i64>, hi: Option<i64>) -> Option<(i64, i64)> {
    match (lo, hi) {
        (Some(l), Some(h)) => {
            require!(l <= h, "E_CI: ci_lo must be <= ci_hi");
            Some((l, h))
        }
        (None, None) => None,
        _ => env::panic_str("E_CI: give both ci_lo and ci_hi, or neither"),
    }
}
fn now_ms() -> u64 {
    env::block_timestamp() / 1_000_000
}
fn emit(event: &str, data: near_sdk::serde_json::Value) {
    env::log_str(&format!(
        "EVENT_JSON:{}",
        json!({"standard": "evidence_ledger", "version": "1.0.0", "event": event, "data": [data]})
    ));
}

impl Registry {
    /// Pay for the storage this call added (caller's attached deposit); refund the rest.
    fn settle_storage(&self, before: u64) {
        let used = env::storage_usage().saturating_sub(before) as u128;
        let cost = used * env::storage_byte_cost().as_yoctonear();
        let dep = env::attached_deposit().as_yoctonear();
        require!(
            dep >= cost,
            format!("E_DEPOSIT: attach at least {cost} yoctoNEAR for storage (attached {dep})")
        );
        if dep > cost {
            let _ = Promise::new(env::predecessor_account_id())
                .transfer(NearToken::from_yoctonear(dep - cost));
        }
    }
}

impl Registry {
    fn add_prediction(&mut self, p: PredictionIn) -> u64 {
        check_text("metric", &p.metric, 64);
        check_text("origin_week", &p.origin_week, 16);
        check_text("target_week", &p.target_week, 16);
        check_text("method", &p.method, 64);
        check_hash("snapshot_hash", &p.snapshot_hash);
        require!(!p.metric.is_empty(), "E_TEXT: metric required");
        require!(
            (5_000..=9_900).contains(&p.level_bp),
            "E_RANGE: level_bp must be 5000..=9900"
        );
        require!(
            p.lo <= p.point && p.point <= p.hi,
            "E_RANGE: need lo <= point <= hi"
        );
        let end = p.target_end_ms.0;
        require!(
            end > now_ms(),
            "E_TIME: target week must end in the future (no backdating)"
        );
        require!(
            end <= now_ms() + MAX_HORIZON_MS,
            "E_TIME: horizon longer than 400 days"
        );
        let who = env::predecessor_account_id();
        let mut key = who.as_bytes().to_vec();
        key.extend_from_slice(p.metric.as_bytes());
        key.extend_from_slice(p.target_week.as_bytes());
        key.extend_from_slice(&p.level_bp.to_le_bytes());
        require!(
            self.pred_dedup.insert(key),
            "E_DUP: this attester already registered this metric/target week/level"
        );
        let id = self.predictions.len() as u64;
        emit(
            "prediction_registered",
            json!({"prediction_id": id, "attester": who, "metric": p.metric, "target_week": p.target_week,
                   "lo": p.lo, "hi": p.hi, "level_bp": p.level_bp}),
        );
        self.predictions.push(Prediction {
            id,
            attester: who,
            ts_ms: now_ms(),
            body: p,
            resolution: None,
            disputes: vec![],
        });
        id
    }
}

#[near]
impl Registry {
    #[init]
    pub fn new() -> Self {
        Self {
            runs: Vector::new(Key::Runs),
            run_dedup: LookupSet::new(Key::RunDedup),
            challenges: Vector::new(Key::Challenges),
            run_challenges: LookupMap::new(Key::RunChallenges),
            predictions: Vector::new(Key::Predictions),
            pred_dedup: LookupSet::new(Key::PredDedup),
        }
    }

    // ------------------------------------------------------------------ runs
    /// Commit a full ledger run. Aborts when a verdict contradicts its own numbers.
    #[payable]
    pub fn publish_run(&mut self, run: RunIn, verdicts: Vec<VerdictIn>) -> u64 {
        let before = env::storage_usage();
        check_hash("spec_hash", &run.spec_hash);
        check_hash("snapshot_hash", &run.snapshot_hash);
        check_hash("code_hash", &run.code_hash);
        check_hash("results_hash", &run.results_hash);
        check_text("note", &run.note, MAX_TEXT);
        check_text("data_through", &run.data_through, 16);
        require!(
            run.backtest_cov80_bp <= 10_000 && run.backtest_cov95_bp <= 10_000,
            "E_RANGE: coverage in basis points must be <= 10000"
        );
        require!(
            !verdicts.is_empty() && verdicts.len() <= MAX_VERDICTS,
            "E_VERDICTS: 1..=32 verdicts per run"
        );
        let mut seen: Vec<&str> = vec![];
        for v in &verdicts {
            require!(
                !v.claim_id.is_empty() && v.claim_id.len() <= 16,
                "E_CLAIM: claim_id 1..=16 bytes"
            );
            require!(
                !seen.contains(&v.claim_id.as_str()),
                "E_CLAIM: duplicate claim_id in run"
            );
            seen.push(&v.claim_id);
            let ci = ci_pair(v.ci_lo, v.ci_hi);
            let want = evaluate(v.value, v.comparator, v.threshold, ci);
            require!(
                want == v.verdict,
                format!(
                    "E_VERDICT: claim {} says {:?} but its own value/interval/threshold give {:?}",
                    v.claim_id, v.verdict, want
                )
            );
        }
        let who = env::predecessor_account_id();
        let mut key = who.as_bytes().to_vec();
        key.extend_from_slice(run.spec_hash.as_bytes());
        key.extend_from_slice(run.snapshot_hash.as_bytes());
        key.extend_from_slice(run.code_hash.as_bytes());
        key.extend_from_slice(run.results_hash.as_bytes());
        require!(
            self.run_dedup.insert(key),
            "E_DUP: this attester already published this exact run"
        );
        let id = self.runs.len() as u64;
        emit(
            "run_published",
            json!({"run_id": id, "attester": who, "snapshot_hash": run.snapshot_hash,
                   "results_hash": run.results_hash, "n_claims": verdicts.len()}),
        );
        self.runs.push(Run {
            id,
            attester: who,
            ts_ms: now_ms(),
            height: env::block_height(),
            meta: run,
            verdicts,
        });
        self.settle_storage(before);
        id
    }

    // ------------------------------------------------------------ challenges
    /// Permissionless dispute of one verdict of a run. The contract recomputes the alternative verdict.
    /// `alt_threshold` defaults to the run's threshold.
    #[payable]
    #[allow(clippy::too_many_arguments)]
    pub fn challenge(
        &mut self,
        run_id: u64,
        claim_id: String,
        alt_snapshot_hash: String,
        alt_value: i64,
        alt_ci_lo: Option<i64>,
        alt_ci_hi: Option<i64>,
        alt_threshold: Option<i64>,
        evidence: String,
    ) -> u64 {
        let before = env::storage_usage();
        check_hash("alt_snapshot_hash", &alt_snapshot_hash);
        check_text("evidence", &evidence, MAX_TEXT);
        let run = self
            .runs
            .get(run_id as u32)
            .unwrap_or_else(|| env::panic_str("E_RUN: no such run"));
        let orig = run
            .verdicts
            .iter()
            .find(|v| v.claim_id == claim_id)
            .unwrap_or_else(|| env::panic_str("E_CLAIM: claim not in this run"));
        let thr = alt_threshold.unwrap_or(orig.threshold);
        let ci = ci_pair(alt_ci_lo, alt_ci_hi);
        let alt_verdict = evaluate(alt_value, orig.comparator, thr, ci);
        let flips = alt_verdict != orig.verdict;
        let mut ids = self
            .run_challenges
            .get(&run_id)
            .cloned()
            .unwrap_or_default();
        require!(
            ids.len() < MAX_CHALLENGES_PER_RUN,
            "E_FULL: challenge limit reached for this run"
        );
        let id = self.challenges.len() as u64;
        ids.push(id);
        self.run_challenges.insert(run_id, ids);
        let who = env::predecessor_account_id();
        emit(
            "challenged",
            json!({"challenge_id": id, "run_id": run_id, "claim_id": claim_id, "challenger": who,
                   "flips": flips, "alt_verdict": alt_verdict}),
        );
        self.challenges.push(Challenge {
            id,
            run_id,
            claim_id,
            challenger: who,
            ts_ms: now_ms(),
            alt_snapshot_hash,
            alt_value,
            alt_ci_lo,
            alt_ci_hi,
            alt_threshold: thr,
            alt_verdict,
            flips,
            evidence,
        });
        self.settle_storage(before);
        id
    }

    // ----------------------------------------------------------- predictions
    /// Commit an interval forecast for a future week. Cannot be backdated: the target week must end in the future.
    #[payable]
    pub fn register_prediction(&mut self, p: PredictionIn) -> u64 {
        let before = env::storage_usage();
        let id = self.add_prediction(p);
        self.settle_storage(before);
        id
    }

    /// Same as `register_prediction` for several forecasts in one transaction (all or nothing).
    #[payable]
    pub fn register_predictions(&mut self, items: Vec<PredictionIn>) -> Vec<u64> {
        require!(
            !items.is_empty() && items.len() <= 40,
            "E_BATCH: 1..=40 predictions per call"
        );
        let before = env::storage_usage();
        let ids = items.into_iter().map(|p| self.add_prediction(p)).collect();
        self.settle_storage(before);
        ids
    }

    /// Record the observed value after the target week ended. The first resolution counts; a later, different
    /// observation is stored as a visible dispute (it never silently overwrites).
    #[payable]
    pub fn resolve(&mut self, prediction_id: u64, observed: i64, source_hash: String) -> bool {
        let before = env::storage_usage();
        check_hash("source_hash", &source_hash);
        let mut p = self
            .predictions
            .get(prediction_id as u32)
            .unwrap_or_else(|| env::panic_str("E_PRED: no such prediction"))
            .clone();
        require!(
            now_ms() >= p.body.target_end_ms.0,
            "E_TIME: target week has not ended yet"
        );
        let hit = observed >= p.body.lo && observed <= p.body.hi;
        let r = Resolution {
            resolver: env::predecessor_account_id(),
            ts_ms: now_ms(),
            observed,
            source_hash,
            hit,
        };
        match &p.resolution {
            None => {
                emit(
                    "prediction_resolved",
                    json!({"prediction_id": prediction_id, "observed": observed, "hit": hit}),
                );
                p.resolution = Some(r);
            }
            Some(first) => {
                require!(
                    first.observed != observed,
                    "E_DUP: same observation already recorded"
                );
                require!(
                    p.disputes.len() < MAX_DISPUTES,
                    "E_FULL: dispute limit reached"
                );
                emit(
                    "resolution_disputed",
                    json!({"prediction_id": prediction_id, "observed": observed}),
                );
                p.disputes.push(r);
            }
        }
        *self.predictions.get_mut(prediction_id as u32).unwrap() = p;
        self.settle_storage(before);
        hit
    }

    // ----------------------------------------------------------------- views
    pub fn info(&self) -> near_sdk::serde_json::Value {
        json!({"version": VERSION, "runs": self.runs.len(), "challenges": self.challenges.len(),
               "predictions": self.predictions.len(),
               "rule": "claims.py verdict: interval fully passes => SUPPORTED, fully fails => REFUTED, else INCONCLUSIVE; no interval: within 5% of threshold => INCONCLUSIVE",
               "fixed_point": "values are integers scaled by 1e6"})
    }
    /// Pure helper: what verdict does the on-chain rule give for these numbers?
    pub fn evaluate_verdict(
        &self,
        value: i64,
        comparator: Comparator,
        threshold: i64,
        ci_lo: Option<i64>,
        ci_hi: Option<i64>,
    ) -> Verdict {
        evaluate(value, comparator, threshold, ci_pair(ci_lo, ci_hi))
    }
    pub fn run_count(&self) -> u32 {
        self.runs.len()
    }
    pub fn get_run(&self, run_id: u64) -> Option<Run> {
        self.runs.get(run_id as u32).cloned()
    }
    pub fn list_runs(&self, from: Option<u32>, limit: Option<u32>) -> Vec<Run> {
        let from = from.unwrap_or(0);
        let limit = limit.unwrap_or(10).min(50);
        (from..self.runs.len().min(from.saturating_add(limit)))
            .filter_map(|i| self.runs.get(i).cloned())
            .collect()
    }
    pub fn get_challenges(&self, run_id: u64) -> Vec<Challenge> {
        self.run_challenges
            .get(&run_id)
            .map(|ids| {
                ids.iter()
                    .filter_map(|i| self.challenges.get(*i as u32).cloned())
                    .collect()
            })
            .unwrap_or_default()
    }
    pub fn prediction_count(&self) -> u32 {
        self.predictions.len()
    }
    pub fn get_prediction(&self, prediction_id: u64) -> Option<Prediction> {
        self.predictions.get(prediction_id as u32).cloned()
    }
    pub fn list_predictions(&self, from: Option<u32>, limit: Option<u32>) -> Vec<Prediction> {
        let from = from.unwrap_or(0);
        let limit = limit.unwrap_or(20).min(100);
        (from..self.predictions.len().min(from.saturating_add(limit)))
            .filter_map(|i| self.predictions.get(i).cloned())
            .collect()
    }
    pub fn scoreboard(&self, attester: AccountId) -> Score {
        let (mut n, mut res, mut hits, mut strict, mut dis, mut lvl) =
            (0u64, 0u64, 0u64, 0u64, 0u64, 0u64);
        for p in self.predictions.iter().filter(|p| p.attester == attester) {
            n += 1;
            if let Some(r) = &p.resolution {
                res += 1;
                lvl += p.body.level_bp as u64;
                if r.hit {
                    hits += 1;
                    if p.disputes.iter().all(|d| d.hit) {
                        strict += 1;
                    }
                }
                if !p.disputes.is_empty() {
                    dis += 1;
                }
            }
        }
        Score {
            predictions: n,
            resolved: res,
            hits,
            hits_strict: strict,
            disputed: dis,
            hit_rate_bp: (hits * 10_000).checked_div(res).unwrap_or(0),
            mean_level_bp: lvl.checked_div(res).unwrap_or(0),
        }
    }
}
