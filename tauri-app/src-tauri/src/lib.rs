//! 峰运通 Tauri 原生命令层。
//!
//! 本模块只负责 WebView 与 Python Core 之间的进程桥接、任务事件转发、精确取消、更新
//! 安装、本地路径打开和系统托盘生命周期。业务动作白名单与算法仍位于 Python Core；
//! Rust 不解析 Excel，也不复制业务规则。Windows 下所有辅助进程都使用无窗口标志启动，
//! 避免正式安装包在桌面操作期间闪现命令窗口。

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
/// 前端传给 Python 桥接进程的标准请求。
struct BridgeRequest {
    /// Core 白名单中的动作键。
    action: String,
    #[serde(default)]
    /// 动作参数；保持通用 JSON，具体结构由 Python 动作校验。
    payload: Value,
    #[serde(default)]
    /// 长任务的唯一编号，用于事件过滤和精确取消；普通查询可为空。
    request_id: String,
}

#[derive(Debug, Deserialize, Serialize)]
/// Python 标准输出返回的统一成功或失败信封。
struct BridgeEnvelope {
    ok: bool,
    #[serde(default)]
    data: Value,
    #[serde(default)]
    error: String,
}

// 进程表只保存当前 Tauri 进程启动的子进程编号，取消命令不能作用于任意系统进程。
static ACTIVE_PROCESSES: OnceLock<Mutex<HashMap<String, u32>>> = OnceLock::new();
// 原子布尔由设置命令写入、窗口事件线程读取，无需为单个开关引入互斥锁。
static MINIMIZE_TO_TRAY: AtomicBool = AtomicBool::new(true);

/// 延迟创建全局任务进程表，避免初始化顺序依赖。
fn active_processes() -> &'static Mutex<HashMap<String, u32>> {
    ACTIVE_PROCESSES.get_or_init(|| Mutex::new(HashMap::new()))
}

/// 定位源码开发或显式部署配置下的项目根目录。
fn project_root() -> PathBuf {
    if let Ok(value) = std::env::var("FYT_PROJECT_ROOT") {
        return PathBuf::from(value); // 测试和特殊部署可覆盖编译期目录，不在此处要求目录已经存在。
    }
    // 开发结构为 tauri-app/src-tauri，向上两级回到项目根；异常布局回退到 Cargo 清单目录。
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")))
        .to_path_buf()
}

/// 按环境覆盖、正式 sidecar、开发虚拟环境的顺序定位 Python 核心运行时。
fn python_executable(root: &Path) -> Result<PathBuf, String> {
    if let Ok(value) = std::env::var("FYT_PYTHON_EXECUTABLE") {
        let path = PathBuf::from(value);
        if path.is_file() {
            return Ok(path);
        }
    }
    let sidecar = std::env::current_exe()
        .map_err(|error| format!("无法定位当前程序：{error}"))?
        .with_file_name("FYTCoreBridge.exe"); // 正式安装时 sidecar 与 Tauri 主程序位于同一目录。
    if sidecar.is_file() {
        return Ok(sidecar);
    }
    let development = root.join(".venv").join("Scripts").join("python.exe");
    if cfg!(debug_assertions) && development.is_file() { // 发布构建禁止静默依赖用户机器上的开发虚拟环境。
        return Ok(development);
    }
    Err("未找到 Python 核心运行时；开发环境请先运行 setup-modern.ps1".into())
}

/// 构造 UTF-8、无控制台窗口且兼容 sidecar 与开发 Python 的子进程命令。
fn make_command(executable: &Path, root: &Path) -> Command {
    let mut command = Command::new(executable);
    command.env("PYTHONIOENCODING", "utf-8");
    command.env("PYTHONUTF8", "1");
    if executable
        .file_name()
        .and_then(|name| name.to_str())
        .is_some_and(|name| name.eq_ignore_ascii_case("python.exe"))
    {
        // 只有直接启动 python.exe 时才补模块参数；冻结 sidecar 已把桥接入口编译进可执行文件。
        command.args(["-m", "core.tauri_bridge"]);
        command.current_dir(root);
    }
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW，安装版和开发版均不显示命令窗口。
    }
    command
}

///
/// 同步执行一次桥接请求，并可把 stderr 中的结构化事件转发给调用方。
///
/// 请求 JSON 写入子进程标准输入，最终信封从标准输出读取；stderr 由独立线程持续消费，
/// 防止大量日志填满管道导致子进程死锁。带事件前缀的行解析为进度或日志事件，其余行只在
/// 桥接失败时作为诊断补充。进程编号在启动后登记、等待完成后移除。
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
        // 只登记有前端请求编号的长任务，普通同步查询不会进入可取消进程表。
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
                    // 事件解析或接收端关闭时丢弃单条事件，不中断仍在运行的业务子进程。
                    if let (Some(sender), Ok(event)) =
                        (event_sender.as_ref(), serde_json::from_str::<Value>(raw))
                    {
                        let _ = sender.send(event);
                    }
                } else {
                    plain.push(line); // 普通 stderr 不实时展示，失败时再并入稳定错误文本。
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
    // wait_with_output 在 stdin 已关闭后等待退出并完整收集 stdout，避免读取半份 JSON 信封。
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

/// 不需要实时事件的同步桥接简化入口，供更新和测试复用。
fn bridge_request_sync(request: BridgeRequest) -> Result<Value, String> {
    bridge_request_sync_with_events(request, None)
}

#[tauri::command]
/// 在阻塞线程执行 Python 任务，并把结构化事件转发到前端全局事件总线。
async fn bridge_request(app: tauri::AppHandle, request: BridgeRequest) -> Result<Value, String> {
    let (event_sender, event_receiver) = mpsc::channel();
    let event_thread = thread::spawn(move || {
        for event in event_receiver {
            let _ = app.emit("bridge-task-event", event); // WebView 已关闭时忽略发送失败，让子进程正常回收。
        }
    });
    let result = tauri::async_runtime::spawn_blocking(move || {
        bridge_request_sync_with_events(request, Some(event_sender))
    })
    .await
    .map_err(|error| format!("Python 核心任务调度失败：{error}"))?;
    let _ = event_thread.join(); // sender 随桥接函数退出而释放，此处确保残余事件全部发送完毕。
    result
}

#[tauri::command]
/// 把可能阻塞的系统进程终止操作移出异步运行时工作线程。
async fn cancel_bridge_request(request_id: String) -> Result<bool, String> {
    tauri::async_runtime::spawn_blocking(move || cancel_bridge_request_sync(&request_id))
        .await
        .map_err(|error| format!("取消任务调度失败：{error}"))?
}

/// 仅终止进程表中与指定请求编号绑定的子进程，并同步通知 Python 任务历史。
fn cancel_bridge_request_sync(request_id: &str) -> Result<bool, String> {
    let process_id = active_processes()
        .lock()
        .map_err(|_| "任务进程表已损坏".to_string())?
        .get(request_id)
        .copied();
    let Some(process_id) = process_id else { return Ok(false) }; // 未登记或已完成任务按无需取消处理。
    #[cfg(target_os = "windows")]
    let status = {
        use std::os::windows::process::CommandExt;
        Command::new("taskkill")
            .args(["/PID", &process_id.to_string(), "/T", "/F"]) // 同时终止桥接进程派生的整个子进程树。
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
    let _ = bridge_request_sync(BridgeRequest { // 系统进程终止优先，任务历史通知失败不掩盖实际取消结果。
        action: "tasks.cancel".into(),
        payload: serde_json::json!({"request_id": request_id}),
        request_id: String::new(),
    });
    Ok(status.success())
}

#[tauri::command]
/// 通过 Python 更新器安装指定包，成功启动安装后退出当前桌面进程。
async fn install_update(app: tauri::AppHandle, path: String) -> Result<Value, String> {
    // 与 open_local_path 一致：Rust 边界先拒绝相对路径和不存在的安装包，避免把任意路径
    // 交给高权限安装命令；最终能否安装仍由 Python updater 二次校验。
    let _ = validate_open_path(&path)?;
    let request = BridgeRequest {
        action: "updater.install".into(),
        payload: serde_json::json!({"path": path}),
        request_id: String::new(),
    };
    let result = tauri::async_runtime::spawn_blocking(move || bridge_request_sync(request))
        .await
        .map_err(|error| format!("更新安装任务调度失败：{error}"))??;
    app.exit(0); // 释放正在使用的程序文件，使外部安装器可以安全覆盖当前版本。
    Ok(result)
}

#[tauri::command]
/// 更新关闭主窗口时是否最小化到托盘的进程内设置。
fn set_minimize_to_tray(enabled: bool) {
    MINIMIZE_TO_TRAY.store(enabled, Ordering::Relaxed);
}

/// 校验前端请求打开的是已存在绝对路径，拒绝相对路径受当前目录影响。
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
/// 通过受控 Tauri 命令打开本地文件或目录，不向前端授予通用 opener 权限。
fn open_local_path(path: String) -> Result<(), String> {
    open_local_path_sync(&path)
}

/// 执行经过绝对路径与存在性校验的系统原生打开操作。
fn open_local_path_sync(path: &str) -> Result<(), String> {
    let target = validate_open_path(&path)?;
    tauri_plugin_opener::open_path(target, None::<&str>)
        .map_err(|error| format!("无法打开本地路径：{error}"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
/// 构建插件、托盘菜单、关闭行为和前端可调用命令白名单，然后启动 Tauri。
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
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
                            // 显示、取消最小化并聚焦三步兼容窗口处于隐藏或最小化的不同状态。
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                });
            if let Some(icon) = app.default_window_icon() {
                tray = tray.icon(icon.clone()); // 复用应用图标，避免托盘另带一份平台资源。
            }
            tray.build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if MINIMIZE_TO_TRAY.load(Ordering::Relaxed) {
                    api.prevent_close(); // 用户选择托盘模式时关闭按钮只隐藏窗口，托盘退出才结束进程。
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

    /// 保护 Python 标准流到 Rust JSON 反序列化之间的 UTF-8 中文传递能力。
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

    /// 以金额转换覆盖一次完整的白名单请求、Python 执行和结果返回链路。
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

    /// 防止未来能力配置绕过自有路径校验，直接向 WebView 暴露任意路径打开权限。
    #[test]
    fn 前端未暴露直接路径打开权限() {
        let capability: Value = serde_json::from_str(include_str!("../capabilities/default.json"))
            .expect("桌面权限配置应为有效 JSON");
        let permissions = capability["permissions"]
            .as_array()
            .expect("桌面权限配置应包含权限数组");
        assert!(!permissions.iter().any(|item| item == "opener:allow-open-path"));
    }

    /// 验证路径打开命令只接受已经存在的绝对路径，拒绝依赖当前目录解析的相对路径。
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

    /// 仅在人工指定测试目录时调用操作系统打开能力，常规测试不弹出资源管理器。
    #[test]
    #[ignore = "仅供本机显式验证系统路径打开"]
    fn 本地路径原生打开冒烟() {
        let target = std::env::var("FYT_OPEN_PATH_SMOKE").expect("应指定冒烟目录");
        open_local_path_sync(&target).expect("系统应成功打开指定目录");
    }

    ///
    /// 使用临时任务数据库和真实重命名动作验证 stderr 事件能按请求编号穿过 Rust 桥接。
    /// 测试结束会恢复原环境变量并删除临时文件，避免污染用户任务历史。
    ///
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
        let old_task_path = std::env::var_os("FYT_TASK_HISTORY_PATH"); // 保存调用进程原值，测试后必须原样恢复。
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
        let events: Vec<Value> = receiver.try_iter().collect(); // 子进程已结束，此处可非阻塞收集全部已发送事件。
        assert_eq!(result["result"]["count"], 1);
        assert!(events.iter().any(|event| event["kind"] == "progress"));
        assert!(events.iter().all(|event| event["request_id"] == "rust-event"));
        fs::remove_dir_all(&temp_dir).expect("应清理临时目录");
    }

    #[cfg(target_os = "windows")]
    /// 登记一个无窗口测试子进程，验证取消只按请求编号终止对应 PID 并完成进程回收。
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
