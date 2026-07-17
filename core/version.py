# -*- coding: utf-8 -*-
"""
应用版本与更新配置（单一事实来源）
==================================
所有涉及版本号、应用标识、更新检查地址的地方都从这里取值，
打包脚本(Inno Setup)也会读取这里的版本号，保证一处修改处处一致。

兼容 Windows 7 + Python 3.8。
"""

# ---------------- 应用标识 ----------------
APP_NAME = "峰运通数据管理系统"
APP_NAME_EN = "FYT Data Management System"      # 英文名（安装目录、注册表键用，避免中文路径问题）
APP_ID = "FYTDataMgmt"                            # 内部短标识（注册表、互斥量、配置目录）
PUBLISHER = "KuroNeko-night"
COPYRIGHT = "Copyright (c) 2026 KuroNeko-night"

# ---------------- 版本号（语义化 主.次.修订）----------------
VERSION = "1.0.6"
VERSION_TUPLE = (1, 0, 6)
BUILD_DATE = "2026-07-17"

# ---------------- 更新检查 ----------------
# 更新模块优先读取 UPDATE_MANIFEST_URL；留空则由下面的 OWNER/REPO 自动拼 GitHub latest 地址。
GITHUB_OWNER = "KuroNeko-night"                  # GitHub 用户名
GITHUB_REPO = "fyt-data-mgmt"                    # 仓库名
# 若填了 OWNER/REPO，下面的 URL 会在 updater 中自动拼出；也可直接写死一个清单地址。
UPDATE_MANIFEST_URL = ""                          # 例如 "https://.../latest.json"，留空=不检查

# ---------------- 下载加速（应对国内直连 GitHub 慢/超时）----------------
# 给 GitHub 链接套一个镜像加速前缀，对"更新清单(latest.json)"和"安装包"下载同时生效。
# 留空 = 直连 GitHub。示例（任选一个可用的，注意都以 / 结尾）：
#   "https://ghproxy.com/"        "https://mirror.ghproxy.com/"
#   "https://gh.ddlc.top/"        "https://ghps.cc/"
# 用法：DOWNLOAD_ACCEL_PREFIX = "https://ghproxy.com/"
# 只对 https://github.com / https://raw.githubusercontent.com 链接生效，其他地址原样使用。
#
# ★ 重要区别（两个加速点，别混淆）：
#   1) 本前缀会编译进客户端 exe，同时加速【清单拉取】和【安装包下载】。
#      —— 想加速"清单拉取"(GitHub 被墙时连新版都发现不了)只能靠它，
#         且必须在【打包分发前】就填好；之后再改需要重新打包才能下发。
#   2) 若只想加速"安装包下载"、且不想重新打包：直接把加速后的完整地址
#      写进 latest.json 的 "url" 字段即可(服务端随时可改，客户端立即生效)。
#   —— 稳妥做法：打包前就把本前缀填一个当前可用的镜像，双保险。
DOWNLOAD_ACCEL_PREFIX = "https://gh-proxy.com/"   # 2026-07 实测可代理 release 下载；失效可换 ghfast.top / ghproxy.net

# 是否在启动时静默检查更新（可被用户设置覆盖）
CHECK_UPDATE_ON_START = False


def version_str():
    """带前缀的版本字符串，用于界面显示。"""
    return "v" + VERSION


def full_title():
    """窗口标题用的完整名称。"""
    return "%s  %s" % (APP_NAME, version_str())
