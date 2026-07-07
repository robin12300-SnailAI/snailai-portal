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
          { id: "l01", title: "第 1 堂课 — 开营日：认识你的 AI 助手", desc: "龙虾(WorkBuddy)介绍、MCP与自定义技能、如何对话、个人AI刚需确定、学员刚需项目启动、注册 GitHub 账户、课后作业（连上 email/drive 等）", duration: "90 min", slides: [], materialsTitle: "20260707 课件链接", materials: [
            { name: "7月7日讲座讲稿（Word）", file: "https://drive.google.com/uc?export=download&id=15bzSSb4gi9TxUsyHk9NK6UBdz_3oYZxF" },
            { name: "AI 项目落地蓝图（PDF）", file: "https://drive.google.com/uc?export=download&id=11DvZPBYoh_O4ACB3m_jX90DbvZdyNnJo" },
            { name: "AI 提示词进阶指南（图片）", file: "https://drive.google.com/uc?export=download&id=18YGFjTb3C_IT0CQm9n8p9BT8Tg45pVi9" },
            { name: "打造你的专属 AI 数字分身（音频）", file: "https://drive.google.com/uc?export=download&id=1Xc8eoB-7nlxbV2fBvauIlstoUA8eWvM0" },
            { name: "AI 成功的秘密：从基础到自动化工作流（视频）", file: "https://drive.google.com/uc?export=download&id=1DvTNxaBGIEj7WOg_JLEXqpUHhHiYj3yQ" }
          ], videos: [],
            chapters: [
              "龙虾(WorkBuddy)总体介绍 — MCP 和自定义技能",
              "如何与龙虾(WorkBuddy)对话",
              "个人 AI 刚需确定",
              "选取一些学员开始 AI 刚需项目",
              "注册 GitHub 账户",
              "课后作业（连上 email / drive 等服务）"
            ]
          },
          { id: "l02", title: "第 2 堂课", desc: "AI 刚需项目启动与建设", duration: "90 min", slides: [], materials: [],
            chapters: [
              "AI 刚需提示词完工后，WorkBuddy 设立共享项，GitHub 推送",
              "学员上传项目资产",
              "开始项目 AI 建设",
              "作业：我的购买清单技能，SQLite 数据库"
            ] }
        ]
      },
      {
        title: "模块二 · 基础工具实战",
        lessons: [
          { id: "l03", title: "第 3 堂课", desc: "待定", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l04", title: "第 4 堂课", desc: "待定", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l05", title: "第 5 堂课", desc: "待定", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l06", title: "第 6 堂课", desc: "待定", duration: "90 min", slides: [], materials: [], chapters: [] }
        ]
      },
      {
        title: "模块三 · 生活场景应用",
        lessons: [
          { id: "l07", title: "第 7 堂课", desc: "待定", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l08", title: "第 8 堂课", desc: "待定", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l09", title: "第 9 堂课", desc: "待定", duration: "90 min", slides: [], materials: [], chapters: [] }
        ]
      },
      {
        title: "模块四 · 总结与下一步",
        lessons: [
          { id: "l10", title: "第 10 堂课 — 结营日", desc: "回顾核心方法、建立你的 AI 工作流、中级预告", duration: "90 min", slides: [], materials: [], chapters: [] }
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
          { id: "l01", title: "用 AI 武装投资决策", desc: "AI 时代的投资信息优势、认知框架", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l02", title: "数据驱动的投资思维", desc: "从感觉投资到数据投资、指标体系建设", duration: "90 min", slides: [], materials: [], chapters: [] }
        ]
      },
      {
        title: "模块二 · AI 分析实战",
        lessons: [
          { id: "l03", title: "财务与报税自动化（澳洲场景）", desc: "费用分析、银行对账单 OCR、AI 辅助报税", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l04", title: "股票 / 房产 AI 分析", desc: "强度系统、房产数据自动化、复盘方法", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l05", title: "银行对账单 OCR 与数据处理", desc: "扫描件识别、结构化数据、可视化", duration: "90 min", slides: [], materials: [], chapters: [] }
        ]
      },
      {
        title: "模块三 · AI 工作流搭建",
        lessons: [
          { id: "l06", title: "双 AI 执行模式", desc: "主管 AI + 执行 AI 协作干活", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l07", title: "自动化与每日提醒", desc: "自动化任务、企业微信推送、每日报告", duration: "90 min", slides: [], materials: [], chapters: [] }
        ]
      },
      {
        title: "模块四 · 综合与结营",
        lessons: [
          { id: "l08", title: "个人 AI 财富工作流搭建", desc: "从问题出发→选工具→自动化执行", duration: "90 min", slides: [], materials: [], chapters: [] },
          { id: "l09", title: "结营与持续升级", desc: "回顾、旗舰版介绍、3 个月学习计划", duration: "90 min", slides: [], materials: [], chapters: [] }
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
/* AI 能力清单（按等级分段，连续编号 1–22）
 * 字段：
 *   id      内部主键（保留 c01–c22，兼容旧备份）
 *   no      展示序号（1–22 连续）
 *   tier    等级：初级 | 中级 | 高级
 *   category 原主题标签（仅作小标签展示）
 *   name / desc  名称 / 说明
 * 打勾规则（见 AI 能力清单/index.html）：
 *   初级 → 助教打勾即过；中级 / 高级 → 助教初审 + 讲师终审。
 */
const CAPABILITIES = [
  /* ---------- 初级（助教打勾即过）---------- */
  { id: "c01", no: 1,  tier: "初级", category: "AI 认知与思维", name: "理解 AI 的能力边界", desc: "能说清大模型能做什么、不能做什么，不把 AI 当万能神" },
  { id: "c02", no: 2,  tier: "初级", category: "AI 认知与思维", name: "输出式学习思维", desc: "边用边学，用 AI 完成真实任务而非只看教程" },
  { id: "c03", no: 3,  tier: "初级", category: "AI 认知与思维", name: "从问题出发选工具", desc: "先有真实问题，再找 AI 怎么帮，而非为用而用" },
  { id: "c04", no: 4,  tier: "初级", category: "基础工具使用", name: "ChatGPT 提示词基础", desc: "会用角色+任务+约束结构，从问答题变选择题" },
  { id: "c05", no: 5,  tier: "初级", category: "基础工具使用", name: "豆包 / 语音输入法", desc: "会用悬浮窗语音输入，用语音和 AI 对话做记录" },
  { id: "c06", no: 6,  tier: "初级", category: "基础工具使用", name: "Gemini 与 Google 全家桶", desc: "会用侧边栏、Drive/Calendar 联动、记忆导入" },
  { id: "c07", no: 7,  tier: "初级", category: "基础工具使用", name: "NotebookLM 资料总结", desc: "上传资料让 AI 总结、提取要点" },
  { id: "c08", no: 8,  tier: "初级", category: "基础工具使用", name: "PDF / 文档处理", desc: "图片 PDF 转文字、生成 Word/PDF" },

  /* ---------- 中级（助教初审 + 讲师终审）---------- */
  { id: "c09", no: 9,  tier: "中级", category: "内容创作", name: "AI 写短视频脚本", desc: "会用钩子+内容+结尾结构生成脚本" },
  { id: "c10", no: 10, tier: "中级", category: "内容创作", name: "文生图提示词", desc: "能写基础文生图提示词生成图片" },
  { id: "c11", no: 11, tier: "中级", category: "内容创作", name: "AI 邮件处理", desc: "起草、翻译、提炼英文/中文邮件" },
  { id: "c12", no: 12, tier: "中级", category: "工作流与自动化", name: "双 AI 协作模式", desc: "主管 AI 规划 + 执行 AI 落地的工作流" },
  { id: "c13", no: 13, tier: "中级", category: "工作流与自动化", name: "提示词工程进阶", desc: "能从喜欢的模板提取并升级提示词" },
  { id: "c14", no: 14, tier: "中级", category: "工作流与自动化", name: "AI 记忆系统配置", desc: "会用 Soul/Identity/User/Memory 建立 AI 档案" },
  { id: "c15", no: 15, tier: "中级", category: "工作流与自动化", name: "自动化任务设置", desc: "会设每日/定时自动化，让 AI 替你跑" },
  { id: "c17", no: 16, tier: "中级", category: "工作流与自动化", name: "企业微信机器人推送", desc: "配置 Webhook，让 AI 推送到手机" },

  /* ---------- 高级（助教初审 + 讲师终审）---------- */
  { id: "c16", no: 17, tier: "高级", category: "工作流与自动化", name: "自定义技能开发", desc: "能用 MD+JSON 把重复工作变成一键技能" },
  { id: "c18", no: 18, tier: "高级", category: "财富 AI 应用", name: "财务 / 报税自动化", desc: "澳洲费用分析、银行对账单 OCR、报税整理" },
  { id: "c19", no: 19, tier: "高级", category: "财富 AI 应用", name: "股票 / 房产 AI 分析", desc: "用 AI 做强度系统、房产数据自动化复盘" },
  { id: "c20", no: 20, tier: "高级", category: "财富 AI 应用", name: "个人 AI 财富工作流", desc: "搭建从数据到决策的完整投资 AI 流程" },
  { id: "c21", no: 21, tier: "高级", category: "安全与伦理", name: "隐私与数据安全", desc: "知道什么资料不该喂给公开 AI、用本地/合规方案" },
  { id: "c22", no: 22, tier: "高级", category: "安全与伦理", name: "AI 内容甄别", desc: "能识别 AI 幻觉、交叉验证关键信息" }
];

/* 证书等级（按「已通过」项数解锁，类似青铜白银）
 * 已通过定义：初级=助教勾；中级/高级=助教勾且讲师勾。 */
const CERT_LEVELS = [
  { min: 22, key: "diamond",  name: "钻石", icon: "👑", color: "#7c4dff" },
  { min: 19, key: "platinum", name: "铂金", icon: "💎", color: "#26c6da" },
  { min: 16, key: "gold",     name: "黄金", icon: "🥇", color: "#ffb300" },
  { min: 12, key: "silver",   name: "白银", icon: "🥈", color: "#90a4ae" },
  { min: 8,  key: "bronze",   name: "青铜", icon: "🥉", color: "#cd7f32" }
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

/* ---------- 直播回放 · 配套课件 ----------
 * 每场直播除视频外，还整理了可学习的课件页（学习指南 / PDF / 配图 / NotebookLM）。
 * 字段：
 *   title   标题
 *   date    日期
 *   type    roadshow=路演 | livestream=直播
 *   desc    一句话简介（显示在卡片上）
 *   video   视频链接（内嵌预览）
 *   page    课件页相对路径（相对「路演直播 PPT」目录，如 "20260623 直播/"）
 */
const LIVE_LESSONS = [
  {
    id: "20260623",
    title: "AI 咒语重塑生意与财富",
    date: "2026-06-23",
    type: "livestream",
    desc: "完整学习指南：10 道自测题 + 答案 + 深度思考 + 术语表，附音频回放与 NotebookLM 闪卡。",
    video: "https://youtu.be/-7Hxlfj2QYg",
    page: "20260623 直播/"
  },
  {
    id: "20260704",
    title: "进化你的财富：AI 大师课 · 蜗牛 AI 财富澳洲应用课",
    date: "2026-07-04",
    type: "livestream",
    desc: "财富 AI 应用实战课件（15 页 PDF）+ 澳洲理财投资指南配图 + NotebookLM 闪卡自测。",
    video: "https://youtu.be/CInKi20s1i0",
    page: "20260704 直播/"
  }
];

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
