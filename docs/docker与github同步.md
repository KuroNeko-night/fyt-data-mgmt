# Docker 运行与 GitHub 同步

## Docker 运行

项目使用多阶段 Dockerfile：Node.js 阶段只构建 `web-app/dist`，Python 阶段运行 Web 服务。运行镜像不包含 Node.js、前端依赖、测试数据或开发打包工具。

基础镜像地址通过 `FYT_DOCKER_NODE_IMAGE` 和 `FYT_DOCKER_PYTHON_IMAGE` 配置。
`Dockerfile` 的标准默认值使用 Docker Hub；Compose 示例默认覆盖为 AWS Public ECR 上的
Docker 官方镜像副本，适合无法稳定访问 Docker Hub 的网络。若所在环境可直连 Docker
Hub，可在 `.env` 中改为 `node:22-bookworm-slim` 和 `python:3.13-slim-bookworm`；企业
环境也可替换为内部镜像仓库。

npm 和 pip 下载源分别通过 `FYT_DOCKER_NPM_REGISTRY`、`FYT_DOCKER_PIP_INDEX_URL`
配置。Dockerfile 默认使用官方源，Compose 示例默认覆盖为 npmmirror 和清华 PyPI 镜像。
若部署环境可以稳定访问官方源，可改为
`https://registry.npmjs.org` 和 `https://pypi.org/simple`。这些构建参数只能填写公开镜像
地址，不要在 URL 中嵌入用户名、密码或 Token，因为构建参数会出现在镜像构建元数据中。

首次运行：

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory secrets -Force
[System.IO.File]::WriteAllText(
  (Join-Path (Resolve-Path secrets) "admin-password.txt"),
  "请替换为至少10位且包含字母和数字的强密码",
  [System.Text.UTF8Encoding]::new($false)
)
docker compose up -d --build
docker compose ps
docker compose logs -f fyt-web
```

若首次构建失败，先执行 `docker desktop status` 和 `docker version` 确认 Linux 引擎已经
运行，再用 `docker compose --progress plain build` 查看具体是基础镜像、npm 还是 pip
网络阶段失败。不要因为镜像网络故障删除命名卷，构建过程不会修改业务数据卷。

默认只把容器端口绑定到 `127.0.0.1:8787`，适合由 Caddy、Nginx 或 Cloudflare Tunnel 反向代理。需要局域网直连时，把 `.env` 中的 `FYT_WEB_BIND` 改为 `0.0.0.0`。

运行数据位于 `FYT_DATA_DIR`，默认是 Docker 命名卷 `fyt-data`；Docker 会用镜像内 `fyt` 用户的权限初始化它，不会出现 Linux 绑定目录常见的 UID 写入问题。需要让宿主机直接看到数据时，可将 `FYT_DATA_DIR` 改为绝对路径；Linux 绑定目录先执行 `sudo chown -R 10001:10001 /srv/fyt-data`。不要执行 `docker compose down -v`，除非已确认不再需要 Docker 命名卷。

容器以 UID/GID `10001` 的非 root 用户运行。若宿主机使用绝对目录挂载，先创建并授权：

```bash
sudo mkdir -p /srv/fyt-data
sudo chown -R 10001:10001 /srv/fyt-data
```

公网 HTTPS 不由应用容器直接负责。证书、Tunnel token 和私钥只放在宿主机或密钥管理系统，不放进镜像和仓库。

容器日志使用 Docker `json-file` 驱动，单文件最多 10 MB、保留 3 份，避免 Docker 日志
无限增长。应用业务输出和回收站仍按服务端自身保留规则管理。

## 与 GitHub 同步

仓库地址固定为 `https://github.com/KuroNeko-night/fyt-data-mgmt.git`。同步脚本会初始化 Git、设置 `origin`、切换到 `main`、检查暂存文件，并拒绝运行数据、数据库、日志、证书、压缩包和构建产物。

Windows：

```powershell
.\scripts\sync-github.ps1 -Message "说明本次修改"
.\scripts\sync-github.ps1 -Message "说明本次修改" -Push
```

如果上一条命令已经完成本地提交，稍后也可以直接运行
`.\scripts\sync-github.ps1 -Push` 推送现有提交；Linux/macOS 对应使用
`bash scripts/sync-github.sh --push`。

Linux/macOS：

```bash
bash scripts/sync-github.sh --message "说明本次修改"
bash scripts/sync-github.sh --message "说明本次修改" --push
```

首次管理员密码通过只读 Docker secret 挂载到 `/run/secrets/fyt_admin_password`，不会进入镜像或容器环境变量。`secrets/admin-password.txt` 已被 Git 和 Docker 构建上下文排除。首次建库成功后，可把 `.env` 中的路径改回 `./secrets/admin-password.example.txt`，再删除真实密码文件；已有数据库的后续启动不会读取空示例文件。

首次推送前需要配置 GitHub SSH 或 Personal Access Token。不要把 token 写进脚本、`.env`、Dockerfile 或日志。

## 自动质量检查

`.github/workflows/ci.yml` 会在 `main`/`master` 的推送和 Pull Request 上执行 Python 回归、Web 构建和 Docker 镜像构建。工作流只有读取权限，不会自动发布镜像、修改生产数据或推送代码。
