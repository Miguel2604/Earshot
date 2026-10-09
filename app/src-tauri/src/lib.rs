use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, PhysicalPosition, RunEvent};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

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
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(Engine(Mutex::new(spawn_engine())))
        .setup(|app| {
            // Overlay: dock top-right of the work area (24px margins), then show.
            let win = app.get_webview_window("main").unwrap();
            if let Some(m) = win.current_monitor()? {
                let (area, gap) = (m.work_area(), (24.0 * m.scale_factor()) as i32);
                let w = win.outer_size()?.width as i32;
                win.set_position(PhysicalPosition::new(area.position.x + area.size.width as i32 - w - gap, area.position.y + gap))?;
            }
            win.show()?;
            // Cmd+\ toggles the overlay.
            app.global_shortcut().on_shortcut(Shortcut::new(Some(Modifiers::SUPER), Code::Backslash), move |_, _, e| {
                if e.state == ShortcutState::Pressed {
                    let _ = if win.is_visible().unwrap_or(false) { win.hide() } else { win.show().and_then(|_| win.set_focus()) };
                }
            })?;
            Ok(())
        })
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
