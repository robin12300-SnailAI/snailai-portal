# AGENTS.md — SnailAI Portal 项目规则（CodeBuddy 自动加载）

> **本文件由 CB（CodeBuddy）打开本项目时自动读取。**
> WB（WorkBuddy）侧对应技能：`皮肤科诊所网站`（~/.workbuddy/skills/皮肤科诊所网站/SKILL.md）。
> 两份文件核心规则同源，修改规则时两边同步更新。

---

## 一、项目档案（路径速查）

```bash
# 本地仓库根目录（完整路径，直接复制）
cd /Users/robinmacpro2021/龙虾文件夹/Andrew项目/皮肤科诊所项目/snailai-portal
```

| 项 | 值 |
|---|---|
| **本仓库职责** | snailai.ai 官网（Flask + 静态）+ Andrew 诊所网站 + Client Portal + 内部任务系统 |
| **诊所网站线上地址** | https://andrew.snailai.ai |
| **诊所网站目录** | 本仓库 `andrew-clinic/` |
| **git 分支** | `main`（受保护语义：push 即触发部署） |
| **部署** | push `main` → Render（服务 `snailai-portal-1`）自动部署，约 1–2 分钟 |
| **诊所网站当前版本** | V3.2.2（浅色杂志风） |
| **版本记录文件** | `andrew-clinic/version.json`（每次改动必须同步更新） |
| **网站主品牌** | SKIN CANCER LASER CENTRE |
| **视觉 model** | https://skinclinicmedspa.com（浅色杂志风基准；深色奢华风已被客户否决） |
| **客户** | Andrew Li & Co Pty Ltd（Dr Andrew Li / Dr Omid Zarbaft） |
| **合同** | Rev18（定稿，A$9,955 incl GST；W4=Booking 对接、W5=Payment 对接） |

### andrew-clinic/ 目录结构

```
andrew-clinic/
├── index.html / services.html / service-detail.html / doctors.html
├── appointment.html / contact.html        # 原型阶段：表单/邮件一律禁用
├── version.json                            # 版本记录，每次改动必更新
├── css/main.css + responsive.css           # 断点 1024/768/480
├── js/main.js + i18n.js + services-data.js
└── images/                                 # 63 文件（svc-*×20、insta-*×5、hero 视频、logo、医生真实照片）
```

---

## 二、修改 / 部署链路（铁律，每次必走）

```bash
# 1. 开工必拉最新（防冲突）
cd /Users/robinmacpro2021/龙虾文件夹/Andrew项目/皮肤科诊所项目/snailai-portal && git pull origin main

# 2. 改代码（andrew-clinic/ 下）

# 3. 本地验证（i18n 切换、图片、轮播、reveal 动画）

# 4. 更新 version.json + commit（Conventional Commits + 版本号）
git add -A
git commit -m "feat(andrew-clinic): V3.2.3 — 一句话说明"

# 5. 推送（触发 Render 自动部署）
git push origin main

# 6. 等 1–2 分钟 → 验证 https://andrew.snailai.ai → 向用户报告「修改前版本 → 新版本号」
```

**未部署、未报版本号 = 任务未完成。**

---

## 三、WB + CB 混合工作流（2026-08-31 确立）

同一台机器、同一 GitHub 账号，两个工具共用本仓库。git 仓库是唯一事实源。

### 分工

| 场景 | 用谁 |
|---|---|
| 文案更新、换图、调样式、加区块 | WB（其技能一条龙） |
| Booking / Payment / Helix 对接、API 集成、多文件工程重构 | **CB（本工具）** |

### 四条规矩

1. **单工具原则**：用 CB 时不碰 WB，反之亦然。绝不同时用两个工具改仓库。
2. **开工必 `git pull origin main`**。
3. **谁改谁推送**：CB 改完直接 commit → push → Render 部署 → 报版本号。**不需要回 WB 转手推送。**
4. **version.json 每次改动必须更新**。

---

## 四、三大对接红线（Booking / Payment / Helix）

来源：合同 Rev18 明文 + 医疗合规。**做对接前必读，违反即违约风险。**

| # | 红线 |
|---|---|
| 1 | **不直连 Helix 临床数据**：公开网站不得直接访问、查询或连接任何底层 Helix 数据库、临床数据、患者联系方式列表。只能走官方 API 层，且仅限预约必要数据 |
| 2 | **不存卡详情**：不存储任何银行卡数据。Payment 走托管支付路径（Stripe 等托管页），卡数据永不落地本站 |
| 3 | **Booking 走 API 层**（W4 工作流）：经预约供应商官方 API，不绕过直取数据库 |
| 4 | **密钥安全**：API 密钥只放服务端环境变量，**严禁写入客户端代码或 git 仓库** |
| 5 | **W8 受控部署边界**：生产部署需客户批准或客户发起的认证发布；凭据用 secrets 管理，不进源码/日志 |

---

## 五、技术规范（andrew-clinic）

### i18n（中英双语）
- 所有文本带 `data-en` / `data-zh` 属性，`js/i18n.js` 文本替换引擎切换
- **默认英文**（澳洲本地诊所）
- 语言切换按钮选择器：`.lang-toggle button` 和 `.nav-lang button` **两套都要绑定**

### 设计 token（浅色杂志风）
```css
--color-bg: #ffffff;      /* 主背景纯白 */
--color-text: #000000;    /* 正文纯黑 */
--color-accent: #d79d7d;  /* rose gold 强调 */
```
字体：Cormorant Garamond（标题）+ Montserrat（正文）+ Noto Serif/Sans SC（中文）。

### 原型守卫（铁律）
所有 mailto 链接、表单提交一律禁用（`initPrototypeGuard()` 拦截 + toast）。原型阶段不得出现邮件弹窗/表单跳转。

---

## 六、踩坑清单（8 条，改代码前必读）

| # | 坑 | 规避 |
|---|---|---|
| 1 | CSS 类重命名未全局搜复用 → 医生卡片消失 | **改类名前必 `grep -r` 全局搜复用** |
| 2 | 深色奢华风被客户否决 | 视觉基准 = skinclinicmedspa.com **浅色杂志风** |
| 3 | 医生简介被 AI 改写遭拒 | **简介逐字复制原站原文**，禁止润色 |
| 4 | i18n 选择器漏绑 → 中文切换失效 | 双选择器 `.lang-toggle` + `.nav-lang` 都绑 |
| 5 | Hero 视频 360° 环绕太晕 | 运动幅度控制在水平慢移（~70% 像素变化） |
| 6 | AI 生图并行同名覆盖 | **AI 生图串行执行**，文件名带语义/序号 |
| 7 | `loading="lazy"` 首屏图截图空白 | 关键首屏图用 `loading="eager"` |
| 8 | 改完不部署不报版本 | push + 报版本号 = 完整闭环 |

---

## 七、关键资产（勿动/勿替换）

| 资产 | 文件 | 约束 |
|---|---|---|
| 医生真实照片 | `images/dr-andrew-li-official.jpg`、`images/omid-zarbaft.jpg` | 原站真实照片，**禁止 AI 生成替换** |
| SCLC 官方 logo | `images/logo-sclc-410.png` 等 | 原站下载 |
| 医生简介文本 | `doctors.html` 内 | 逐字原站复制，禁止改写 |
