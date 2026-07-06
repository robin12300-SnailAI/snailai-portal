# 蜗牛AI 学员门户 — 后端部署与运维

后端：Python + Flask + 内置 `sqlite3`。既提供 REST API（`/api/*`），又托管整个学员门户静态站点（同源，免 CORS）。

---

## 一、本地运行

```bash
# 1) 创建并激活虚拟环境（一次性）
PY=/Users/robinmacpro2021/.workbuddy/binaries/python/versions/3.13.12/bin/python3
PYTHON_VENV=/Users/robinmacpro2021/.workbuddy/binaries/python/envs/snailai-portal
$PY -m venv "$PYTHON_VENV"
"$PYTHON_VENV/bin/pip" install -r server/requirements.txt

# 2) 启动（默认 127.0.0.1:5000）
PORT=5000 "$PYTHON_VENV/bin/python" server/app.py
```

打开 http://127.0.0.1:5000/ 即可。首次启动自动建库 `server/snailai.db` 并写入演示数据。

**演示账号**
- 学员：student01 / snail123
- 学员：student02 / snail123
- 助教：ta01 / snailai@ta
- 总讲师：teacher01 / snail@teacher

---

## 二、加真实学员 / 助教（上线前必做）

用 `manage.py`（不要手改数据库）：

```bash
cd 官网学生登录
VENV=/Users/robinmacpro2021/.workbuddy/binaries/python/envs/snailai-portal

# 列出当前用户
"$VENV/bin/python" server/manage.py listusers

# 新增学员
"$VENV/bin/python" server/manage.py adduser zhangsan "张三" student Snail2026!

# 新增助教
"$VENV/bin/python" server/manage.py adduser wangta "王助教" ta SnailTA2026!

# 重置某学员密码
"$VENV/bin/python" server/manage.py resetpw zhangsan NewPass123

# 删除用户及其勾选记录
"$VENV/bin/python" server/manage.py deluser zhangsan
```

> 删除学员会同时删除其能力清单勾选记录，谨慎操作。

---

## 三、生产部署

### 方案 A：Render（最简单，免费档可用）
1. 在 Render 新建 **Web Service**，连接本仓库（或上传 `官网学生登录/` 目录）。
2. Build Command：`pip install -r server/requirements.txt`
3. Start Command：`gunicorn -w 2 -b 0.0.0.0:$PORT server:app`
   - 需在 requirements.txt 取消 `gunicorn` 注释并 `pip install gunicorn`
4. 环境变量（可选）：`PORT`（Render 自动给）、`CORS_ORIGIN`（若门户走 GitHub Pages 填其域名，否则留 `*`）、`HOST=0.0.0.0`
5. 部署后会得到一个 `https://xxxx.onrender.com` 地址。

### 方案 B：自己的 VPS / 云服务器
```bash
# 服务器上
python3 -m venv venv && source venv/bin/activate
pip install -r server/requirements.txt
pip install gunicorn
# 用 gunicorn 常驻（配合 systemd / supervisor / nohup）
gunicorn -w 2 -b 0.0.0.0:5000 server:app
```
- `server/snailai.db` 是 SQLite 文件，随服务进程保存在磁盘，**务必定期备份此文件**。
- SQLite 适合几十~上百并发读写；学员规模更大时再迁移到 PostgreSQL（改 `db_conn()` 即可）。

### 跨域（GitHub Pages 门户 + 独立后端）
若门户继续托管在 GitHub Pages、后端单独部署，在门户任意页面 `<head>` 之前加：
```html
<script>window.SNAILAI_API_BASE = "https://你的后端地址";</script>
```
后端需设 `CORS_ORIGIN=https://你的githubpages域名`。

---

## 四、让 GitHub Pages 主站「学员登录」指向新后端

目前 `蜗牛 AI 线上课/snailai-website/` 等 6 个主站页面的「学员登录」按钮指向
`student/login.html`（GitHub Pages 路径，门户尚未部署到那）。后端上线后，把这 6 处链接改为后端地址，例如：
```
https://你的后端地址/login.html
```
（或统一改成后端域名根路径）。

---

## 五、接口一览

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/login` | 公开 | 登录，返回 `{token, user}` |
| POST | `/api/logout` | 登录 | 注销当前会话 |
| GET  | `/api/me` | 登录 | 当前用户信息 |
| GET  | `/api/capabilities` | 登录 | 全部能力项 |
| GET  | `/api/students` | 助教/总讲师 | 学员列表 |
| GET  | `/api/checks/<username>` | 本人/助教/总讲师 | 某学员勾选 |
| PUT  | `/api/checks/<username>/<capId>` | 按角色 | 勾选某一列 `{column, value}` |

**权限矩阵**（列 → 可修改角色）
- `self`（自查）：学员（仅自己）/ 助教 / 总讲师
- `ta`（初审）：助教 / 总讲师
- `final`（最终确认）：仅总讲师

---

## 六、备份与恢复

```bash
# 备份（直接拷文件即可，停止服务更稳妥）
cp server/snailai.db server/snailai.db.bak-$(date +%F)

# 恢复
cp server/snailai.db.bak-YYYY-MM-DD server/snailai.db
```

SQLite 单文件，可随项目一起进 Git（建议加 `.gitignore` 排除 `*.db` 仅在需要时提交快照）。
