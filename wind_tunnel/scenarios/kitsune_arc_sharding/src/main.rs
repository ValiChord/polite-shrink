//! Arc-sharding scenario — SKELETON (work item 1: proves the dependency graph
//! builds against the sharding fork; the real scenario is work item 4).
//!
//! Planned shape: N agents join at FULL arc, publish chatter ops, then the
//! sharding controller shrinks toward target_redundancy R. A churn cohort is a
//! second short `--duration` invocation whose exit forces unresponsive-marking,
//! regrow, handoff, and the storm brake. Coverage/floor analysis runs post-hoc
//! on the recorded metrics.
//!
//! Behaviour below is publish-chatter only, borrowed from upstream
//! kitsune_continuous_flow while the skeleton stands in for the real scenario.

use kitsune_wind_tunnel_runner::prelude::*;
use rand::Rng;
use std::time::Duration;

fn agent_setup(ctx: &mut AgentContext<KitsuneRunnerContext, KitsuneAgentContext>) -> HookResult {
    create_chatter(ctx)?;
    join_chatter_network(ctx)
}

fn behaviour(
    ctx: &mut AgentContext<KitsuneRunnerContext, KitsuneAgentContext>,
) -> anyhow::Result<()> {
    // Number of chatter ops published per interval; env-tunable.
    let number_of_messages: u8 = std::env::var("NUM_MESSAGES")
        .unwrap_or("3".to_string())
        .parse()
        .expect("NUM_MESSAGES must be a number < 256");
    let timestamp = std::time::UNIX_EPOCH
        .elapsed()
        .expect("time went backwards")
        .as_millis();
    let messages = (0..number_of_messages)
        .map(|i| format!("op_{}_{}_{}", ctx.agent_index(), timestamp, i))
        .collect();
    say(ctx, messages)?;

    let interval = rand::rng().random_range(10..1000);
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
    .use_agent_setup(agent_setup)
    .use_agent_behaviour(behaviour)
    .with_default_duration_s(30);
    run(builder)?;
    Ok(())
}
