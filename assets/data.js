/* ============================================================
 * 蜗牛AI 学员门户 — 数据中心
 * 所有课程、课时、能力清单都在这里定义。
 * 你后续放资料时，只需修改本文件对应字段即可，无需改 HTML。
 * ============================================================ */

/* ---------- 班级定义 ---------- */
const COURSES = {
  online: {
    id: "online",
    name: "AI 应用线上班",
    nameEn: "AI Application · Online",
    desc: "零基础到能用的 AI 应用入门。10 课时带你用 AI 解决日常工作生活问题，建立 AI 思维。",
    cover: "🟢",
    basePath: "AI 应用线上班/lesson",
    modules: [
      {
        title: "模块一 · AI 认知觉醒",
        lessons: [
          { id: "l01", title: "AI 是什么，不是什么", desc: "大模型认知、能力边界、第一次和 AI 对话", duration: "45 min", slides: [], materials: [], videos: [{ title: "什么是 AI 刚需", url: "https://youtu.be/NZag6CZ0PHA" }] },
          { id: "l02", title: "输出式学习 — 你的不懂恰恰是 AI 存在的意义", desc: "边用边学 > 先学后用，用 AI 学一个不懂的东西", duration: "45 min", slides: [], materials: [] }
        ]
      },
      {
        title: "模块二 · 基础工具实战",
        lessons: [
          { id: "l03", title: "ChatGPT 正确使用姿势", desc: "从问答题变选择题、提示词基本结构、避免总结的坑", duration: "45 min", slides: [], materials: [] },
          { id: "l04", title: "AI 输入法与应用安装", desc: "豆包输入法悬浮窗、语音转文字、用语音做日记", duration: "45 min", slides: [], materials: [] },
          { id: "l05", title: "Gemini 与 Google 全家桶", desc: "侧边栏、Drive/Calendar/Tasks 联动、记忆功能", duration: "45 min", slides: [], materials: [] },
          { id: "l06", title: "AI 文档与内容处理", desc: "NotebookLM、PDF 扫描件处理、Word/PDF 生成", duration: "45 min", slides: [], materials: [] }
        ]
      },
      {
        title: "模块三 · 生活场景应用",
        lessons: [
          { id: "l07", title: "AI 与邮件、日常信息处理", desc: "浏览器插件、邮件起草翻译、微信里用 AI", duration: "45 min", slides: [], materials: [] },
          { id: "l08", title: "AI 与购物、生活决策", desc: "亚马逊比价、优缺点对比表、购买决策", duration: "45 min", slides: [], materials: [] },
          { id: "l09", title: "AI 与内容创作入门", desc: "短视频脚本、文生图、简单视频生成", duration: "45 min", slides: [], materials: [] }
        ]
      },
      {
        title: "模块四 · 总结与下一步",
        lessons: [
          { id: "l10", title: "AI 开窍日 — 你能用 AI 做什么", desc: "回顾核心方法、建立你的 AI 工作流、中级预告", duration: "45 min", slides: [], materials: [] }
        ]
      }
    ]
  },

  offline: {
    id: "offline",
    name: "AI 财富线下班",
    nameEn: "AI Wealth · Offline (Sydney)",
    desc: "悉尼线下·用 AI 武装投资决策。从财务自动化到股票/房产 AI 分析，搭建你的个人 AI 财富工作流。",
    cover: "💰",
    basePath: "AI 财富线下班/lesson",
    modules: [
      {
        title: "模块一 · AI 投资认知",
        lessons: [
          { id: "l01", title: "用 AI 武装投资决策", desc: "AI 时代的投资信息优势、认知框架", duration: "90 min", slides: [], materials: [] },
          { id: "l02", title: "数据驱动的投资思维", desc: "从感觉投资到数据投资、指标体系建设", duration: "90 min", slides: [], materials: [] }
        ]
      },
      {
        title: "模块二 · AI 分析实战",
        lessons: [
          { id: "l03", title: "财务与报税自动化（澳洲场景）", desc: "费用分析、银行对账单 OCR、AI 辅助报税", duration: "90 min", slides: [], materials: [] },
          { id: "l04", title: "股票 / 房产 AI 分析", desc: "强度系统、房产数据自动化、复盘方法", duration: "90 min", slides: [], materials: [] },
          { id: "l05", title: "银行对账单 OCR 与数据处理", desc: "扫描件识别、结构化数据、可视化", duration: "90 min", slides: [], materials: [] }
        ]
      },
      {
        title: "模块三 · AI 工作流搭建",
        lessons: [
          { id: "l06", title: "双 AI 执行模式", desc: "主管 AI + 执行 AI 协作干活", duration: "90 min", slides: [], materials: [] },
          { id: "l07", title: "自动化与每日提醒", desc: "自动化任务、企业微信推送、每日报告", duration: "90 min", slides: [], materials: [] }
        ]
      },
      {
        title: "模块四 · 综合与结营",
        lessons: [
          { id: "l08", title: "个人 AI 财富工作流搭建", desc: "从问题出发→选工具→自动化执行", duration: "90 min", slides: [], materials: [] },
          { id: "l09", title: "结营与持续升级", desc: "回顾、旗舰版介绍、3 个月学习计划", duration: "90 min", slides: [], materials: [] }
        ]
      }
    ]
  }
};

/* ---------- AI 能力清单（所有学员通用）----------
 * 每个能力项：
 *   id        唯一标识
 *   category  所属类别
 *   name      能力名称
 *   desc      一句话说明（让学员知道这是什么）
 * 学员勾选状态与教师确认状态存 localStorage，不在此处。
 */
const CAPABILITIES = [
  { id: "c01", category: "AI 认知与思维", name: "理解 AI 的能力边界", desc: "能说清大模型能做什么、不能做什么，不把 AI 当万能神" },
  { id: "c02", category: "AI 认知与思维", name: "输出式学习思维", desc: "边用边学，用 AI 完成真实任务而非只看教程" },
  { id: "c03", category: "AI 认知与思维", name: "从问题出发选工具", desc: "先有真实问题，再找 AI 怎么帮，而非为用而用" },

  { id: "c04", category: "基础工具使用", name: "ChatGPT 提示词基础", desc: "会用角色+任务+约束结构，从问答题变选择题" },
  { id: "c05", category: "基础工具使用", name: "豆包 / 语音输入法", desc: "会用悬浮窗语音输入，用语音和 AI 对话做记录" },
  { id: "c06", category: "基础工具使用", name: "Gemini 与 Google 全家桶", desc: "会用侧边栏、Drive/Calendar 联动、记忆导入" },
  { id: "c07", category: "基础工具使用", name: "NotebookLM 资料总结", desc: "上传资料让 AI 总结、提取要点" },
  { id: "c08", category: "基础工具使用", name: "PDF / 文档处理", desc: "图片 PDF 转文字、生成 Word/PDF" },

  { id: "c09", category: "内容创作", name: "AI 写短视频脚本", desc: "会用钩子+内容+结尾结构生成脚本" },
  { id: "c10", category: "内容创作", name: "文生图提示词", desc: "能写基础文生图提示词生成图片" },
  { id: "c11", category: "内容创作", name: "AI 邮件处理", desc: "起草、翻译、提炼英文/中文邮件" },

  { id: "c12", category: "工作流与自动化", name: "双 AI 协作模式", desc: "主管 AI 规划 + 执行 AI 落地的工作流" },
  { id: "c13", category: "工作流与自动化", name: "提示词工程进阶", desc: "能从喜欢的模板提取并升级提示词" },
  { id: "c14", category: "工作流与自动化", name: "AI 记忆系统配置", desc: "会用 Soul/Identity/User/Memory 建立 AI 档案" },
  { id: "c15", category: "工作流与自动化", name: "自动化任务设置", desc: "会设每日/定时自动化，让 AI 替你跑" },
  { id: "c16", category: "工作流与自动化", name: "自定义技能开发", desc: "能用 MD+JSON 把重复工作变成一键技能" },
  { id: "c17", category: "工作流与自动化", name: "企业微信机器人推送", desc: "配置 Webhook，让 AI 推送到手机" },

  { id: "c18", category: "财富 AI 应用", name: "财务 / 报税自动化", desc: "澳洲费用分析、银行对账单 OCR、报税整理" },
  { id: "c19", category: "财富 AI 应用", name: "股票 / 房产 AI 分析", desc: "用 AI 做强度系统、房产数据自动化复盘" },
  { id: "c20", category: "财富 AI 应用", name: "个人 AI 财富工作流", desc: "搭建从数据到决策的完整投资 AI 流程" },

  { id: "c21", category: "安全与伦理", name: "隐私与数据安全", desc: "知道什么资料不该喂给公开 AI、用本地/合规方案" },
  { id: "c22", category: "安全与伦理", name: "AI 内容甄别", desc: "能识别 AI 幻觉、交叉验证关键信息" }
];

/* 路演 / 直播 PPT（独立板块，统一展示）
 * 字段说明：
 *   title  标题
 *   url    视频链接（YouTube 播放器内嵌）；留空则显示「待上传」
 *   date   日期（可选）
 *   type   roadshow=路演 | livestream=直播（仅用于标签显示）
 */
const ROADSHOW_SLIDES = [
  { title: "蜗牛AI · 澳洲华人 AI 应用私享会 (2026-06-20)", url: "https://www.youtube.com/watch?v=DUJSgMQ-4BI", date: "2026-06-20", type: "roadshow" },
  { title: "Robin 财富直播 (2026-07-04)", url: "https://www.youtube.com/watch?v=qIZp8pTQA3M", date: "2026-07-04", type: "livestream" },
  { title: "蜗牛 AI 官方播放列表", url: "https://www.youtube.com/embed/videoseries?list=PLrAXtmRdnEQy6nuLMfO9tV4rnQ5w8e6yA", date: "", type: "playlist" }
];

/* 课前 4 小时预习视频（线上班开班前必看）*/
const PREP_VIDEO = { title: "开课前核心准备 · 4 小时 AI 基础预习", url: "https://www.youtube.com/watch?v=--Qcfa5Kwbo" };

/* ---------- YouTube 解析 / 内嵌助手 ---------- */
/* 从各种 YouTube 链接中提取可嵌入的信息：{id} 或 {list} */
function ytParse(url) {
  if (!url) return null;
  const pl = url.match(/[?&]list=([^&]+)/);
  // 播放列表内嵌（videoseries）优先按列表处理
  if (pl && /videoseries/.test(url)) return { list: pl[1] };
  let m;
  if ((m = url.match(/[?&]v=([^&]+)/))) return { id: m[1] };
  if ((m = url.match(/youtu\.be\/([^?]+)/))) return { id: m[1] };
  if ((m = url.match(/youtube\.com\/embed\/([^?]+)/))) return { id: m[1] };
  if (pl) return { list: pl[1] };
  return null;
}
/* 生成响应式 YouTube 内嵌播放器 HTML；无有效链接返回空串 */
function ytEmbedHtml(url, title) {
  const r = ytParse(url);
  if (!r) return "";
  const src = r.list
    ? "https://www.youtube.com/embed/videoseries?list=" + r.list
    : "https://www.youtube.com/embed/" + r.id;
  return `<div class="yt-wrap"><iframe src="${src}" title="${title || "YouTube"}" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen loading="lazy"></iframe></div>`;
}
