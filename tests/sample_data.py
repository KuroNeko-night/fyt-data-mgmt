# -*- coding: utf-8 -*-
"""样本数据定位助手。

样本数据不在本项目内，而在仓库根「程序重构」下的各功能子目录：
    程序重构/
      峰运通数据管理系统/tests/  <- 本文件
      考勤对账程序/考勤填报测试数据/
      考勤对账程序/工时对账测试数据/
      采购数对账/测试数据/
      送货计划制作/输入/
      表格制作工具/每日到料表样本/
      表格制作工具/透视表样本/46A/
      发票筛选/输入/6月资料统计/

每个 getter 找不到文件时返回 None / []，集成测试据此 skip，
保证在没有样本的环境（如 CI）里测试不误报失败。
"""
import os
import glob

# tests/ -> 峰运通数据管理系统/ -> 程序重构/
_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(_PROJ)


def repo(*parts):
    """拼接仓库根下的路径。"""
    return os.path.join(REPO_ROOT, *parts)


def _first(pattern):
    hits = sorted(glob.glob(pattern))
    return hits[0] if hits else None


def _find(pattern, contains=None, exclude=None):
    """glob 匹配并按文件名子串过滤，返回排序后的绝对路径列表（排除临时 ~$ 文件）。"""
    out = []
    for p in sorted(glob.glob(pattern)):
        base = os.path.basename(p)
        if base.startswith("~$"):
            continue
        if contains and contains not in base:
            continue
        if exclude and exclude in base:
            continue
        out.append(p)
    return out


# ---------------- 考勤填报 ----------------
def attendance_target():
    return _first(repo("考勤对账程序", "考勤填报测试数据", "*KD仓考勤*.xlsx"))


def attendance_source():
    return _first(repo("考勤对账程序", "考勤填报测试数据", "每日统计表*.xlsx"))


# ---------------- 工时对账 ----------------
def reconcile_target():
    return _first(repo("考勤对账程序", "工时对账测试数据", "待对表", "*考勤表*.xlsx"))


def reconcile_sources():
    return _find(repo("考勤对账程序", "工时对账测试数据", "待对表数据来源", "*.xlsx"))


def reconcile_labor():
    xlsx = _find(repo("考勤对账程序", "工时对账测试数据", "待对数据", "*.xlsx"))
    xls = _find(repo("考勤对账程序", "工时对账测试数据", "待对数据", "*.xls"))
    return xlsx + xls


# ---------------- 采购数对账 ----------------
def purchase_ours():
    return _first(repo("采购数对账", "测试数据", "*对账单*.xlsx"))


def purchase_supplier():
    return _first(repo("采购数对账", "测试数据", "*对单明细*.xlsx"))


# ---------------- 送货计划 ----------------
def delivery_bom():
    """物料清单：含 VX11-SUB 的那份（带数量、无供应商列）。"""
    return _first(repo("送货计划制作", "输入", "VX11-SUB*.xlsx"))


def delivery_supplier():
    """供应商明细：含 A5+Sub-KD 物料清单（带供应商列）。"""
    return _first(repo("送货计划制作", "输入", "*A5+Sub-KD*.xlsx"))


# ---------------- 到料明细 ----------------
def arrival_plans():
    return _find(repo("表格制作工具", "每日到料表样本", "*送货计划*.xlsx"))


# ---------------- 透视表 ----------------
def pivot_sources():
    """46A 样本的源表（排除“正确透视表”这张答案表）。"""
    return _find(repo("表格制作工具", "透视表样本", "46A", "*.xlsx"),
                 exclude="正确透视")


# ---------------- 发票 ----------------
def invoice_folder():
    d = repo("发票筛选", "输入", "6月资料统计")
    return d if os.path.isdir(d) else None


# ---------------- 补充测试样本(SAP 多子表 KD 清单 / PFEP 核算表) ----------------
def _supp_dir():
    return repo("补充测试样本")


def supp_kd_bom():
    """SAP KD 清单(多子表,含 BOM 子表;deliv_bom)。"""
    return _first(os.path.join(_supp_dir(), "V11-KD*.XLSX")) \
        or _first(os.path.join(_supp_dir(), "V11-KD*.xlsx"))


def supp_kd_supplier():
    """SAP 供应商表(下阶物料+供应商代码/名称;deliv_supp)。"""
    return _first(os.path.join(_supp_dir(), "VX11-KD*.xlsx"))


def supp_pfep_sources():
    """PFEP 采购量核算表(pivot_src),3 份。"""
    return _find(os.path.join(_supp_dir(), "*PFEP*.xlsx"))
