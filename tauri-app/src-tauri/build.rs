// Tauri 编译期入口：生成权限、资源和平台配置所需的 Cargo 构建指令。
fn main() {
    tauri_build::build() // 保持官方构建助手为唯一入口，避免手工配置与 tauri.conf.json 漂移。
}
