# -*- coding: utf-8 -*-
"""
桌面端全局设置读写
==================
把输出位置、主题、动效、完成提示、增量缓存、导航状态和到料批次记忆统一保存到
``core.paths.config_path()``。默认桌面路径位于用户文档目录，Web 任务可通过
``FYT_CONFIG_PATH`` 指向隔离运行目录，业务模块不得自行读取其他散落配置文件。

加载时只接受 ``DEFAULTS`` 中已登记的字段，并逐项校验类型和取值范围；未知磁盘字段
暂时忽略，便于新版本配置由旧程序读取。配置不存在时可迁移早期到料工具配置；配置
存在但损坏时备份为 ``.bak`` 并回落默认值，不再用旧配置覆盖用户当前文件。保存采用
同目录临时文件、刷新缓冲并原子替换，进程中断不会留下半截 JSON。
"""
import os
import json
import shutil
import logging

from . import paths
from . import version

_log = logging.getLogger(__name__)

DEFAULTS = {
    # 这里既定义缺省值，也充当允许持久化的字段白名单；新增设置需同步 _valid_value。
    "output_mode": "unified",          # unified | beside | custom
    "custom_output_root": "",
    "theme_mode": "auto",              # auto(跟随系统) | light | dark
    "reduce_motion": False,             # 减少非必要位移、淡入与回弹动画
    "check_update_on_start": version.CHECK_UPDATE_ON_START,
    "auto_open_output": True,          # 处理完成后自动打开输出文件夹
    "show_done_dialog": True,          # 处理完成后弹出结果提示框
    "minimize_to_tray": True,          # 点关闭时最小化到系统托盘而非退出
    "enable_incremental_cache": True,  # 输入和参数未变化时复用既有输出
    "onboarding_seen": False,
    # 到料明细批次记忆（迁移自旧 ~/.arrival_table_config.json）
    "arrival": {"top_label": "截止16点的数据", "last_total": 566, "batches": {}},
    "nav_collapsed": False,
    "preview_hidden": True,
    "right_panel_w": 420,
}


_BOOLEAN_KEYS = {
    "reduce_motion", "check_update_on_start", "auto_open_output",
    "show_done_dialog", "minimize_to_tray", "enable_incremental_cache",
    "onboarding_seen", "nav_collapsed", "preview_hidden",
}


def _validate_arrival(value):
    """清洗到料嵌套设置；单个损坏批次只丢弃该项。"""
    if not isinstance(value, dict):
        raise ValueError("到料明细设置必须是对象")
    top_label = value.get("top_label", DEFAULTS["arrival"]["top_label"])  # 缺失字段沿用稳定默认值。
    last_total = value.get("last_total", DEFAULTS["arrival"]["last_total"])  # 保留旧版人工总数记忆。
    batches = value.get("batches", {})  # 历史批次是可选映射，缺失时按空表处理。
    if not isinstance(top_label, str) or isinstance(last_total, bool) or not isinstance(last_total, (int, float)):
        raise ValueError("到料明细设置字段无效")
    if not isinstance(batches, dict):
        raise ValueError("到料批次设置必须是对象")
    clean_batches = {}
    for batch, item in batches.items():  # 逐条隔离历史脏数据，避免一条坏记录拖垮整个设置。
        if not isinstance(item, dict):
            continue
        total = item.get("total", DEFAULTS["arrival"]["last_total"])  # 缺失总数沿用上一次有效值。
        remark = item.get("remark", "")  # 备注不是必填字段，统一回退为空文本。
        if isinstance(total, bool) or not isinstance(total, (int, float)) or not isinstance(remark, str):
            continue
        clean_batches[str(batch)] = {"total": int(total), "remark": remark}  # 固化前端稳定协议类型。
    return {"top_label": top_label, "last_total": int(last_total), "batches": clean_batches}


def _valid_value(key, value):
    """校验并规范化单个设置值，失败时抛出可记录的 ``ValueError``。

    JSON 语法正确不代表字段类型可靠，例如布尔值在 Python 中也是整数子类，因此数值
    设置必须显式排除 bool。函数对无需转换的字段返回原值，对宽度和到料嵌套设置返回
    清洗后的副本，防止脏数据进入进程内状态。
    """
    if key == "output_mode":
        if value not in ("unified", "beside", "custom"):  # 输出目录策略必须来自固定枚举。
            raise ValueError("输出模式无效")
        return value
    if key == "theme_mode":
        if value not in ("auto", "light", "dark"):  # 主题枚举与双端设计令牌保持一致。
            raise ValueError("主题模式无效")
        return value
    if key == "custom_output_root":
        if not isinstance(value, str):  # 路径允许为空，但不能接受数组、数字等 JSON 类型。
            raise ValueError("路径设置必须是文本")
        return value
    if key in _BOOLEAN_KEYS:
        if not isinstance(value, bool):  # Python 中 bool 是 int 子类，必须显式按布尔校验。
            raise ValueError("布尔设置类型无效")
        return value
    if key == "right_panel_w":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 240 <= value <= 1200:
            raise ValueError("侧栏宽度无效")
        return int(value)  # 页面布局按整数像素保存，避免浮点配置造成渲染抖动。
    if key == "arrival":
        return _validate_arrival(value)  # 嵌套配置交给独立校验器，主函数保持扁平。
    raise ValueError("未知设置")


class Settings(object):
    """管理一份进程内设置副本，并提供显式加载、校验和原子保存。"""

    def __init__(self):
        """深复制默认设置后立即尝试从磁盘加载覆盖值。"""
        # DEFAULTS 含嵌套字典，不能使用浅拷贝；JSON 往返可得到纯数据深副本。
        self._data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        """从统一配置路径加载已知字段，损坏时备份并保留默认设置。

        文件不存在与文件损坏必须区分：前者代表首次运行，可尝试迁移旧配置；后者代表
        用户当前配置出了问题，只能备份并警告，不能再用可能更旧的数据静默覆盖。
        """
        p = paths.config_path()
        if not os.path.exists(p):
            self._migrate_legacy()
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                disk = json.load(f)
            if not isinstance(disk, dict):
                raise ValueError("配置根节点必须是对象")
            for key in DEFAULTS:
                if key in disk:
                    # 逐字段校验后覆盖；磁盘中的未知新字段不会进入旧版本运行状态。
                    self._data[key] = _valid_value(key, disk[key])
        except Exception as e:
            # copy2 尽量保留损坏文件时间等元数据，便于后续人工定位问题。
            try:
                shutil.copy2(p, p + ".bak")
            except Exception:
                pass
            _log.warning("配置文件损坏，已备份为 %s.bak 并回落默认设置：%s", p, e)

    def _merge(self, base, over):
        """递归把嵌套字典 ``over`` 合并到 ``base``；非字典值直接覆盖。

        该兼容辅助方法不负责字段校验，只有已受信任的内部数据才应调用；当前正式加载
        路径采用逐字段 ``_valid_value``，避免旧式宽松合并引入未知配置。
        """
        for k, v in over.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._merge(base[k], v)
            else:
                base[k] = v

    def _migrate_legacy(self):
        """首次运行时读取旧到料工具配置到内存，不主动删除旧文件。

        迁移是尽力而为的兼容路径：文件不存在、格式损坏或字段缺失均静默使用默认值，
        因为首次启动不应被一个非必需的历史配置阻断。正式保存仍由调用方执行。
        """
        legacy = os.path.join(os.path.expanduser("~"), ".arrival_table_config.json")
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                old = json.load(f)
            self._data["arrival"]["top_label"] = old.get("top_label", "截止16点的数据")
            self._data["arrival"]["last_total"] = old.get("last_total", 566)
            self._data["arrival"]["batches"] = old.get("batches", {})
        except Exception:
            # 旧配置不再是现行事实来源，迁移失败没有必要升级为用户可见错误。
            pass

    def save(self):
        """把当前设置原子写入统一配置文件，成功返回 ``True``。

        临时文件与正式文件位于同一目录，刷新 Python 缓冲后尽力 ``fsync`` 到磁盘，再
        用 ``os.replace`` 原子替换。失败时清理临时文件并记录日志，保留原配置不变。
        """
        p = paths.config_path()
        tmp = p + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    # 部分文件系统不支持 fsync；原子替换仍可执行，因此只忽略 OSError。
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, p)
            return True
        except Exception as e:
            _log.warning("保存配置失败：%s", e)
            try:
                if os.path.exists(tmp):
                    # 清理只针对本函数固定的同目录临时文件，不触碰正式配置。
                    os.remove(tmp)
            except OSError:
                pass
            return False

    # ---- 便捷访问 ----
    def get(self, key, default=None):
        """读取设置值；未知键返回调用方提供的默认值。"""
        return self._data.get(key, default)

    def set(self, key, value):
        """校验并更新一个已登记设置；调用方仍需显式 ``save`` 落盘。"""
        if key not in DEFAULTS:
            raise KeyError("未知设置：%s" % key)
        self._data[key] = _valid_value(key, value)

    @property
    def output_mode(self):
        """返回输出模式，缺失时兼容回落到统一目录。"""
        return self._data.get("output_mode", "unified")

    @property
    def custom_output_root(self):
        """返回自定义输出根文本，未设置时为空串。"""
        return self._data.get("custom_output_root", "")

    @property
    def theme_mode(self):
        """返回界面主题模式：跟随系统、亮色或暗色。"""
        return self._data.get("theme_mode", "auto")

    def output_kwargs(self):
        """生成可直接传给 ``paths.resolve_output_dir`` 的路径策略参数。"""
        return {"mode": self.output_mode,
                "custom_root": self.custom_output_root or None}

    @property
    def arrival(self):
        """返回可原地维护的到料设置字典，缺失时创建空字典。"""
        return self._data.setdefault("arrival", {})


# 设置在进程内共享，避免每个业务模块反复读盘；测试可显式重置此变量。
_instance = None


def get_settings():
    """延迟创建并返回当前进程唯一的 ``Settings`` 实例。"""
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance
