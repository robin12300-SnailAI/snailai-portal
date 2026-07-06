# 蜗牛AI 学员门户 (snailai-portal)

学员 / 助教 / 总讲师三角色登录的 AI 培训学员门户，后端用 **Flask + SQLite** 统一管理账号与「AI 能力清单」三勾选。

## 功能

- **三角色登录**：学员（自查）、助教（初审）、总讲师（最终确认），密码 pbkdf2 + salt 哈希
- **AI 能力清单**：每项能力 3 步确认（自查 → 初审 → 最终确认），后端强制权限隔离
- **课程中心**：AI 应用线上班、AI 财富线下班，课时页内嵌 PPT 与 YouTube 视频、配套资料下载
- **路演直播 PPT**：历次分享会 / 直播回放内嵌播放
- **仪表盘**：学员看自己进度，助教/总讲师看全员总览

## 目录结构

```
官网学生登录/
├── server/                # 后端：Flask + SQLite（REST API + 托管静态站）
│   ├── app.py             # 主程序：API + 静态托管 + 权限
│   ├── manage.py          # 命令行：增删改学员/助教、重置密码
│   ├── requirements.txt
│   └── README.md          # 部署文档（Render / VPS）
├── assets/                # 前端公共 JS/CSS
│   ├── auth.js            # API 登录/登出/token
│   ├── app.js             # 公共导航 + 登录守卫
│   ├── data.js            # 课程/视频/能力项数据（静态）
│   └── styles.css
├── login.html             # 登录页
├── dashboard.html         # 学员仪表盘
├── lesson.html            # 通用课时页（PPT + 视频 + 资料）
├── AI 能力清单/           # 三角色能力清单勾选
├── AI 应用线上班/         # 线上班课程列表
├── AI 财富线下班/         # 财富班课程列表
└── 路演直播 PPT/          # 路演/直播回放
```

## 本地运行

```bash
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PORT=5000 python app.py
# 打开 http://127.0.0.1:5000/
```

演示账号（上线前请用 manage.py 替换）：

| 角色 | 账号 | 密码 |
|------|------|------|
| 学员 | student01 | snail123 |
| 助教 | ta01 | snailai@ta |
| 总讲师 | teacher01 | snail@teacher |

## 后端部署

见 [`server/README.md`](server/README.md)。部署后把 6 个主站「学员登录」链接改指向后端地址即可。

> 注：路演/课程内容的大媒体文件（音频、PDF、图片）不入库，单独托管。
