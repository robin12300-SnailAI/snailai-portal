---
name: andrew-clinic-AGENTS-md
overview: 在 andrew-clinic/ 目录下创建精简版 AGENTS.md，仅包含 Andrew 诊所相关规则，使 CodeBuddy 打开该目录时能自动加载项目上下文。
todos:
  - id: create-agents-md
    content: 创建 andrew-clinic/AGENTS.md 精简版项目规则文件
    status: completed
  - id: fix-version-json
    content: 修正 andrew-clinic/version.json 版本号为 V3.2.2
    status: completed
    dependencies:
      - create-agents-md
---

## 产品概述

在 `andrew-clinic/` 目录下创建一份精简版 AGENTS.md，使 CodeBuddy 打开该子目录时能自动加载 Andrew 诊所项目规则。

## 核心功能

- 从上级 AGENTS.md 提取仅与 Andrew 诊所相关的内容，去除蜗牛AI 门户相关部分
- 适配从 `andrew-clinic/` 子目录工作的场景（路径、部署命令等）
- 保留：项目档案、部署链路、三大对接红线、技术规范、踩坑清单、关键资产
- 去除：蜗牛AI 门户内容、WB+CB 混合工作流、企业商机扫描
- 文件创建后同步更新上级 AGENTS.md 中的版本号引用

## 技术方案

纯文档任务，创建一个 Markdown 文件。无代码变更。

### 关键适配点

1. **路径**：工作目录从仓库根变为 `andrew-clinic/`，所有相对路径需调整
2. **部署链路**：git 操作仍需从仓库根执行，需在文档中明确说明
3. **内容来源**：从上级 AGENTS.md 的七个章节中提取五个（一、二、四、五、六、七），跳过三（WB+CB 混合工作流）
4. **version.json**：当前值为 `1.0.0`，与实际 V3.2.2 不一致，需一并修正