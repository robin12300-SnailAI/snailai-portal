---
name: andrew-clinic-version-badge
overview: 在 Andrew 诊所首页左上角添加胶囊状版本号徽章，自动从 version.json 读取版本号，每次部署后可直观确认推送成功。
design:
  architecture:
    framework: html
  styleKeywords:
    - Minimalism
    - Pill-badge
    - Subtle
  fontSystem:
    fontFamily: Montserrat
    heading:
      size: 32px
      weight: 600
    subheading:
      size: 18px
      weight: 500
    body:
      size: 16px
      weight: 400
  colorSystem:
    primary:
      - "#000000"
    background:
      - "#FFFFFF"
    text:
      - "#FFFFFF"
    functional:
      - "#D79D7D"
todos:
  - id: add-version-html
    content: 在 index.html navbar 内 nav-left 前插入版本胶囊元素
    status: completed
  - id: add-version-css
    content: 在 main.css 新增 .nav-version-pill 样式 + responsive.css 移动端适配
    status: completed
    dependencies:
      - add-version-html
  - id: add-version-js
    content: 在 main.js 新增 fetch version.json 动态填充版本号逻辑
    status: completed
    dependencies:
      - add-version-html
  - id: bump-version
    content: 更新 version.json 为 3.2.3 并推送部署
    status: completed
    dependencies:
      - add-version-css
      - add-version-js
---

## 产品概述

在 Andrew 诊所网站首页左上角添加一个胶囊状版本号徽章，每次推送更新后通过版本号直观确认部署成功。

## 核心功能

- 首页左上角显示胶囊状版本号（如 V3.2.3）
- 版本号从 version.json 动态读取，每次只需改 version.json 即可自动更新
- 版本号在 navbar 透明/白色两种状态下都清晰可见
- 移动端也可见（尺寸适配）
- 同步修复 footer 中过时的 V3.0.0 版本号

## 技术方案

### 实现策略

在 navbar 内 `.nav-left` 之前插入一个版本胶囊元素，用 JS fetch `version.json` 动态填充版本号。样式复用已有 `.footer-version-pill` 的设计语言（黑底白字胶囊），但作为独立 class `.nav-version-pill` 定位在 navbar 左侧。

### 关键技术决策

1. **JS 动态读取 version.json** — 而非硬编码版本号，这样每次更新只需改 version.json 一个文件，所有位置自动同步
2. **放在 nav-container 内而非 fixed 定位** — 跟随 navbar 滚动，不需要额外 z-index 管理，且移动端自动适配
3. **独立 class `.nav-version-pill`** — 与 `.footer-version-pill` 共享设计语言但独立控制，避免改 footer 影响导航

### 修改文件清单

```
andrew-clinic/
├── index.html          # [MODIFY] 在 nav-left 前插入版本胶囊 HTML
├── css/main.css        # [MODIFY] 新增 .nav-version-pill 样式
├── css/responsive.css  # [MODIFY] 移动端版本胶囊尺寸适配
├── js/main.js          # [MODIFY] 新增 fetch version.json 并填充版本号的逻辑
└── version.json        # [MODIFY] 版本号 3.2.2 → 3.2.3
```

### 实现细节

**index.html**：在 `.nav-left` div 之前插入：

```html
<span class="nav-version-pill" id="navVersion"></span>
```

**main.css**：新增 `.nav-version-pill` 样式，复用 footer-version-pill 的设计语言但调整位置和间距：

- 黑底白字胶囊，border-radius: 30px
- font-size: 0.6rem，不抢导航链接视觉权重
- margin-right: 12px 与 nav-link 间距一致

**responsive.css**：移动端（768px 以下）nav-left 隐藏时，版本胶囊需保持可见，可移到 logo 旁边或独立显示

**main.js**：页面加载时 fetch('version.json') 读取版本号，填充到 `#navVersion` 和 footer 中的 `.footer-version-pill`

**version.json**：3.2.2 → 3.2.3

## 设计方案

在 navbar 左侧、导航链接之前添加一个微型胶囊版本号徽章。

### 视觉规格

- 形状：胶囊（pill），border-radius: 30px
- 配色：黑底（#000000）白字（#ffffff），与现有 footer-version-pill 一致
- 字体：Montserrat 600，0.6rem，letter-spacing: 0.1em
- 内边距：2px 10px
- 位置：navbar 内、nav-left 最左侧
- 视觉权重：极低，不干扰导航，仅作开发确认用途

### 状态适配

- Navbar 透明时（页面顶部）：黑底白字胶囊在透明背景上清晰可见
- Navbar 白色时（滚动后）：黑底白字胶囊在白色背景上同样清晰
- 移动端：nav-link 隐藏时版本胶囊保持可见，紧贴 logo 左侧

### Footer 同步

- Footer 中过时的 V3.0.0 也由 JS 动态填充，与左上角版本号统一来源