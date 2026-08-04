#![forbid(unsafe_code)]

use std::{env, path::PathBuf, process::ExitCode};

fn main() -> ExitCode {
    let database = database_path();
    if let Err(error) = ledgermind_daemon::run_stdio(&database) {
        eprintln!("ledgermind-core stopped: {error}");
        return ExitCode::FAILURE;
    }
    ExitCode::SUCCESS
}

fn database_path() -> PathBuf {
    let mut arguments = env::args_os().skip(1);
    while let Some(argument) = arguments.next() {
        if argument != "--database" {
            continue;
        }
        let Some(path) = arguments.next() else {
            continue;
        };
        return PathBuf::from(path);
    }
    env::var_os("LEDGERMIND_KNOWLEDGE_DB")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("knowledge.db"))
}
