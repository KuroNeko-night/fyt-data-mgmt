"""Web 接口层的预期错误类型。"""

from __future__ import annotations


class ApiError(Exception):
    """携带 HTTP 状态码和可直接展示给用户的错误文本。"""

    def __init__(self, status: int, message: str):
        """保存稳定的状态码与客户文案，供统一异常响应层序列化。

        该异常只用于权限不足、参数不合法、资源不存在等预期失败。未预期异常不应包装
        成 ``ApiError``，否则可能把内部路径或第三方异常内容直接暴露给浏览器。
        """
        super().__init__(message)
        self.status = status
        self.message = message
