use std::process::{Child, Command};
use std::sync::{Arc, Mutex};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

struct BackendProcess(Arc<Mutex<Option<Child>>>);

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn spawn_backend() -> Option<Child> {
    let mut cmd = if std::path::Path::new("backend/.venv/Scripts/python.exe").exists() {
        Command::new("backend/.venv/Scripts/python.exe")
    } else if std::path::Path::new("../backend/.venv/Scripts/python.exe").exists() {
        Command::new("../backend/.venv/Scripts/python.exe")
    } else {
        Command::new("python")
    };

    cmd.args(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]);

    if std::path::Path::new("backend").exists() {
        cmd.current_dir("backend");
    } else if std::path::Path::new("../backend").exists() {
        cmd.current_dir("../backend");
    }

    #[cfg(target_os = "windows")]
    cmd.creation_flags(CREATE_NO_WINDOW);

    match cmd.spawn() {
        Ok(child) => {
            println!("Backend FastAPI spawned successfully (PID: {})", child.id());
            Some(child)
        }
        Err(err) => {
            eprintln!("Failed to spawn backend FastAPI: {}", err);
            None
        }
    }
}

pub fn run() {
    let backend_handle = Arc::new(Mutex::new(spawn_backend()));
    let backend_cleanup = Arc::clone(&backend_handle);

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(BackendProcess(backend_handle))
        .on_window_event(move |_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Ok(mut lock) = backend_cleanup.lock() {
                    if let Some(mut child) = lock.take() {
                        let _ = child.kill();
                        println!("Backend process terminated on window close.");
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
