//! Arc-sharding observability: per-tick arc-width sampling and a
//! tracing-to-metrics bridge for the sharding controller's events.
//!
//! The controller (kitsune2 fork, `kitsune2_gossip::sharding`) exposes its
//! decisions only as structured `tracing` events; nothing in Wind Tunnel
//! installs a tracing subscriber (the runner uses `env_logger`, which only
//! handles the `log` crate). Installing our own global subscriber here turns
//! those events into Wind Tunnel metrics without touching the fork.

use kitsune2_api::{DhtArc, DynLocalAgent, LocalAgent};
use std::sync::{Arc, OnceLock};
use std::time::Duration;
use tracing::field::{Field, Visit};
use tracing_subscriber::layer::{Context, Layer, SubscriberExt};
use tracing_subscriber::filter::{EnvFilter, filter_fn};
use wind_tunnel_instruments::prelude::{ReportMetric, Reporter};

/// Aborts the sampling task when the owning `WtChatter` is dropped.
#[derive(Debug)]
pub(crate) struct AbortGuard(tokio::task::AbortHandle);

impl Drop for AbortGuard {
    fn drop(&mut self) {
        self.0.abort();
    }
}

/// Periodically report the agent's declared storage arc as an `arc_state`
/// metric. `get_cur_storage_arc` is the same surface the fork's storm test
/// treats as authoritative for coverage, and the only public one — the
/// target-arc hint has no getter.
pub(crate) fn spawn_arc_sampler(
    agent: DynLocalAgent,
    reporter: Arc<Reporter>,
) -> anyhow::Result<AbortGuard> {
    let mut interval_ms: u64 = 1_000;
    crate::env_knob("K2_ARC_SAMPLE_INTERVAL_MS", &mut interval_ms)?;
    let agent_id = agent.agent().to_string();
    let handle = tokio::spawn(async move {
        let mut ticker = tokio::time::interval(Duration::from_millis(interval_ms));
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        loop {
            ticker.tick().await;
            let arc = agent.get_cur_storage_arc();
            let (start, end) = match arc {
                DhtArc::Empty => (0u32, 0u32),
                DhtArc::Arc(start, end) => (start, end),
            };
            reporter.add_custom(
                ReportMetric::new("arc_state")
                    .with_tag("agent_id", agent_id.clone())
                    .with_field("arc_start", start as u64)
                    .with_field("arc_end", end as u64)
                    .with_field("arc_span", arc.arc_span() as u64)
                    .with_field("is_empty", arc.is_empty() as u64),
            );
        }
    });
    Ok(AbortGuard(handle.abort_handle()))
}

/// Install the global tracing subscriber that converts the sharding
/// controller's events into `sharding_event` metrics. Idempotent — all
/// chatters in a process share one reporter, and only the first call
/// installs. Set `K2_LOG` (EnvFilter syntax) to additionally print tracing
/// output for debugging; `RUST_LOG`/env_logger only covers `log`-crate
/// records and never sees these events.
pub(crate) fn install_sharding_event_bridge(reporter: Arc<Reporter>) {
    static INSTALLED: OnceLock<()> = OnceLock::new();
    INSTALLED.get_or_init(|| {
        let bridge = ShardingEventBridge { reporter }
            .with_filter(filter_fn(|meta| meta.target().contains("sharding")));
        let fmt = std::env::var("K2_LOG").ok().map(|spec| {
            tracing_subscriber::fmt::layer().with_filter(EnvFilter::new(spec))
        });
        let subscriber = tracing_subscriber::registry().with(bridge).with(fmt);
        if tracing::subscriber::set_global_default(subscriber).is_err() {
            log::warn!(
                "tracing global subscriber already installed elsewhere; \
                 sharding_event metrics will NOT be recorded"
            );
        }
    });
}

struct ShardingEventBridge {
    reporter: Arc<Reporter>,
}

impl<S: tracing::Subscriber> Layer<S> for ShardingEventBridge {
    fn on_event(&self, event: &tracing::Event<'_>, _ctx: Context<'_, S>) {
        if let Some(metric) = event_to_metric(event) {
            self.reporter.add_custom(metric);
        }
    }
}

fn event_to_metric(event: &tracing::Event<'_>) -> Option<ReportMetric> {
    let mut fields = EventFields::default();
    event.record(&mut fields);
    let message = fields.message?;
    let kind = sharding_event_kind(&message)?;
    let mut metric = ReportMetric::new("sharding_event")
        .with_tag("event", kind)
        .with_field("message", message);
    if let Some(agent) = fields.agent {
        metric = metric.with_tag("agent_id", agent);
    }
    if let Some(level) = fields.level {
        metric = metric.with_field("level", level);
    }
    for (name, value) in fields.extra {
        metric = metric.with_field(name, value);
    }
    Some(metric)
}

/// Classify a controller event by its message. The strings track
/// `kitsune2_gossip/src/sharding/controller.rs` in the fork; anything
/// unrecognised but sharding-prefixed lands in `other` with the message
/// preserved, so a fork wording change degrades visibly instead of
/// dropping data.
fn sharding_event_kind(message: &str) -> Option<&'static str> {
    Some(match message {
        m if m.contains("announcing shrink intent") => "shrink_intent",
        m if m.contains("executed polite shrink") => "shrink_executed",
        m if m.contains("shrink intent cancelled at re-check") => "intent_cancelled",
        m if m.contains("peer loss detected") => "peer_loss_cancel",
        m if m.contains("growing target arc") => "grow",
        m if m.starts_with("sharding:") => "other",
        _ => return None,
    })
}

#[derive(Default)]
struct EventFields {
    message: Option<String>,
    agent: Option<String>,
    level: Option<i64>,
    extra: Vec<(String, String)>,
}

impl Visit for EventFields {
    fn record_debug(&mut self, field: &Field, value: &dyn std::fmt::Debug) {
        let value = format!("{value:?}");
        match field.name() {
            "message" => self.message = Some(value),
            "agent" => self.agent = Some(value),
            _ => self.extra.push((field.name().to_string(), value)),
        }
    }

    fn record_i64(&mut self, field: &Field, value: i64) {
        if field.name() == "level" {
            self.level = Some(value);
        } else {
            self.record_debug(field, &value);
        }
    }

    fn record_u64(&mut self, field: &Field, value: u64) {
        if field.name() == "level" {
            self.level = Some(value as i64);
        } else {
            self.record_debug(field, &value);
        }
    }

    fn record_str(&mut self, field: &Field, value: &str) {
        match field.name() {
            "message" => self.message = Some(value.to_string()),
            "agent" => self.agent = Some(value.to_string()),
            _ => self.extra.push((field.name().to_string(), value.to_string())),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn event_kind_mapping() {
        assert_eq!(
            sharding_event_kind("sharding: announcing shrink intent"),
            Some("shrink_intent")
        );
        assert_eq!(
            sharding_event_kind("sharding: executed polite shrink"),
            Some("shrink_executed")
        );
        assert_eq!(
            sharding_event_kind("sharding: shrink intent cancelled at re-check"),
            Some("intent_cancelled")
        );
        assert_eq!(
            sharding_event_kind(
                "sharding: peer loss detected, cancelling pending shrink intent"
            ),
            Some("peer_loss_cancel")
        );
        assert_eq!(
            sharding_event_kind("sharding: growing target arc"),
            Some("grow")
        );
        // Unrecognised sharding messages must degrade visibly, not vanish.
        assert_eq!(
            sharding_event_kind("sharding: some future event"),
            Some("other")
        );
        assert_eq!(sharding_event_kind("unrelated log line"), None);
    }

    /// End-to-end through the tracing machinery: a controller-shaped event
    /// recorded under a real subscriber must come out as a sharding_event
    /// metric with the agent tag and level field intact. Uses a thread-local
    /// subscriber (`with_default`) so it cannot race the global bridge.
    #[test]
    fn bridge_converts_controller_event_to_metric() {
        #[derive(Clone, Default)]
        struct Capture(Arc<std::sync::Mutex<Vec<ReportMetric>>>);
        impl<S: tracing::Subscriber> Layer<S> for Capture {
            fn on_event(&self, event: &tracing::Event<'_>, _ctx: Context<'_, S>) {
                if let Some(metric) = event_to_metric(event) {
                    self.0.lock().unwrap().push(metric);
                }
            }
        }

        let capture = Capture::default();
        let subscriber = tracing_subscriber::registry().with(capture.clone());
        tracing::subscriber::with_default(subscriber, || {
            tracing::debug!(
                agent = ?"fake-agent-id",
                level = 3u64,
                "sharding: growing target arc"
            );
            tracing::debug!("unrelated event, must not be captured");
        });

        let metrics = capture.0.lock().unwrap();
        assert_eq!(metrics.len(), 1);
        let dump = format!(
            "name={:?} tags={:?} fields={:?}",
            metrics[0].name, metrics[0].tags, metrics[0].fields
        );
        assert!(dump.contains("sharding_event"), "{dump}");
        assert!(dump.contains("grow"), "{dump}");
        assert!(dump.contains("fake-agent-id"), "{dump}");
        assert!(dump.contains("3"), "{dump}");
    }
}
