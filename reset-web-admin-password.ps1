$ErrorActionPreference = "Stop"

# 在本机停止服务后重置 Web 数据库中的 admin 密码。
# 密码通过 SecureString 读取，只在当前进程内短暂转换为明文并经环境变量传给 Python；finally
# 会清零非托管内存并移除环境变量。脚本复用服务端哈希和建库实现，不自行复制密码算法。
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"  # 必须使用项目环境以加载同版本 web_server。
if (-not (Test-Path -LiteralPath $python)) {
  throw "尚未安装现代环境，请先运行 setup-modern.ps1。"
}

$secure = Read-Host "请输入新的管理员密码（至少 10 位，且包含字母和数字）" -AsSecureString
# SecureStringToBSTR 是调用 Python 前取得明文的必要边界，指针必须在 finally 中主动清零。
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  if ($plain.Length -lt 10 -or $plain -notmatch "[A-Za-z]" -or $plain -notmatch "\d") { throw "管理员密码至少 10 位，且需同时包含字母和数字。" }
  # 两个变量分别供重置代码取值和首次数据库初始化通过安全启动校验；都不写入配置文件。
  $env:FYT_NEW_ADMIN_PASSWORD = $plain
  $env:FYT_ADMIN_PASSWORD = $plain
  # SQL 使用参数绑定；盐值和摘要由服务端唯一实现生成，避免脚本与登录校验规则漂移。
  & $python -c "import os, web_server; password = os.environ['FYT_NEW_ADMIN_PASSWORD']; salt, digest = web_server.hash_password(password); web_server.init_db(); connection = web_server.db(); connection.execute('UPDATE users SET salt = ?, password_hash = ? WHERE username = ?', (salt, digest, 'admin')); connection.commit(); connection.close(); print('[完成] 管理员密码已更新。')"
  if ($LASTEXITCODE -ne 0) { throw "管理员密码更新失败。" }
} finally {
  if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }  # 释放前覆盖明文缓冲区。
  Remove-Item Env:FYT_NEW_ADMIN_PASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:FYT_ADMIN_PASSWORD -ErrorAction SilentlyContinue
}

