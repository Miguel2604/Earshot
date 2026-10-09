use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};

/// The Python engine (../../engine) serving the local models on 127.0.0.1:8765.
struct Engine(Mutex<Option<Child>>);

// ponytail: dev/demo launch via `uv run` from the repo checkout; bundle engine as a Tauri sidecar binary for a real installer.
fn spawn_engine() -> Option<Child> {
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../engine");
    Command::new("uv")
        .args(["run", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8765"])
        .current_dir(dir)
        .spawn()
        .map_err(|e| eprintln!("engine failed to start (is uv installed?): {e}"))
        .ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(Engine(Mutex::new(spawn_engine())))
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(mut child) = app.state::<Engine>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
