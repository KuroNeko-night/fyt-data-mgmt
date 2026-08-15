"""账号密码策略的单一事实来源。

密码策略是账号安全的门槛校验，同时被 Web 服务端（``web_server.py``）与 Tkinter 控制台
（``web_control_gui.py``）的首次管理员密码输入复用。集中在此处可避免两处文案或规则漂移；
控制台只做预检提示，服务端建库时仍会再次执行权威校验，因此本模块保持纯标准库、无任何
配置或第三方依赖，控制台可在不加载 Web 服务栈的情况下安全导入。
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from . import config as server_config


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """使用 PBKDF2 生成密码盐值和摘要，二者均以十六进制持久化。

    新密码默认生成 16 字节随机盐；校验旧密码时显式传入数据库盐。迭代轮数来自统一配置，
    便于未来提升强度而不在认证服务中散落常量。
    """
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        server_config.PBKDF2_ROUNDS,
    )  # 密码始终按 UTF-8 编码，支持中文但不依赖系统代码页。
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, digest_hex: str) -> bool:
    """以恒定时间比较校验登录密码，避免摘要比较泄漏信息。"""
    _, candidate = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(candidate, digest_hex)


def password_policy_error(password: str) -> str:
    """返回面向用户的密码策略错误，空字符串表示通过。

    规则与 ``AGENTS.md`` 一致：至少 10 位、同时包含字母和数字，并限制上限长度以避免
    超大输入拖慢 PBKDF2 摘要计算。
    """
    if len(password) < 10:
        return "密码至少 10 位"
    if len(password) > 128:
        return "密码不能超过 128 位"
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        return "密码需同时包含字母和数字"
    return ""
