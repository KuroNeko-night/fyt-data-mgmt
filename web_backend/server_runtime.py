"""Web HTTP 服务生命周期与周期维护调度。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


@dataclass(frozen=True)
class ServerRuntimeDependencies:
    """启动 Web 服务所需的配置、处理器和维护回调。"""

    host: str
    port: int
    handler_class: type[BaseHTTPRequestHandler]
    maintenance_interval: int
    output_retention_count: int
    trash_retention_days: int
    init_db: Callable[[], None]
    run_storage_maintenance: Callable[[], dict[str, int]]
    auto_backup_if_due: Callable[[], str]
    auto_weekly_report_if_due: Callable[[], str]
    auto_monthly_report_if_due: Callable[[], str]


class MaintenanceHTTPServer(ThreadingHTTPServer):
    """在标准 HTTP 请求循环中低频执行维护，不额外常驻清理线程。

    ``ThreadingHTTPServer`` 的 ``service_actions`` 钩子会在主监听循环中周期调用；维护
    动作因此与服务生命周期天然绑定，不会出现后台清理线程忘记停止的问题。实际请求仍
    由独立线程处理，维护异常只记录日志并等待下一周期，不关闭监听端口。
    """

    def __init__(
        self,
        *args: Any,
        maintenance_interval: int,
        maintenance_action: Callable[[], dict[str, int]],
        auto_backup_action: Callable[[], str],
        weekly_report_action: Callable[[], str],
        monthly_report_action: Callable[[], str],
        **kwargs: Any,
    ) -> None:
        """保存维护回调，并以单调时钟安排首次执行时间。

        回调通过依赖注入传入，使服务器生命周期模块不需要导入备份、报表或存储领域
        服务。这样既避免循环依赖，也允许测试使用无磁盘副作用的替身验证调度顺序。
        """
        super().__init__(*args, **kwargs)
        self.maintenance_interval = max(60, int(maintenance_interval))  # 防止错误配置导致每个请求循环都执行磁盘维护。
        self._maintenance_action = maintenance_action
        self._auto_backup_action = auto_backup_action
        self._weekly_report_action = weekly_report_action
        self._monthly_report_action = monthly_report_action
        self._next_maintenance_at = time.monotonic() + self.maintenance_interval  # 单调时钟不受系统校时或时区变化影响。

    def service_actions(self) -> None:
        """到达调度时间后依次执行存储维护、备份和周期报表。"""
        if time.monotonic() < self._next_maintenance_at:  # ThreadingHTTPServer 会周期调用此钩子，未到期时保持常数开销。
            return
        self._next_maintenance_at = time.monotonic() + self.maintenance_interval  # 先推进时间点，异常也不会造成紧密重试循环。
        try:
            report = self._maintenance_action()
        except Exception as exc:  # 维护失败不能终止主 HTTP 服务，等待下一周期再次尝试。
            print(f"[维护] 定期存储维护暂未完成：{exc}")
            return
        if any(report.values()):
            _print_storage_report("存储维护完成", report)
        # 备份与周期报表是非关键维护：任一失败只记日志，下一周期重试，不把健康检查拖成失败。
        _run_optional_action("自动备份", self._auto_backup_action)
        _run_optional_action("周报生成", self._weekly_report_action)
        _run_optional_action("月报生成", self._monthly_report_action)


def _print_storage_report(title: str, report: dict[str, int]) -> None:
    """按统一格式输出存储维护结果。"""
    print(
        f"[维护] {title}："
        f"归档旧输出 {report['moved_outputs']} 项，"
        f"清理回收站 {report['purged_trash']} 项，"
        f"清理未发布现场问题 {report['purged_workshop_drafts']} 项，"
        f"待重试 {report['trash_cleanup_failures']} 项"
    )


def _run_optional_action(label: str, action: Callable[[], str]) -> None:
    """执行一个非关键周期动作，失败只记录日志，不中断 HTTP 服务。

    回调返回空字符串表示本周期没有到期或没有产物，因此保持静默；返回文本时才写入
    服务日志。备份与周期报表都遵守这个约定，调度器无需了解各自的到期规则。
    """
    try:
        report = action()
    except Exception as exc:
        print(f"[维护] {label}暂未完成：{exc}")
        return
    if report:
        print(f"[维护] {report}")


def run_server(deps: ServerRuntimeDependencies) -> None:
    """初始化数据库与存储状态，然后持续运行 HTTP 服务。

    启动顺序是对外可用性的关键约束：先完成建表迁移，再清理过期数据，最后绑定监听
    端口。这样健康检查一旦可访问，其他请求就不会遇到缺表或半迁移结构。周期维护失败
    会在维护回调内部降级，但数据库初始化失败必须让进程退出，以免服务带病启动。
    """
    deps.init_db()  # 先完成幂等建表和迁移，任何请求线程都不会看到半初始化数据库。
    initial_report = deps.run_storage_maintenance()  # 启动即回收过期数据，避免必须等待首个维护周期。
    server = MaintenanceHTTPServer(
        (deps.host, deps.port),
        deps.handler_class,
        maintenance_interval=deps.maintenance_interval,
        maintenance_action=deps.run_storage_maintenance,
        auto_backup_action=deps.auto_backup_if_due,
        weekly_report_action=deps.auto_weekly_report_if_due,
        monthly_report_action=deps.auto_monthly_report_if_due,
    )
    print(f"[完成] 峰运通 Web 服务已启动: http://{deps.host}:{deps.port}")
    print("[提示] 管理员账号已就绪；密码不会写入页面或运行日志")
    print(
        f"[提示] 每个账号保留最近 {deps.output_retention_count} 次输出；"
        f"回收站数据保留 {deps.trash_retention_days} 天"
    )
    if any(initial_report.values()):
        _print_storage_report("启动维护完成", initial_report)
    try:
        server.serve_forever()  # 标准库内部以短轮询调用 service_actions，从而复用同一生命周期。
    except KeyboardInterrupt:
        print("\n[完成] 服务已停止")
    finally:
        server.server_close()  # 无论键盘中断还是异常退出，都立即释放监听端口。
