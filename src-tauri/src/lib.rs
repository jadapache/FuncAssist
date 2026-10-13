use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

struct BackendProcess(Arc<Mutex<Option<Child>>>);

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn is_backend_listening() -> bool {
    use std::net::TcpStream;
    use std::time::Duration;
    if let Ok(addr) = "127.0.0.1:6728".parse() {
        TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok()
    } else {
        false
    }
}

fn find_backend_dir() -> Option<PathBuf> {
    let mut candidates = Vec::new();

    // 1. Next to current executable (installed or portable layouts)
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join("resources").join("backend"));
            candidates.push(exe_dir.join("backend"));
            candidates.push(exe_dir.join("..").join("backend"));
            candidates.push(exe_dir.join("..").join("..").join("backend"));
        }
    }

    // 2. Relative to current working directory
    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("backend"));
        candidates.push(cwd.join("..").join("backend"));
    }

    // 3. Fallback known dev workspace path
    candidates.push(PathBuf::from("C:\\Dev\\QA_MGMT\\backend"));

    for candidate in candidates {
        if candidate.join("app").join("main.py").exists() {
            return Some(candidate);
        }
    }

    None
}

fn find_python_executable(backend_dir: Option<&Path>) -> PathBuf {
    // 1. Virtual environment in detected backend folder
    if let Some(dir) = backend_dir {
        #[cfg(target_os = "windows")]
        let venv_python = dir.join(".venv").join("Scripts").join("python.exe");
        #[cfg(not(target_os = "windows"))]
        let venv_python = dir.join(".venv").join("bin").join("python");

        if venv_python.exists() {
            return venv_python;
        }
    }

    // 2. Virtual environment in dev workspace
    #[cfg(target_os = "windows")]
    {
        let dev_venv = Path::new("C:\\Dev\\QA_MGMT\\backend\\.venv\\Scripts\\python.exe");
        if dev_venv.exists() {
            return dev_venv.to_path_buf();
        }
    }

    // 3. System python fallback
    #[cfg(target_os = "windows")]
    {
        PathBuf::from("python")
    }
    #[cfg(not(target_os = "windows"))]
    {
        PathBuf::from("python3")
    }
}

fn find_backend_executable() -> Option<PathBuf> {
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        let exe = PathBuf::from(local_app_data)
            .join("funcassist")
            .join("bin")
            .join("funcassist-backend.exe");
        if exe.is_file() && exe.metadata().map(|m| m.len()).unwrap_or(0) > 10000 {
            return Some(exe);
        }
    }

    None
}

fn spawn_backend() -> Option<Child> {
    if is_backend_listening() {
        println!("Backend is already running. Reusing existing instance.");
        return None;
    }

    let mut cmd = if let Some(backend_exe) = find_backend_executable() {
        println!("Starting standalone backend binary: {:?}", backend_exe);
        let mut c = Command::new(&backend_exe);
        if let Some(parent) = backend_exe.parent() {
            c.current_dir(parent);
        }
        c
    } else {
        let backend_dir = find_backend_dir();
        let python_exe = find_python_executable(backend_dir.as_deref());

        println!("Starting backend with Python: {:?}", python_exe);
        if let Some(ref dir) = backend_dir {
            println!("Backend working directory: {:?}", dir);
        }

        let mut c = Command::new(&python_exe);
        c.args(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "6728"]);

        if let Some(ref dir) = backend_dir {
            c.current_dir(dir);
        }
        c
    };

    // Force UTF-8 environment variables for sidecar child process
    cmd.env("PYTHONUTF8", "1");
    cmd.env("PYTHONIOENCODING", "utf-8");

    // Redirect output to log file in AppData/Local/funcassist/logs/backend.log
    if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
        let log_dir = PathBuf::from(local_app_data).join("funcassist").join("logs");
        let _ = std::fs::create_dir_all(&log_dir);
        let log_file_path = log_dir.join("backend.log");
        if let Ok(log_file) = std::fs::OpenOptions::new().create(true).append(true).open(log_file_path) {
            if let Ok(err_file) = log_file.try_clone() {
                cmd.stdout(Stdio::from(log_file));
                cmd.stderr(Stdio::from(err_file));
            }
        }
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

fn ensure_ffmpeg_in_appdata() {
    let local_app_data = match std::env::var("LOCALAPPDATA") {
        Ok(v) => v,
        Err(_) => return,
    };

    let app_dir = PathBuf::from(local_app_data).join("funcassist");
    let _ = std::fs::create_dir_all(&app_dir);

    let target_root = app_dir.join("ffmpeg.exe");

    // If already exists and is valid, nothing to do
    if target_root.exists() && target_root.metadata().map(|m| m.len()).unwrap_or(0) > 10000 {
        return;
    }

    let mut candidates = Vec::new();

    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            candidates.push(exe_dir.join("resources").join("bin").join("ffmpeg.exe"));
            candidates.push(exe_dir.join("resources").join("ffmpeg.exe"));
            candidates.push(exe_dir.join("bin").join("ffmpeg.exe"));
            candidates.push(exe_dir.join("ffmpeg.exe"));
            candidates.push(exe_dir.join("..").join("resources").join("bin").join("ffmpeg.exe"));
        }
    }

    if let Ok(cwd) = std::env::current_dir() {
        candidates.push(cwd.join("src-tauri").join("bin").join("ffmpeg.exe"));
        candidates.push(cwd.join("bin").join("ffmpeg.exe"));
        candidates.push(cwd.join("ffmpeg.exe"));
    }

    candidates.push(PathBuf::from("C:\\Dev\\QA_MGMT\\src-tauri\\bin\\ffmpeg.exe"));

    for candidate in candidates {
        if candidate.exists() && candidate.metadata().map(|m| m.len()).unwrap_or(0) > 10000 {
            println!("Copying FFmpeg from {:?} to AppData/Local/funcassist/ffmpeg.exe...", candidate);
            let _ = std::fs::copy(&candidate, &target_root);
            break;
        }
    }
}

pub fn run() {
    ensure_ffmpeg_in_appdata();
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
