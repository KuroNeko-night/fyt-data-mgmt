# -*- coding: utf-8 -*-
"""PyInstaller 桥接程序的最小入口。

所有动作白名单、参数校验、日志协议和业务调用都保留在 ``core.tauri_bridge``；此文件只提供
稳定的可执行入口，供桌面 sidecar 与 Windows Web 任务桥接两个 spec 复用。
"""

from core.tauri_bridge import main


if __name__ == "__main__":
    raise SystemExit(main())  # 保留桥接主函数退出码，供 Rust 或 Web 父进程判断任务结果。
