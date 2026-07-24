# -*- coding: utf-8 -*-
"""
全局设置 —— 合并原两程序各自散落的配置
========================================
原状况：只有表格工具持久化设置(~/.arrival_table_config.json)，考勤程序不记忆任何东西。
现统一到一个配置文件：<文档>/峰运通数据管理系统/配置.json，含：
  · 输出模式(unified/beside/custom) 与自定义根目录；
  · 到料明细的批次记忆(top_label/last_total/batches)——迁移自旧配置；
  · 启动检查更新开关；
  · 首次使用引导是否已看过。

兼容 Windows 10/11 + Python 3.13。
"""
import os
import json
import shutil
import logging

from . import paths
from . import version

_log = logging.getLogger(__name__)

DEFAULTS = {
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


def _valid_value(key, value):
    """校验持久化设置，避免合法 JSON 的错误类型破坏业务入口。"""
    if key == "output_mode":
        if value not in ("unified", "beside", "custom"):
            raise ValueError("输出模式无效")
    elif key == "theme_mode":
        if value not in ("auto", "light", "dark"):
            raise ValueError("主题模式无效")
    elif key in ("custom_output_root",):
        if not isinstance(value, str):
            raise ValueError("路径设置必须是文本")
    elif key in ("reduce_motion", "check_update_on_start", "auto_open_output",
                 "show_done_dialog", "minimize_to_tray", "enable_incremental_cache",
                 "onboarding_seen", "nav_collapsed", "preview_hidden"):
        if not isinstance(value, bool):
            raise ValueError("布尔设置类型无效")
    elif key == "right_panel_w":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 240 <= value <= 1200:
            raise ValueError("侧栏宽度无效")
        return int(value)
    elif key == "arrival":
        if not isinstance(value, dict):
            raise ValueError("到料明细设置必须是对象")
        top_label = value.get("top_label", DEFAULTS["arrival"]["top_label"])
        last_total = value.get("last_total", DEFAULTS["arrival"]["last_total"])
        batches = value.get("batches", {})
        if not isinstance(top_label, str) or isinstance(last_total, bool) or not isinstance(last_total, (int, float)):
            raise ValueError("到料明细设置字段无效")
        if not isinstance(batches, dict):
            raise ValueError("到料批次设置必须是对象")
        clean_batches = {}
        for batch, item in batches.items():
            if not isinstance(item, dict):
                continue
            total = item.get("total", DEFAULTS["arrival"]["last_total"])
            remark = item.get("remark", "")
            if isinstance(total, bool) or not isinstance(total, (int, float)) or not isinstance(remark, str):
                continue
            clean_batches[str(batch)] = {"total": int(total), "remark": remark}
        return {"top_label": top_label, "last_total": int(last_total), "batches": clean_batches}
    else:
        raise ValueError("未知设置")
    return value


class Settings(object):
    """全局设置读写。改动后调用 save() 落盘。"""

    def __init__(self):
        self._data = json.loads(json.dumps(DEFAULTS))  # 深拷贝默认值
        self.load()

    def load(self):
        p = paths.config_path()
        # 区分"文件不存在"与"存在但损坏"：只有前者才迁移旧配置；
        # 后者若也迁移，会用陈旧旧配置覆盖并悄悄丢弃用户当前设置。
        if not os.path.exists(p):
            self._migrate_legacy()   # 首次运行：尝试迁移旧配置
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                disk = json.load(f)
            if not isinstance(disk, dict):
                raise ValueError("配置根节点必须是对象")
            for key in DEFAULTS:
                if key in disk:
                    self._data[key] = _valid_value(key, disk[key])
        except Exception as e:
            # 配置存在但解析失败(如被写坏)：备份损坏文件、告警、回落默认，
            # 不跑迁移(避免旧配置覆盖)，也不静默。
            try:
                shutil.copy2(p, p + ".bak")
            except Exception:
                pass
            _log.warning("配置文件损坏，已备份为 %s.bak 并回落默认设置：%s", p, e)

    def _merge(self, base, over):
        for k, v in over.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._merge(base[k], v)
            else:
                base[k] = v

    def _migrate_legacy(self):
        """迁移旧表格工具的 ~/.arrival_table_config.json（若存在）。"""
        legacy = os.path.join(os.path.expanduser("~"), ".arrival_table_config.json")
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                old = json.load(f)
            self._data["arrival"]["top_label"] = old.get("top_label", "截止16点的数据")
            self._data["arrival"]["last_total"] = old.get("last_total", 566)
            self._data["arrival"]["batches"] = old.get("batches", {})
        except Exception:
            pass

    def save(self):
        # 原子写：先落临时文件再 os.replace 到正式路径（同盘原子），
        # 写一半被杀不会留半截 JSON 覆盖掉好配置。失败时 log,不完全静默。
        p = paths.config_path()
        tmp = p + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, p)
            return True
        except Exception as e:
            _log.warning("保存配置失败：%s", e)
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return False

    # ---- 便捷访问 ----
    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        if key not in DEFAULTS:
            raise KeyError("未知设置：%s" % key)
        self._data[key] = _valid_value(key, value)

    @property
    def output_mode(self):
        return self._data.get("output_mode", "unified")

    @property
    def custom_output_root(self):
        return self._data.get("custom_output_root", "")

    @property
    def theme_mode(self):
        return self._data.get("theme_mode", "auto")

    def output_kwargs(self):
        """给 paths.resolve_output_dir 用的公共参数。"""
        return {"mode": self.output_mode,
                "custom_root": self.custom_output_root or None}

    @property
    def arrival(self):
        return self._data.setdefault("arrival", {})


# 进程内单例
_instance = None


def get_settings():
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance
