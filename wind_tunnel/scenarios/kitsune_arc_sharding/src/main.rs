//! Arc-sharding scenario: measure the V3 polite-shrink controller under
//! Wind Tunnel on real iroh transport.
//!
//! One invocation = one cohort of in-process agents:
//!
//! - **Main cohort**: long `--duration`. Agents join at FULL arc, publish
//!   chatter ops on a steady cadence, and the sharding controller shrinks
//!   their arcs toward target redundancy R (set
//!   `K2_SHARDING_CLAMP_MIN_PEERS` below the total agent count or the
//!   controller never engages).
//! - **Churn cohort** (storm runs): a second invocation with the **same
//!   `--run-id`** (the run id is the space id — same id = same DHT) and a
//!   short `--duration`. Its process exit is abrupt from the network's
//!   point of view: survivors must notice the losses, cancel suspect
//!   intents (storm brake), regrow, and hand off.
//!
//! All controller observability comes from the instrumented client's
//! `arc_state` + `sharding_event` metrics; run with
//! `--reporter influx-file` (+ `WT_METRICS_DIR`) so
//! `analysis/analyze_run.py` can reconstruct coverage. Orchestrated end to
//! end by `run_experiment.sh`.

use kitsune_wind_tunnel_runner::prelude::*;
use rand::Rng;
use std::io::Write;
use std::time::Duration;

fn agent_setup(ctx: &mut AgentContext<KitsuneRunnerContext, KitsuneAgentContext>) -> HookResult {
    create_chatter(ctx)?;
    join_chatter_network(ctx)
}

/// Op-log support for the post-run reachability check: when K2_OP_LOG_DIR is
/// set, every publish appends the op ids to published_<agent>.jsonl and the
/// teardown dumps the agent's full held-op inventory to held_<agent>.json.
/// Filenames use the chatter id (not the agent index, which collides across
/// the main and churn cohort processes).
mod op_log {
    use super::*;

    pub fn dir() -> Option<std::path::PathBuf> {
        std::env::var("K2_OP_LOG_DIR").ok().map(Into::into)
    }

    fn now_ms() -> u128 {
        std::time::UNIX_EPOCH
            .elapsed()
            .expect("time went backwards")
            .as_millis()
    }

    pub fn append_published(agent: &str, op_ids: &[String]) -> anyhow::Result<()> {
        let Some(dir) = dir() else { return Ok(()) };
        std::fs::create_dir_all(&dir)?;
        let line = serde_json::json!({"t_ms": now_ms() as u64, "agent": agent, "op_ids": op_ids});
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(dir.join(format!("published_{agent}.jsonl")))?;
        writeln!(file, "{line}")?;
        Ok(())
    }

    pub fn write_held(agent: &str, op_ids: &[String]) -> anyhow::Result<()> {
        let Some(dir) = dir() else { return Ok(()) };
        std::fs::create_dir_all(&dir)?;
        let doc = serde_json::json!({"t_ms": now_ms() as u64, "agent": agent, "op_ids": op_ids});
        std::fs::write(
            dir.join(format!("held_{agent}.json")),
            serde_json::to_vec(&doc)?,
        )?;
        Ok(())
    }
}

fn agent_teardown(
    ctx: &mut AgentContext<KitsuneRunnerContext, KitsuneAgentContext>,
) -> HookResult {
    if op_log::dir().is_none() {
        return Ok(());
    }
    let agent = ctx.get().chatter_id();
    let chatter = ctx.get().chatter();
    let held: Vec<String> = ctx
        .runner_context()
        .executor()
        .execute_in_place(async move {
            Ok(chatter
                .held_op_ids()
                .await
                .iter()
                .map(|id| id.to_string())
                .collect())
        })?;
    op_log::write_held(&agent, &held)?;
    Ok(())
}

fn behaviour(
    ctx: &mut AgentContext<KitsuneRunnerContext, KitsuneAgentContext>,
) -> anyhow::Result<()> {
    // Ops published per interval and mean interval between publishes.
    let number_of_messages: u8 = std::env::var("NUM_MESSAGES")
        .unwrap_or("3".to_string())
        .parse()
        .expect("NUM_MESSAGES must be a number < 256");
    let publish_interval_ms: u64 = std::env::var("PUBLISH_INTERVAL_MS")
        .unwrap_or("1000".to_string())
        .parse()
        .expect("PUBLISH_INTERVAL_MS must be a number of milliseconds");

    let timestamp = std::time::UNIX_EPOCH
        .elapsed()
        .expect("time went backwards")
        .as_millis();
    let messages: Vec<String> = (0..number_of_messages)
        .map(|i| format!("op_{}_{}_{}", ctx.agent_index(), timestamp, i))
        .collect();
    // Publish via the chatter directly (the runner's `say` helper discards
    // the op ids, which the reachability check needs).
    let chatter = ctx.get().chatter();
    let op_ids: Vec<String> = ctx
        .runner_context()
        .executor()
        .execute_in_place(async move {
            Ok(chatter
                .say(messages)
                .await?
                .iter()
                .map(|id| id.to_string())
                .collect())
        })?;
    op_log::append_published(&ctx.get().chatter_id(), &op_ids)?;

    // Uniform jitter of 0.5x–1.5x around the configured interval so agents
    // don't publish in lockstep.
    let interval = rand::rng().random_range(publish_interval_ms / 2..=publish_interval_ms * 3 / 2);
    ctx.runner_context().executor().execute_in_place(async {
        tokio::time::sleep(Duration::from_millis(interval)).await;
        Ok(())
    })
}

fn main() -> WindTunnelResult<()> {
    let builder = KitsuneScenarioDefinitionBuilder::<
        KitsuneRunnerContext,
        KitsuneAgentContext,
    >::new_with_init("kitsune_arc_sharding")?
    .into_std()
    .add_capture_env("NUM_MESSAGES")
    .add_capture_env("PUBLISH_INTERVAL_MS")
    // Sharding knobs read by kitsune_client_instrumented; captured so every
    // run records the controller settings it ran with.
    .add_capture_env("K2_INITIAL_ARC")
    .add_capture_env("K2_SHARDING_TARGET_REDUNDANCY")
    .add_capture_env("K2_SHARDING_CLAMP_MIN_PEERS")
    .add_capture_env("K2_SHARDING_CHECK_INTERVAL_MS")
    .add_capture_env("K2_SHARDING_GROW_PERSISTENCE")
    .add_capture_env("K2_SHARDING_SHRINK_PERSISTENCE")
    .add_capture_env("K2_SHARDING_INTENT_WAIT")
    .add_capture_env("K2_SHARDING_INTENT_MIN_WAIT_MS")
    .add_capture_env("K2_SHARDING_LAG_FLOOR_MS")
    .add_capture_env("K2_SHARDING_LAG_CEILING_MS")
    .add_capture_env("K2_ARC_SAMPLE_INTERVAL_MS")
    .add_capture_env("K2_OP_LOG_DIR")
    .use_agent_setup(agent_setup)
    .use_agent_behaviour(behaviour)
    .use_agent_teardown(agent_teardown)
    .with_default_duration_s(300);
    run(builder)?;
    Ok(())
}
