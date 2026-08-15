"""Web HTTP 请求协议和路由辅助模块。

本包承载同源 /api 的协议边界：``handler`` 负责请求分发，``routes`` 维护白名单路由表，
``context`` 解析会话与角色，``responses`` 统一 JSON/文件响应，``static_files`` 托管
Vite 构建产物，``path_params`` 做路径编号校验。业务规则不放在本包，而由领域服务与
``core`` 提供。
"""

