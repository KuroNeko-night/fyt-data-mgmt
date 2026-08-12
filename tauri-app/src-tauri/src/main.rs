//! Tauri 桌面应用的原生进程入口。
//!
//! 实际命令、桥接进程和托盘生命周期集中在库模块中，入口只负责启动，
//! 便于库代码由 Rust 测试直接调用。

// 发布构建使用 Windows GUI 子系统，避免安装版启动时额外出现命令窗口；调试构建仍保留控制台。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

/// 启动桌面应用并把生命周期交给库模块统一管理。
fn main() {
    fyt_data_mgmt_tauri_lib::run();
}
