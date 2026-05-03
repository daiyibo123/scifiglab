# SciFigLab

SciFigLab 是一个面向科研与工程实验数据的可视化图生成平台，支持实验记录、指标解析、交互式图表、多实验对比和论文结果表导出。

## 功能特性

- **项目管理** — 按研究领域组织项目，支持描述与标签
- **实验管理** — 创建实验、设置状态/标记（最佳、论文使用、归档），自动生成实验编号
- **文件上传与加密** — 支持日志、CSV、配置文件等，上传自动加密存储，保护实验数据安全
- **日志智能解析** — 自动从训练日志中提取 epoch、step、指标值
- **CSV 指标导入** — 批量导入 CSV 格式的指标数据
- **配置文件解析** — 解析 YAML/JSON/TOML/INI 配置，展示超参数表
- **交互式图表** — 折线/柱状/散点/面积/阶梯等多种图表类型，支持多指标选择、平滑、最佳点标注
- **多格式导出** — 图表导出 PNG / JPG / SVG 矢量图 / PDF
- **多实验对比** — 跨实验同指标对比图表与摘要表
- **实验组与论文表格** — 分组管理实验，一键生成 Markdown / CSV 论文结果表，自动加粗最优值
- **仪表盘** — 项目/实验/文件/指标统计总览，最近实验动态
- **管理后台** — 管理员功能开关、用户管理，首次部署自动初始化管理员
- **响应式 UI** — 可伸缩侧边栏导航，移动端适配，美观首页

## 部署

### 方式一：本地启动

```bash
# 克隆项目
git clone https://github.com/daiyibo123/scifiglab.git
cd scifiglab

# 创建虚拟环境并安装依赖
python -m venv venv
# Windows: venv\Scripts\activate / Linux: source venv/bin/activate
pip install -r requirements.txt

# 复制环境变量并修改 SECRET_KEY
cp .env.example .env

# 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 方式二：Docker 部署（推荐）

```bash
cp .env.example .env
docker-compose up -d --build
```

启动后访问 http://localhost:8000，首次会自动跳转管理员初始化页面。

## 在线更新

管理员登录后，侧边栏会显示“更新”按钮。点击后会从 GitHub 拉取最新代码，且只更新代码，不更新数据库、用户和上传文件。

在线更新的前提：

- 服务器部署目录必须通过 `git clone https://github.com/daiyibo123/scifiglab.git` 获得。
- `data/`、`.env`、`*.db`、`*.sqlite3` 不应被 Git 跟踪。
- Docker 部署时容器会挂载当前代码目录到 `/app`，更新成功后通过 `restart: unless-stopped` 自动重启。
- 如果不是 Docker 环境，更新成功后需要手动重启服务。

### 环境变量

| 变量名 | 说明 |
| --- | --- |
| `SECRET_KEY` | JWT 与加密密钥，**生产环境务必修改** |
| `APP_ENV` | `development` / `production` |
| `UPLOAD_MAX_SIZE_MB` | 单文件最大上传大小，默认 `20` |
| `GITHUB_REPO_URL` | 在线更新使用的 GitHub 仓库地址 |

### Resend 邮件配置

注册验证码和服务器预警邮件都使用 SMTP 发送。使用 Resend 时，在 `.env` 中配置：

```env
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_USER=resend
SMTP_PASSWORD=你的 Resend API Key
SMTP_FROM=SciFigLab <no-reply@你的已验证域名>
SMTP_USE_TLS=true
```

`SMTP_FROM` 必须使用 Resend 已验证域名下的邮箱地址，例如 `no-reply@example.com`。DNS 中 DKIM、SPF、DMARC 验证通过后再启用发送。

## License

MIT
