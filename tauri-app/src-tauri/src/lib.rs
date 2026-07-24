use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Mutex, OnceLock};
use std::thread;
use tauri::{Emitter, Manager};

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct BridgeRequest {
    action: String,
    #[serde(default)]
    payload: Value,
    #[serde(default)]
    request_id: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct BridgeEnvelope {
    ok: bool,
    #[serde(default)]
    data: Value,
    #[serde(default)]
    error: String,
}

static ACTIVE_PROCESSES: OnceLock<Mutex<HashMap<String, u32>>> = OnceLock::new();
static MINIMIZE_TO_TRAY: AtomicBool = AtomicBool::new(true);

fn active_processes() -> &'static Mutex<HashMap<String, u32>> {
    ACTIVE_PROCESSES.get_or_init(|| Mutex::new(HashMap::new()))
}

fn project_root() -> PathBuf {
    if let Ok(value) = std::env::var("FYT_PROJECT_ROOT") {
        return PathBuf::from(value);
    }
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")))
        .to_path_buf()
}

fn python_executable(root: &Path) -> Result<PathBuf, String> {
    if let Ok(value) = std::env::var("FYT_PYTHON_EXECUTABLE") {
        let path = PathBuf::from(value);
        if path.is_file() {
            return Ok(path);
        }
    }
    let sidecar = std::env::current_exe()
        .map_err(|error| format!("无法定位当前程序：{error}"))?
        .with_file_name("FYTCoreBridge.exe");
    if sidecar.is_file() {
        return Ok(sidecar);
    }
    let development = root.join(".venv").join("Scripts").join("python.exe");
    if cfg!(debug_assertions) && development.is_file() {
        return Ok(development);
    }
    Err("未找到 Python 核心运行时；开发环境请先运行 setup-modern.ps1".into())
}

fn make_command(executable: &Path, root: &Path) -> Command {
    let mut command = Command::new(executable);
    command.env("PYTHONIOENCODING", "utf-8");
    command.env("PYTHONUTF8", "1");
    if executable
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case("python.exe"))
    {
        command.args(["-m", "core.tauri_bridge"]);
        command.current_dir(root);
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    command
}

fn bridge_request_sync_with_events(
    request: BridgeRequest,
    event_sender: Option<mpsc::Sender<Value>>,
) -> Result<Value, String> {
    let root = project_root();
    let executable = python_executable(&root)?;
    let request_id = request.request_id.clone();
    let body = serde_json::to_vec(&request)
        .map_err(|error| format!("桥接请求序列化失败：{error}"))?;
    let mut command = make_command(&executable, &root);
    command.env("FYT_BRIDGE_EVENTS", "1");
    command.env("FYT_REQUEST_ID", &request_id);
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("无法启动 Python 核心：{error}"))?;
    let child_id = child.id();
    if !request_id.is_empty() {
        active_processes()
            .lock()
            .map_err(|_| "任务进程表已损坏".to_string())?
            .insert(request_id.clone(), child_id);
    }
    let stderr = child.stderr.take();
    let stderr_thread = thread::spawn(move || {
        let mut plain = Vec::new();
        if let Some(stream) = stderr {
            for line in BufReader::new(stream).lines().map_while(Result::ok) {
                if let Some(raw) = line.strip_prefix("__FYT_EVENT__") {
                    if let (Some(sender), Ok(event)) =
                        (event_sender.as_ref(), serde_json::from_str::<Value>(raw))
                    {
                        let _ = sender.send(event);
                    }
                } else {
                    plain.push(line);
                }
            }
        }
        plain.join("\n")
    });
    child
        .stdin
        .take()
        .ok_or_else(|| "无法写入 Python 核心请求".to_string())?
        .write_all(&body)
        .map_err(|error| format!("写入 Python 核心请求失败：{error}"))?;
    let output = child
        .wait_with_output()
        .map_err(|error| format!("等待 Python 核心失败：{error}"))?;
    if !request_id.is_empty() {
        if let Ok(mut processes) = active_processes().lock() {
            processes.remove(&request_id);
        }
    }
    let stderr = stderr_thread.join().unwrap_or_else(|_| "读取 Python 错误输出失败".into());
    let envelope: BridgeEnvelope = serde_json::from_slice(&output.stdout).map_err(|error| {
        format!("Python 核心返回无效 JSON：{error}；{stderr}")
    })?;
    if envelope.ok {
        Ok(envelope.data)
    } else {
        Err(if envelope.error.is_empty() {
            stderr.trim().to_string()
        } else {
            envelope.error
        })
    }
}

fn bridge_request_sync(request: BridgeRequest) -> Result<Value, String> {
    bridge_request_sync_with_events(request, None)
}

#[tauri::command]
async fn bridge_request(app: tauri::AppHandle, request: BridgeRequest) -> Result<Value, String> {
    let (event_sender, event_receiver) = mpsc::channel();
    let event_thread = thread::spawn(move || {
        for event in event_receiver {
            let _ = app.emit("bridge-task-event", event);
        }
    });
    let result = tauri::async_runtime::spawn_blocking(move || {
        bridge_request_sync_with_events(request, Some(event_sender))
    })
    .await
    .map_err(|error| format!("Python 核心任务调度失败：{error}"))?;
    let _ = event_thread.join();
    result
}

#[tauri::command]
async fn cancel_bridge_request(request_id: String) -> Result<bool, String> {
    tauri::async_runtime::spawn_blocking(move || cancel_bridge_request_sync(&request_id))
        .await
        .map_err(|error| format!("取消任务调度失败：{error}"))?
}

fn cancel_bridge_request_sync(request_id: &str) -> Result<bool, String> {
    let process_id = active_processes()
        .lock()
        .map_err(|_| "任务进程表已损坏".to_string())?
        .get(request_id)
        .copied();
    let Some(process_id) = process_id else { return Ok(false) };
    #[cfg(target_os = "windows")]
    let status = {
        use std::os::windows::process::CommandExt;
        Command::new("taskkill")
            .args(["/PID", &process_id.to_string(), "/T", "/F"])
            .creation_flags(0x08000000)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|error| format!("取消任务失败：{error}"))?
    };
    #[cfg(not(target_os = "windows"))]
    let status = Command::new("kill")
        .arg(process_id.to_string())
        .status()
        .map_err(|error| format!("取消任务失败：{error}"))?;
    let _ = bridge_request_sync(BridgeRequest {
        action: "tasks.cancel".into(),
        payload: serde_json::json!({"request_id": request_id}),
        request_id: String::new(),
    });
    Ok(status.success())
}

#[tauri::command]
async fn install_update(app: tauri::AppHandle, path: String) -> Result<Value, String> {
    let request = BridgeRequest {
        action: "updater.install".into(),
        payload: serde_json::json!({"path": path}),
        request_id: String::new(),
    };
    let result = tauri::async_runtime::spawn_blocking(move || bridge_request_sync(request))
        .await
        .map_err(|error| format!("更新安装任务调度失败：{error}"))??;
    app.exit(0);
    Ok(result)
}

#[tauri::command]
fn set_minimize_to_tray(enabled: bool) {
    MINIMIZE_TO_TRAY.store(enabled, Ordering::Relaxed);
}

fn validate_open_path(path: &str) -> Result<PathBuf, String> {
    let target = PathBuf::from(path.trim());
    if !target.is_absolute() {
        return Err("只允许打开绝对路径。".into());
    }
    if !target.exists() {
        return Err(format!("目标路径不存在：{}", target.display()));
    }
    Ok(target)
}

#[tauri::command]
fn open_local_path(path: String) -> Result<(), String> {
    open_local_path_sync(&path)
}

fn open_local_path_sync(path: &str) -> Result<(), String> {
    let target = validate_open_path(&path)?;
    tauri_plugin_opener::open_path(target, None::<&str>)
        .map_err(|error| format!("无法打开本地路径：{error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            use tauri::menu::{Menu, MenuItem};
            use tauri::tray::TrayIconBuilder;

            let show_item = MenuItem::with_id(
                app, "show", "显示主窗口", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(
                app, "quit", "退出程序", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &quit_item])?;
            let mut tray = TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(false)
                .tooltip("峰运通数据管理系统")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone());
            }
            tray.build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if MINIMIZE_TO_TRAY.load(Ordering::Relaxed) {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            bridge_request,
            cancel_bridge_request,
            install_update,
            set_minimize_to_tray,
            open_local_path
        ])
        .run(tauri::generate_context!())
        .expect("启动峰运通 Tauri 前端失败");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn 健康检查保持中文_utf8() {
        let data = bridge_request_sync(BridgeRequest {
            action: "system.health".into(),
            payload: Value::Object(Default::default()),
            request_id: String::new(),
        })
        .expect("健康检查应成功");
        assert_eq!(data["app_name"], "峰运通数据管理系统");
    }

    #[test]
    fn 金额转换可经桥接调用() {
        let data = bridge_request_sync(BridgeRequest {
            action: "currency.convert".into(),
            payload: serde_json::json!({"amount": "12345.67"}),
            request_id: String::new(),
        })
        .expect("金额转换应成功");
        assert_eq!(data["text"], "壹万贰仟叁佰肆拾伍元陆角柒分");
    }

    #[test]
    fn 前端未暴露直接路径打开权限() {
        let capability: Value = serde_json::from_str(include_str!("../capabilities/default.json"))
            .expect("桌面权限配置应为有效 JSON");
        let permissions = capability["permissions"]
            .as_array()
            .expect("桌面权限配置应包含权限数组");
        assert!(!permissions.iter().any(|item| item == "opener:allow-open-path"));
    }

    #[test]
    fn 本地路径打开只接受存在的绝对路径() {
        let target = std::env::temp_dir().join(format!("fyt_open_path_{}", std::process::id()));
        fs::create_dir_all(&target).expect("应创建路径打开测试目录");
        assert_eq!(
            validate_open_path(target.to_str().expect("临时路径应为 UTF-8"))
                .expect("存在的绝对路径应通过校验"),
            target
        );
        assert!(validate_open_path("相对路径").is_err());
        fs::remove_dir_all(&target).expect("应清理路径打开测试目录");
    }

    #[test]
    #[ignore = "仅供本机显式验证系统路径打开"]
    fn 本地路径原生打开冒烟() {
        let target = std::env::var("FYT_OPEN_PATH_SMOKE").expect("应指定冒烟目录");
        open_local_path_sync(&target).expect("系统应成功打开指定目录");
    }

    #[test]
    fn 长任务事件可穿过_rust_桥接() {
        let temp_dir = std::env::temp_dir().join(format!(
            "fyt_rust_event_{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&temp_dir);
        fs::create_dir_all(&temp_dir).expect("应创建临时目录");
        let source = temp_dir.join("原文件.txt");
        fs::write(&source, "测试").expect("应创建测试文件");
        let task_db = temp_dir.join("tasks.db");
        let old_task_path = std::env::var_os("FYT_TASK_HISTORY_PATH");
        std::env::set_var("FYT_TASK_HISTORY_PATH", &task_db);
        let (sender, receiver) = mpsc::channel();
        let result = bridge_request_sync_with_events(
            BridgeRequest {
                action: "rename.apply".into(),
                payload: serde_json::json!({
                    "paths": [source],
                    "rule": {"prefix": "新_"}
                }),
                request_id: "rust-event".into(),
            },
            Some(sender),
        )
        .expect("重命名长任务应成功");
        if let Some(value) = old_task_path {
            std::env::set_var("FYT_TASK_HISTORY_PATH", value);
        } else {
            std::env::remove_var("FYT_TASK_HISTORY_PATH");
        }
        let events: Vec<Value> = receiver.try_iter().collect();
        assert_eq!(result["result"]["count"], 1);
        assert!(events.iter().any(|event| event["kind"] == "progress"));
        assert!(events.iter().all(|event| event["request_id"] == "rust-event"));
        fs::remove_dir_all(&temp_dir).expect("应清理临时目录");
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn 取消仅终止登记的子进程() {
        use std::os::windows::process::CommandExt;
        let mut child = Command::new("cmd")
            .args(["/C", "ping", "-n", "30", "127.0.0.1"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(0x08000000)
            .spawn()
            .expect("应启动测试子进程");
        active_processes()
            .lock()
            .expect("进程表应可用")
            .insert("cancel-test".into(), child.id());
        assert!(cancel_bridge_request_sync("cancel-test").expect("取消应成功"));
        let status = child.wait().expect("应回收测试子进程");
        assert!(!status.success());
    }
}
