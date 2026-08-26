/**
 * SKIN CANCER LASER CENTRE — Services Data
 * Version: 1.0.0
 * Bilingual data for service-detail.html template
 */

const SERVICES_DATA = {
  "skin-analysis": {
    id: "skin-analysis",
    title: { en: "SKIN ANALYSIS (VISIA)", zh: "皮肤分析 (VISIA)" },
    subtitle: { en: "Comprehensive Digital Skin Assessment", zh: "全面的数字皮肤评估" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>`,
    color: "#f5f5f5",
    description: {
      en: "VISIA Digital Skin Analysis uses advanced imaging technology to evaluate your skin's health across multiple dimensions. This non-invasive assessment provides a detailed understanding of your skin condition, enabling our team to create a personalised treatment plan.",
      zh: "VISIA 数字皮肤分析使用先进的成像技术，从多个维度评估您的皮肤健康。这项非侵入性评估详细解读您的皮肤状况，使我们的团队能够制定个性化治疗方案。"
    },
    sections: [
      {
        title: { en: "What VISIA Analyses", zh: "VISIA 分析项目" },
        type: "list",
        items: {
          en: ["Spots & pigmentation", "Wrinkles & fine lines", "Texture & smoothness", "Pores size & distribution", "UV damage & sun spots", "Red areas & vascularity", "Brown spots & melasma", "Acne & bacterial activity"],
          zh: ["色斑与色素沉着", "皱纹与细纹", "质地与光滑度", "毛孔大小与分布", "紫外线损伤与日晒斑", "泛红区域与血管", "棕色斑与黄褐斑", "痤疮与细菌活动"]
        }
      },
      {
        title: { en: "The Process", zh: "检查流程" },
        type: "steps",
        steps: [
          { num: 1, title: { en: "Consultation", zh: "咨询" }, desc: { en: "Brief discussion about your skin concerns", zh: "简要讨论您的皮肤问题" } },
          { num: 2, title: { en: "Imaging", zh: "成像" }, desc: { en: "VISIA captures multi-spectral images", zh: "VISIA 捕获多光谱图像" } },
          { num: 3, title: { en: "Analysis", zh: "分析" }, desc: { en: "AI-powered skin analysis and scoring", zh: "AI 驱动的皮肤分析和评分" } },
          { num: 4, title: { en: "Plan", zh: "方案" }, desc: { en: "Personalised treatment recommendations", zh: "个性化治疗建议" } }
        ]
      }
    ],
    cta: { en: "Book Your Skin Analysis", zh: "预约皮肤分析" }
  },

  "pdt": {
    id: "pdt",
    title: { en: "PHOTO DYNAMIC THERAPY (PDT)", zh: "光动力疗法 (PDT)" },
    subtitle: { en: "Light-Activated Treatment for Skin Cancer & Pre-Cancerous Lesions", zh: "光激活治疗皮肤癌及癌前病变" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>`,
    color: "#fff8e1",
    description: {
      en: "Photodynamic Therapy (PDT) is an advanced, non-surgical treatment that uses a photosensitising agent and specific light wavelength to selectively destroy abnormal skin cells. It is highly effective for treating skin cancers, pre-cancerous lesions (actinic keratoses), and certain skin conditions with excellent cosmetic outcomes.",
      zh: "光动力疗法 (PDT) 是一种先进的非手术治疗，使用光敏剂和特定波长的光线选择性地破坏异常皮肤细胞。它对治疗皮肤癌、癌前病变（日光性角化病）和某些皮肤病症非常有效，且具有出色的美容效果。"
    },
    sections: [
      {
        title: { en: "How PDT Works", zh: "PDT 治疗原理" },
        type: "steps",
        steps: [
          { num: 1, title: { en: "Application", zh: "涂抹光敏剂" }, desc: { en: "A photosensitising agent is applied to the treatment area and allowed to incubate for a specific period", zh: "将光敏剂涂抹于治疗区域，并让其孵育一段时间" } },
          { num: 2, title: { en: "Absorption", zh: "光敏剂吸收" }, desc: { en: "The agent is selectively absorbed by abnormal cells, which have higher metabolic activity", zh: "光敏剂被代谢活性更高的异常细胞选择性吸收" } },
          { num: 3, title: { en: "Activation", zh: "光照激活" }, desc: { en: "A specific wavelength of light activates the agent, producing reactive oxygen species", zh: "特定波长的光线激活光敏剂，产生活性氧" } },
          { num: 4, title: { en: "Destruction", zh: "病灶清除" }, desc: { en: "The reactive oxygen species destroy the targeted abnormal cells while preserving healthy tissue", zh: "活性氧破坏目标异常细胞，同时保护健康组织" } }
        ]
      },
      {
        title: { en: "Indications", zh: "适应症" },
        type: "list",
        items: {
          en: [
            "Actinic Keratoses (pre-cancerous lesions)",
            "Superficial Basal Cell Carcinoma",
            "Bowen's Disease (squamous cell carcinoma in situ)",
            "Field cancerisation (widespread sun damage)",
            "Moderate to severe acne",
            "Photorejuvenation & sun-damaged skin"
          ],
          zh: [
            "日光性角化病（癌前病变）",
            "浅表性基底细胞癌",
            "鲍恩病（原位鳞状细胞癌）",
            "区域癌化（广泛性日光损伤）",
            "中重度痤疮",
            "光子嫩肤与日晒受损皮肤"
          ]
        }
      },
      {
        title: { en: "Post-Treatment Care", zh: "治疗后护理" },
        type: "list",
        items: {
          en: [
            "Avoid direct sunlight for 48 hours after treatment",
            "Keep treated area clean and moisturised",
            "Apply prescribed healing ointment as directed",
            "Expect redness, swelling and crusting for 5-7 days",
            "Use broad-spectrum SPF 50+ sunscreen daily",
            "Follow up with your practitioner at recommended intervals"
          ],
          zh: [
            "治疗后 48 小时内避免阳光直射",
            "保持治疗区域清洁和滋润",
            "按医嘱涂抹处方愈合药膏",
            "预期 5-7 天内出现红肿和结痂",
            "每天使用广谱 SPF 50+ 防晒霜",
            "按建议间隔随访"
          ]
        }
      },
      {
        title: { en: "PDT vs Other Treatments", zh: "PDT 与其他疗法对比" },
        type: "comparison",
        headers: { en: ["Feature", "PDT", "Surgery", "Cryotherapy", "5-FU Cream"], zh: ["特点", "PDT", "手术", "冷冻疗法", "5-FU 乳膏"] },
        rows: [
          { en: ["Scarring", "Minimal", "Possible", "Possible", "Minimal"], zh: ["疤痕", "极少", "可能", "可能", "极少"] },
          { en: ["Downtime", "5-7 days", "2-4 weeks", "1-2 weeks", "4-8 weeks"], zh: ["恢复期", "5-7 天", "2-4 周", "1-2 周", "4-8 周"] },
          { en: ["Cosmetic Outcome", "Excellent", "Variable", "Variable", "Good"], zh: ["美容效果", "优秀", "因人而异", "因人而异", "良好"] },
          { en: ["Field Treatment", "Yes", "No", "No", "Yes"], zh: ["区域治疗", "是", "否", "否", "是"] },
          { en: ["Sessions Required", "1-2", "1", "1-3", "Daily x weeks"], zh: ["所需疗程", "1-2 次", "1 次", "1-3 次", "每日持续数周"] }
        ]
      }
    ],
    cta: { en: "Book PDT Consultation", zh: "预约 PDT 咨询" }
  },

  "dermal-enhancement": {
    id: "dermal-enhancement",
    title: { en: "DERMAL ENHANCEMENT", zh: "皮肤焕新" },
    subtitle: { en: "FracRevive® Nd:YAG Laser Skin Rejuvenation", zh: "FracRevive® Nd:YAG 激光皮肤焕新" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    color: "#e8eaf6",
    description: {
      en: "FracRevive® Nd:YAG laser treatment stimulates collagen production and promotes skin rejuvenation. This fractional laser technology targets specific areas of the skin, triggering the body's natural healing response to improve texture, tone and firmness.",
      zh: "FracRevive® Nd:YAG 激光治疗刺激胶原蛋白生成，促进皮肤焕新。这种点阵激光技术针对皮肤的特定区域，触发身体自然愈合反应，改善质地、色调和紧致度。"
    },
    sections: [
      {
        title: { en: "Benefits", zh: "优势" },
        type: "list",
        items: {
          en: ["Stimulates natural collagen production", "Improves skin texture and tone", "Reduces fine lines and wrinkles", "Minimises pore appearance", "Minimal downtime", "Safe for most skin types"],
          zh: ["刺激天然胶原蛋白生成", "改善皮肤质地和色调", "减少细纹和皱纹", "缩小毛孔外观", "恢复期短", "适用于大多数皮肤类型"]
        }
      }
    ],
    cta: { en: "Book Dermal Enhancement", zh: "预约皮肤焕新" }
  },

  "pico-laser": {
    id: "pico-laser",
    title: { en: "PICO LASER", zh: "皮秒激光" },
    subtitle: { en: "Fotona StarWalker® PICO Pro + FracTAT®", zh: "Fotona StarWalker® PICO Pro + FracTAT®" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>`,
    color: "#fce4ec",
    description: {
      en: "The Fotona StarWalker® PICO Pro is a next-generation picosecond laser system that delivers ultra-short pulses to shatter pigment particles without damaging surrounding tissue. Combined with FracTAT® technology, it offers unparalleled results in tattoo removal, pigmentation correction and skin revitalisation.",
      zh: "Fotona StarWalker® PICO Pro 是下一代皮秒激光系统，提供超短脉冲来粉碎色素颗粒而不损伤周围组织。结合 FracTAT® 技术，在纹身去除、色素校正和皮肤活化方面提供无与伦比的效果。"
    },
    sections: [
      {
        title: { en: "Treatment Areas", zh: "治疗范围" },
        type: "list",
        items: {
          en: ["Tattoo removal (all colours)", "UV brown spots and sun damage", "Melasma and hyperpigmentation", "Freckle removal", "Skin toning and brightening", "Acne scar improvement"],
          zh: ["纹身去除（所有颜色）", "紫外线褐斑和日光损伤", "黄褐斑和色素沉着", "雀斑去除", "皮肤调理和提亮", "痤疮疤痕改善"]
        }
      },
      {
        title: { en: "Why Pico Laser?", zh: "为什么选择皮秒激光？" },
        type: "list",
        items: {
          en: ["Ultra-short pulse duration (picoseconds)", "Shatters pigment into tiny particles for faster clearance", "Less discomfort than traditional lasers", "Fewer sessions required", "Safe and effective for most skin types", "Minimal risk of scarring or discolouration"],
          zh: ["超短脉冲持续时间（皮秒级）", "将色素粉碎成微小颗粒，更快清除", "比传统激光更少不适", "所需疗程更少", "对大多数皮肤类型安全有效", "疤痕或变色风险极低"]
        }
      }
    ],
    cta: { en: "Book Pico Laser Consultation", zh: "预约皮秒激光咨询" }
  },

  "healite-ii": {
    id: "healite-ii",
    title: { en: "HEALITE II", zh: "Healite II 光疗" },
    subtitle: { en: "LED Phototherapy for Healing & Rejuvenation", zh: "LED 光疗法用于愈合与焕新" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>`,
    color: "#e0f2f1",
    description: {
      en: "Healite II is a non-invasive LED phototherapy system that uses specific wavelengths of light to accelerate healing, reduce inflammation and promote skin rejuvenation. This painless treatment can be used alone or in combination with other procedures to enhance results.",
      zh: "Healite II 是一种非侵入性 LED 光疗系统，使用特定波长的光线加速愈合、减少炎症并促进皮肤焕新。这种无痛治疗可单独使用或与其他程序结合以增强效果。"
    },
    sections: [
      {
        title: { en: "Benefits", zh: "优势" },
        type: "list",
        items: {
          en: ["Accelerates wound healing", "Reduces inflammation and redness", "Stimulates collagen production", "Painless and relaxing treatment", "No downtime", "Enhances results of other treatments"],
          zh: ["加速伤口愈合", "减少炎症和泛红", "刺激胶原蛋白生成", "无痛放松的治疗", "无恢复期", "增强其他治疗效果"]
        }
      }
    ],
    cta: { en: "Book Healite II Session", zh: "预约 Healite II 光疗" }
  },

  "wrinkles-pores": {
    id: "wrinkles-pores",
    title: { en: "WRINKLES & PORES", zh: "皱纹与毛孔" },
    subtitle: { en: "Targeted Treatment for Ageing Skin", zh: "针对老化皮肤的精准治疗" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    color: "#f3e5f5",
    description: {
      en: "Our comprehensive approach to wrinkle and pore treatment combines multiple technologies to address the underlying causes of skin ageing. From laser resurfacing to collagen-stimulating treatments, we develop personalised plans to restore your skin's youthful appearance.",
      zh: "我们针对皱纹和毛孔的综合治疗方案结合多种技术，解决皮肤老化的根本原因。从激光焕肤到胶原蛋白刺激治疗，我们制定个性化方案恢复您皮肤的年轻外观。"
    },
    sections: [
      {
        title: { en: "Treatment Options", zh: "治疗方案" },
        type: "list",
        items: {
          en: ["Fractional laser resurfacing", "Collagen induction therapy", "LED phototherapy", "Dermal enhancement procedures", "Personalised skincare regimens"],
          zh: ["点阵激光焕肤", "胶原蛋白诱导疗法", "LED 光疗", "皮肤焕新程序", "个性化护肤方案"]
        }
      }
    ],
    cta: { en: "Book Wrinkle Treatment", zh: "预约皱纹治疗" }
  },

  "uv-brown-spots": {
    id: "uv-brown-spots",
    title: { en: "UV BROWN SPOTS", zh: "紫外线褐斑" },
    subtitle: { en: "Effective Treatment for Sun-Induced Pigmentation", zh: "有效治疗日晒引起的色素沉着" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><circle cx="12" cy="12" r="5"/><path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`,
    color: "#fff3e0",
    description: {
      en: "UV brown spots (solar lentigines) are caused by cumulative sun exposure. Our advanced laser and light-based treatments effectively target and reduce these pigmented lesions for a more even, youthful complexion.",
      zh: "紫外线褐斑（日光性黑子）由累积性日晒引起。我们先进的激光和光疗有效靶向并减少这些色素病变，使肤色更加均匀年轻。"
    },
    sections: [
      {
        title: { en: "Treatment Options", zh: "治疗方案" },
        type: "list",
        items: {
          en: ["Pico Laser (Fotona StarWalker®)", "IPL photorejuvenation", "Chemical peels", "Prescription skincare"],
          zh: ["皮秒激光 (Fotona StarWalker®)", "IPL 光子嫩肤", "化学焕肤", "处方护肤"]
        }
      }
    ],
    cta: { en: "Book Brown Spot Treatment", zh: "预约褐斑治疗" }
  },

  "spots": {
    id: "spots",
    title: { en: "SPOTS & PIGMENTATION", zh: "色斑与色素沉着" },
    subtitle: { en: "Comprehensive Pigmentation Management", zh: "全面的色素管理" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M12 2a10 10 0 100 20 10 10 0 000-20z"/><circle cx="9" cy="10" r="1.5" fill="#c79323"/><circle cx="14" cy="8" r="1" fill="#c79323"/><circle cx="11" cy="14" r="1.5" fill="#c79323"/><circle cx="16" cy="13" r="1" fill="#c79323"/></svg>`,
    color: "#faf3e0",
    description: {
      en: "Whether caused by sun exposure, hormonal changes or ageing, unwanted pigmentation can be effectively treated with our range of advanced technologies. We assess your specific type of pigmentation to recommend the most appropriate treatment.",
      zh: "无论是由日晒、荷尔蒙变化还是衰老引起的色素沉着，都可以通过我们的一系列先进技术有效治疗。我们评估您特定类型的色素沉着，推荐最合适的治疗方案。"
    },
    sections: [
      {
        title: { en: "Types We Treat", zh: "我们治疗的类型" },
        type: "list",
        items: {
          en: ["Solar lentigines (sun spots)", "Melasma", "Freckles", "Post-inflammatory hyperpigmentation", "Age spots"],
          zh: ["日光性黑子（日晒斑）", "黄褐斑", "雀斑", "炎症后色素沉着", "老年斑"]
        }
      }
    ],
    cta: { en: "Book Pigmentation Consultation", zh: "预约色素咨询" }
  },

  "acne": {
    id: "acne",
    title: { en: "ACNE TREATMENT", zh: "痤疮治疗" },
    subtitle: { en: "Advanced Solutions for Active Acne & Scarring", zh: "活动性痤疮和疤痕的先进解决方案" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M9 10h.01M15 10h.01M9.5 15.5a3.5 3.5 0 005 0"/><circle cx="12" cy="12" r="10"/></svg>`,
    color: "#e8f5e9",
    description: {
      en: "Our multi-modal approach to acne treatment addresses both active breakouts and residual scarring. From PDT for severe acne to laser resurfacing for scars, we provide comprehensive care for all acne concerns.",
      zh: "我们针对痤疮的多模式治疗方案同时解决活动性痤疮和残留疤痕。从重度痤疮的 PDT 治疗到疤痕的激光焕肤，我们为所有痤疮问题提供全面护理。"
    },
    sections: [
      {
        title: { en: "Our Approach", zh: "我们的方案" },
        type: "list",
        items: {
          en: ["VISIA skin analysis for accurate assessment", "PDT for moderate-severe acne", "Healite II LED therapy for inflammation", "Pico Laser for acne scarring", "Personalised skincare protocols"],
          zh: ["VISIA 皮肤分析精确评估", "PDT 治疗中重度痤疮", "Healite II LED 光疗消炎", "皮秒激光治疗痤疮疤痕", "个性化护肤方案"]
        }
      }
    ],
    cta: { en: "Book Acne Consultation", zh: "预约痤疮咨询" }
  },

  "skin-cancer-check": {
    id: "skin-cancer-check",
    title: { en: "SKIN CANCER CHECK", zh: "皮肤癌检查" },
    subtitle: { en: "Early Detection Saves Lives", zh: "早发现拯救生命" },
    icon: `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#c79323" stroke-width="1.5"><path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944m11.658 4.016a11.95 11.95 0 01-2.236 5.166M12 21.056A11.955 11.955 0 012.344 6.96"/><path d="M12 21.056c1.842 0 3.578-.424 5.118-1.18"/></svg>`,
    color: "#e3f2fd",
    description: {
      en: "Regular skin checks are essential for early detection of skin cancer. Our experienced doctors perform thorough examinations using dermoscopy and, when needed, biopsy to ensure accurate diagnosis and timely treatment.",
      zh: "定期皮肤检查对早期发现皮肤癌至关重要。我们的经验丰富的医生使用皮肤镜进行彻底检查，并在需要时进行活检以确保准确诊断和及时治疗。"
    },
    sections: [
      {
        title: { en: "What to Expect", zh: "检查流程" },
        type: "steps",
        steps: [
          { num: 1, title: { en: "Full Body Exam", zh: "全身检查" }, desc: { en: "Complete visual examination of all skin surfaces", zh: "对所有皮肤表面进行完整目视检查" } },
          { num: 2, title: { en: "Dermoscopy", zh: "皮肤镜检查" }, desc: { en: "Magnified analysis of any suspicious lesions", zh: "对可疑病变进行放大分析" } },
          { num: 3, title: { en: "Biopsy (if needed)", zh: "活检（如需要）" }, desc: { en: "Sample taken for laboratory analysis", zh: "取样送实验室分析" } },
          { num: 4, title: { en: "Treatment Plan", zh: "治疗方案" }, desc: { en: "Personalised treatment or monitoring schedule", zh: "个性化治疗或监测计划" } }
        ]
      }
    ],
    cta: { en: "Book Skin Check", zh: "预约皮肤检查" }
  }
};
