//! Local bootstrap server + embedded iroh relay for arc-sharding runs.
//!
//! The fork's `bootstrap_srv` embeds the iroh relay (protocol V2), so one
//! binary provides both services; scenario agents use the same
//! `http://host:port` URL for `--bootstrap-server-url` and `--relay-url`.
//! Building it inside this workspace keeps the whole experiment in one
//! `cargo build --workspace` instead of a separate fork-tree build.

use kitsune2_bootstrap_srv::{BootstrapSrv, Config};

fn main() {
    let listen = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "127.0.0.1:30744".to_string())
        .parse()
        .expect("argument must be a socket address, e.g. 127.0.0.1:30744");
    let mut config = Config::testing();
    config.listen_address_list = vec![listen];
    let srv = BootstrapSrv::new(config).expect("failed to start bootstrap server");
    for addr in srv.listen_addrs() {
        // The orchestration script waits for this line.
        println!("bootstrap+relay ready at http://{addr}");
    }
    loop {
        std::thread::sleep(std::time::Duration::from_secs(3600));
    }
}
