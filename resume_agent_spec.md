# 简历 Agent 项目 — 产品与开发完整规范

> 本文档面向首次开发 Agent 的工程师，同时作为交付给 Codex 等代码生成工具的完整上下文。涵盖产品定义、概念入门、技术架构、工具规范、开发流程和验证标准。

---

## 1. 项目背景

### 1.1 比赛与赛道

本项目参加 **Google Cloud Rapid Agent Hackathon**，提交至 **MongoDB 赛道**。截止日期 2026 年 6 月 11 日。

### 1.2 解决的问题

为投递 SWE 实习的国际学生提供一个能够：

- 根据目标 JD 智能调整简历内容
- 自动应用专业排版（多语言、多模板）
- 持久化管理多版本（不同公司、不同岗位）

的 AI Agent。

### 1.3 与简单 LLM 应用的区别

普通 LLM 应用是"输入 → 输出"的一次性交互。本项目是真正的 Agent，原因：

- 多步骤工具链调用（解析 / 匹配 / 验证 / 改写 / 渲染 / 持久化）
- 双层对话循环（澄清循环 + 精修循环）
- LLM 输出自我验证 + 失败重试
- 持久化状态（MongoDB 版本管理 + Session 临时草稿）

### 1.4 比赛要求对齐

| 比赛要求 | 本项目实现 |
|---|---|
| 必须用 Gemini | Agent Builder 内置 Gemini |
| 必须用 Google Cloud Agent Builder | 整个 Agent 在 Agent Builder 中编排 |
| 至少集成一个合作伙伴 MCP | MongoDB Atlas MCP Server |
| Real-world Agent，不是聊天机器人 | 多步骤工具调用 + 双重对话循环 + 自我验证 |
| Human oversight | 用户对每个修改都有最终决定权 |

---

## 2. 核心概念入门

如果你是第一次开发 Agent，请先理解以下五个概念。

### 2.1 Agent 是什么

Agent 本质上是一个**带工具的 LLM 循环**：

```
loop:
    LLM 观察当前状态
    LLM 决定下一步:
      - 调用某个工具 → 执行 → 把结果作为新观察 → 回到 loop
      - 直接回复用户 → 等待用户下一条消息
      - 任务结束 → 退出
```

让 LLM 变成 Agent 的关键不是模型本身，而是**给它工具，并让它在循环里反复决策**。

### 2.2 Tool（工具）是什么

Tool 是 Agent 可以调用的功能，通常是一个函数。每个 Tool 需要：

- **名字**：Agent 用它来引用工具（如 `parse_resume`）
- **描述**：告诉 Agent 什么场景该用这个工具
- **输入 schema**：JSON Schema 定义参数
- **输出 schema**：JSON Schema 定义返回值
- **实现**：实际执行的代码（可能是本地函数、HTTP endpoint，或 MCP Server）

Agent 看到用户请求时，根据每个工具的描述判断该不该调用、传什么参数。

### 2.3 MCP（Model Context Protocol）是什么

MCP 是一个让 AI 调用外部服务的**标准协议**。可以类比为"AI 世界的 REST API 标准"。任何服务（数据库、SaaS、内部系统）只要实现一个 MCP Server，所有支持 MCP 的 AI 框架就能调用它。

**关键好处**：你不需要为 MongoDB 写适配器代码。MongoDB 官方已经提供了 MCP Server，你启动它、注册给 Agent Builder，Agent 就能用了。

### 2.4 Google Cloud Agent Builder 是什么

Google Cloud 提供的 **Agent 编排平台**。通过 Web UI 或配置文件定义：

- Agent 的 system prompt
- Agent 可以使用的工具（自定义 + MCP）
- Agent 的部署方式（API endpoint）

Agent Builder 负责跑那个循环——你不需要自己写 "while + 工具调用 + 状态管理"。

### 2.5 Gemini 是什么

Google 的大语言模型，作为 Agent 的"大脑"。**你不直接调用 Gemini API**，而是通过 Agent Builder 间接使用。

### 2.6 它们如何协同

```
用户请求
   ↓
Streamlit 前端（你写的 Python UI）
   ↓
Agent Builder Agent Endpoint（你部署的）
   ↓
Agent Builder 内部循环：
   Gemini 决定调用某个工具
   ↓
   Agent Builder 路由请求：
     - 自定义工具 → 你的 FastAPI 服务
     - MCP 工具    → MongoDB MCP Server
   ↓
   返回结果给 Gemini，进入下一轮
   ↓
   Gemini 决定回复用户
   ↓
返回给 Streamlit 展示
```

---

## 3. 产品功能详细说明

### 3.1 核心功能（MVP 必做）

#### F1. 多格式简历输入

- **支持**：PDF 上传、纯文本粘贴
- **架构预留**：Word、LaTeX（不在 MVP 实现，但 schema 兼容）
- **统一处理**：所有输入先转纯文本，再由 LLM 提取结构化字段

#### F2. 简历内容解析

输出标准化的 **ResumeJSON** 结构，提取字段包括：

- 个人信息（姓名、邮箱、电话、LinkedIn、GitHub、地点）
- 教育经历（学校、学位、专业、GPA、起止时间）
- 工作/实习经历（公司、职位、地点、起止时间、bullet 描述）
- 项目经历（项目名、技术栈、起止时间、bullet 描述）
- 技能（按类别分组）
- 其他（证书、获奖等）

每个 bullet、experience、project 自动生成 UUID，便于后续引用和修改。

#### F3. JD 匹配分析

用户粘贴 JD，Agent 分析并输出：

- **整体匹配度评分**（0-100）
- **关键词覆盖**：JD 提到的技术词中，简历覆盖了哪些、缺了哪些
- **经历相关性**：每段经历对该 JD 的相关度
- **改进建议清单**：按 impact 排序的具体修改建议

#### F4. 澄清对话循环（Loop 1）

Agent 在给出初步建议后，主动追问以挖掘信息：

- "想要弱化这段经历还是多做文章？"
- "这个项目有没有可量化的数据可以加进去？"
- "你的简历里还有没有 hidden strength 没体现？"

**关键原则**：
- 用户随时可以说"够了，按当前建议改"退出循环
- Agent 不强求所有问题都被回答
- 默认 Agent 只提建议，不主动修改

#### F5. 建议选择

将所有建议（初始 + 澄清产生的）列出，用户用 checkbox 选择要应用哪些。未勾选的保持原样。

#### F6. 应用 + 精修循环（Loop 2）

Agent 应用选中建议，生成 Working Draft，展示给用户。用户可继续：

- "这条 bullet 再改得更具体"
- "把项目经历调到工作经历之前"
- "加一段开源贡献"

Agent 更新 Working Draft（**不写入数据库**）。循环持续到用户明确说"保存"。

#### F7. 模板选择与渲染

- 用户从预定义模板中选择
- Agent 将 ResumeJSON 注入模板 → 生成 HTML → 转 PDF
- 用户预览 / 下载

#### F8. 版本保存（显式提交）

用户主动点击"保存"才将 Working Draft 提交到 MongoDB。保存时填写：公司、岗位、备注等标签。一旦保存就是不可变 snapshot。

#### F9. 历史版本列表

用户可查看所有保存过的版本，按时间或标签筛选/排序。

#### F10. 版本加载与对比

- **加载**：选中某个历史版本 → 加载到 Working Draft → 可继续修改
- **对比**：选中两个版本 → Agent 分析差异 → 文字总结哪些 bullet 变了

### 3.2 不在 MVP（写入 Devpost Future Work）

- Word、LaTeX 输入支持
- 更多模板（不同行业、不同语言）
- AI 窗口与编辑窗口分离（用户直接编辑字段）
- 协作功能（导师/朋友评论）

---

## 4. 技术栈

### 4.1 核心平台

| 组件 | 用途 |
|---|---|
| Google Cloud Agent Builder | Agent 编排与部署 |
| Gemini（内置） | LLM 引擎 |
| MongoDB Atlas | 持久化存储（免费 tier） |
| MongoDB MCP Server | Agent 与 MongoDB 之间的桥梁 |

### 4.2 后端

- **语言**：Python 3.11
- **Web 服务**：FastAPI（暴露自定义工具为 HTTP endpoint）
- **简历解析**：
  - `pdfplumber` — PDF 解析
  - `python-docx` — Word 解析（架构预留，MVP 不启用）
- **模板渲染**：
  - `jinja2` — HTML 模板渲染
  - `playwright` — HTML → PDF（推荐）
  - 备选：`weasyprint`（纯 Python，无需浏览器）
- **验证**：
  - `pyyaml` — 加载规则配置
  - `pydantic` — 数据模型验证

### 4.3 前端

- **框架**：Streamlit
- **布局**：左右双栏（左对话区，右简历预览，顶部模板/保存）

### 4.4 部署

- **本地开发**：所有服务在本地跑，足够录 demo
- **可选加分项**：FastAPI 部署到 Google Cloud Run

---

## 5. 系统架构

### 5.1 组件视图

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit 前端                       │
│  (左:对话区  |  右:简历预览  |  顶:模板/保存)         │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP
                   ▼
┌─────────────────────────────────────────────────────┐
│         Agent Builder Agent Endpoint                 │
│  ┌───────────────────────────────────────────────┐  │
│  │              Gemini (决策引擎)                 │  │
│  └───────────────┬───────────────────────────────┘  │
│                  │ 工具调用                          │
│  ┌───────────────┴───────────────┐                  │
│  ▼                               ▼                  │
└──┼───────────────────────────────┼──────────────────┘
   │                               │
   │ 自定义工具(HTTP)               │ MCP 协议
   ▼                               ▼
┌──────────────────┐         ┌──────────────────┐
│ FastAPI 服务      │         │ MongoDB MCP      │
│ - parse_resume    │         │ Server           │
│ - analyze_match   │         └────────┬─────────┘
│ - rewrite_bullet  │                  │
│ - check_format    │                  ▼
│ - render_template │         ┌──────────────────┐
└──────────────────┘         │ MongoDB Atlas     │
                              └──────────────────┘
```

### 5.2 数据流（一个完整交互）

1. 用户在 Streamlit 上传简历 + 粘贴 JD + 点"开始分析"
2. Streamlit 调用 Agent endpoint，传入用户消息和 session_id
3. Agent (Gemini) 决定先调 `parse_resume`
4. Agent Builder 将请求路由到 FastAPI，FastAPI 解析后返回 ResumeJSON
5. Agent 决定调 `analyze_jd_match`，传入 ResumeJSON 和 JD
6. FastAPI 返回匹配度评分和建议清单
7. Agent 决定回复用户："这是分析结果，有几个问题想问你..."
8. Streamlit 接收回复并显示
9. 用户回答 → Streamlit 再次调 Agent endpoint → ... 循环

---

## 6. 数据模型

### 6.1 MongoDB Collections

#### `users`

```json
{
  "_id": "ObjectId",
  "user_id": "string",
  "created_at": "ISO datetime",
  "preferences": {
    "default_template": "string",
    "default_language": "en | zh"
  }
}
```

#### `resume_versions`

```json
{
  "_id": "ObjectId",
  "version_id": "string (UUID)",
  "user_id": "string",
  "tags": {
    "company": "string",
    "role": "string",
    "notes": "string"
  },
  "content": "ResumeJSON",
  "template_name": "string",
  "jd_text": "string",
  "match_score": "number",
  "validation_summary": {
    "passed": "boolean",
    "violations": ["string"]
  },
  "rendered_pdf_url": "string",
  "created_at": "ISO datetime"
}
```

### 6.2 ResumeJSON 结构

```json
{
  "language": "en | zh",
  "personal_info": {
    "name": "string",
    "email": "string",
    "phone": "string",
    "links": {
      "linkedin": "string",
      "github": "string",
      "website": "string"
    },
    "location": "string"
  },
  "education": [
    {
      "id": "UUID",
      "school": "string",
      "degree": "string",
      "major": "string",
      "gpa": "string",
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM | Present",
      "location": "string",
      "details": ["string"]
    }
  ],
  "experience": [
    {
      "id": "UUID",
      "company": "string",
      "role": "string",
      "location": "string",
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM | Present",
      "bullets": [
        {
          "id": "UUID",
          "content": "string",
          "validation": {
            "passed": "boolean",
            "checks": {
              "has_action_verb": "boolean",
              "has_quantification": "boolean",
              "within_length": "boolean"
            }
          }
        }
      ]
    }
  ],
  "projects": [
    {
      "id": "UUID",
      "name": "string",
      "tech_stack": ["string"],
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM | Present",
      "bullets": "[与 experience 相同结构]"
    }
  ],
  "skills": {
    "languages": ["string"],
    "frameworks": ["string"],
    "tools": ["string"],
    "other": ["string"]
  },
  "additional": {
    "certifications": ["string"],
    "awards": ["string"],
    "publications": ["string"]
  }
}
```

### 6.3 Streamlit Session State

```python
st.session_state = {
    "session_id": str,
    "current_draft": ResumeJSON,        # 当前编辑中
    "original_resume": ResumeJSON,      # 用户上传的原始版本
    "jd_text": str,
    "match_analysis": dict,
    "suggestions": [
        {
            "id": str,
            "description": str,
            "target": str,              # bullet_id 或 section name
            "type": str,                # rewrite | reorder | add | remove
            "impact_score": int,
            "selected_by_user": bool
        }
    ],
    "selected_template": str,
    "conversation_history": [
        {"role": str, "content": str, "timestamp": str}
    ],
    "validation_status": dict
}
```

---

## 7. 工具规范

### 7.1 自定义工具（你需要实现）

#### Tool 1: parse_resume

**用途**：将原始简历解析为 ResumeJSON

**输入**：
```json
{
  "raw_text": "string",
  "source_format": "pdf | text | docx | latex"
}
```

**输出**：
```json
{
  "resume_json": "ResumeJSON",
  "parse_warnings": ["string"]
}
```

**实现要点**：
- PDF 输入先用 `pdfplumber` 提取文本
- 提取结构化字段使用 LLM（在 FastAPI 内部调用，或交由 Agent Builder 处理）
- 为每个 bullet、experience、project、education 生成 UUID
- 解析失败的字段返回 null + warning
- **不在此处做内容质量检查**

#### Tool 2: analyze_jd_match

**用途**：分析简历与 JD 的匹配度，生成建议清单

**输入**：
```json
{
  "resume_json": "ResumeJSON",
  "jd_text": "string"
}
```

**输出**：
```json
{
  "match_score": "number",
  "keyword_coverage": {
    "covered": ["string"],
    "missing": ["string"]
  },
  "experience_relevance": [
    {"experience_id": "string", "score": "number", "reason": "string"}
  ],
  "suggestions": [
    {
      "id": "string",
      "description": "string",
      "target": "string",
      "type": "rewrite | reorder | add | remove | quantify",
      "impact_score": "number"
    }
  ]
}
```

**实现要点**：
- 关键词提取由 LLM 完成
- 经历相关性基于语义相似度
- 建议按 impact_score 降序

#### Tool 3: check_formatting

**用途**：对 ResumeJSON 执行硬规则检查（**用户输入和 Agent 输出都调用**）

**输入**：
```json
{
  "resume_json": "ResumeJSON",
  "template_name": "string (可选)"
}
```

**输出**：
```json
{
  "passed": "boolean",
  "violations": [
    {
      "rule_id": "string",
      "severity": "error | warning",
      "target": "string",
      "message": "string",
      "suggestion": "string"
    }
  ]
}
```

**规则配置**（`config/structure_rules.yaml`）示例：

```yaml
rules:
  - id: max_page_count
    severity: error
    description: 简历不应超过 1 页
    estimated_chars_per_page: 3500

  - id: consistent_date_format
    severity: error
    description: 所有日期使用统一格式

  - id: required_sections
    severity: error
    required: [personal_info, education]

  - id: max_bullets_per_experience
    severity: warning
    max: 5

  - id: min_bullets_per_experience
    severity: warning
    min: 2
```

#### Tool 4: rewrite_bullet

**用途**：改写一条 bullet，**内部包含 3 次重试的验证循环**

**输入**：
```json
{
  "original_bullet": "string",
  "instruction": "string",
  "context": {
    "experience_role": "string",
    "tech_stack": ["string"],
    "jd_text": "string"
  }
}
```

**输出**：
```json
{
  "new_bullet": "string",
  "validation": {
    "passed": "boolean",
    "checks": {
      "has_action_verb": "boolean",
      "has_quantification": "boolean",
      "within_length": "boolean"
    }
  },
  "attempts": "number",
  "warning": "string"
}
```

**实现伪代码**：

```python
MAX_RETRIES = 3

def rewrite_bullet(original, instruction, context):
    for attempt in range(MAX_RETRIES):
        new_bullet = llm.generate(
            prompt_for_rewrite(original, instruction, context)
        )
        validation = check_bullet_rubric(new_bullet)
        if validation["passed"]:
            return {
                "new_bullet": new_bullet,
                "validation": validation,
                "attempts": attempt + 1
            }
        # 把 violations 加入下一轮 instruction
        instruction = f"{instruction}. Address: {validation['violations']}"

    return {
        "new_bullet": new_bullet,  # 返回最近一版
        "validation": validation,
        "attempts": MAX_RETRIES,
        "warning": "Could not fully meet rubric after 3 attempts"
    }
```

#### Tool 5: render_template

**用途**：将 ResumeJSON 渲染为 PDF

**输入**：
```json
{
  "resume_json": "ResumeJSON",
  "template_name": "string",
  "output_format": "pdf | html"
}
```

**输出**：
```json
{
  "file_url": "string",
  "html_preview": "string"
}
```

**实现伪代码**：

```python
def render_template(resume_json, template_name, output_format):
    template = load_template(template_name)
    html = jinja_env.from_string(template).render(resume=resume_json)

    if output_format == "html":
        return {"html_preview": html, "file_url": None}

    pdf_path = f"/tmp/{uuid.uuid4()}.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.pdf(path=pdf_path, format="Letter")
        browser.close()

    return {"file_url": pdf_path, "html_preview": html}
```

#### Tool 6: compare_versions

**用途**：对比两个简历版本

**输入**：
```json
{
  "version_a_id": "string",
  "version_b_id": "string"
}
```

**输出**：
```json
{
  "summary": "string",
  "diff": {
    "modified_bullets": [
      {"before": "string", "after": "string", "section": "string"}
    ],
    "added": ["string"],
    "removed": ["string"],
    "reordered": ["string"]
  }
}
```

### 7.2 MongoDB MCP 工具（不需自己实现）

由 MongoDB MCP Server 提供：

- `mongodb.save_document(collection, document)` → version_id
- `mongodb.find_documents(collection, filter)` → documents list
- `mongodb.get_document(collection, id)` → document
- `mongodb.delete_document(collection, id)` → success status

直接在 Agent Builder 中注册 MongoDB MCP，Gemini 自动看到这些工具。

---

## 8. 验证框架

**核心原则**：LLM 输出必须经过验证，规则同时作用于输入和输出。

### 8.1 三层规则体系

| 层级 | 内容 | 实现方式 |
|---|---|---|
| **视觉层** | 字体、margin、行距、颜色 | 模板 CSS 编码 |
| **结构层** | 一页、section 顺序、字段完整性 | Python 函数硬检查 |
| **内容层** | bullet 用词、量化程度、专业度 | LLM 用 rubric 判断 |

### 8.2 内容 Rubric 示例（`config/rubric.yaml`）

```yaml
bullet_quality:
  starts_with_action_verb:
    weight: high
    good: [Built, Designed, Implemented, Reduced, Led, Optimized, Architected]
    bad: ["Worked on", "Helped with", "Was responsible for", "Assisted in"]

  has_quantification:
    weight: high
    description: 包含数字、百分比、规模指标
    examples:
      good: "Reduced API latency by 30% through Redis caching"
      bad: "Improved API performance"

  specificity:
    weight: medium
    description: 提到具体技术、工具、方法
    examples:
      good: "Trained ResNet-50 on 50k images, achieving 94% accuracy"
      bad: "Did machine learning project"

  length:
    weight: low
    target_lines: 1-2
    max_chars: 180
```

### 8.3 验证循环模式

```
LLM 生成 → 验证
            ↓
       不达标 → 把 violations 反馈给 LLM → 重新生成（最多 3 次）
            ↓
       达标 → 输出

3 次仍不达标 → 返回最佳尝试 + warning
              ↓
       Agent 转化为对用户的追问
```

### 8.4 应用场景

- `rewrite_bullet` 内部自动循环（硬约束）
- Agent 应用所有建议后主动调 `check_formatting` 全量验证（软约束）
- Agent 看到 warning 时，转化为澄清问题给用户

---

## 9. 模板系统

### 9.1 MVP 模板

| 名称 | 语言 | 风格 | 用途 |
|---|---|---|---|
| `jakes_resume_en` | 英文 | 单栏简洁 | SWE 实习投递主推 |
| `simple_modern_zh` | 中文 | 双栏现代 | 国内/中文岗位 |

### 9.2 模板目录结构

```
config/templates/
├── jakes_resume_en/
│   ├── template.html      # Jinja2 模板
│   ├── styles.css         # 视觉样式
│   └── meta.yaml          # 模板元信息
└── simple_modern_zh/
    ├── template.html
    ├── styles.css
    └── meta.yaml
```

### 9.3 meta.yaml 示例

```yaml
name: jakes_resume_en
display_name: "Jake's Resume (English)"
language: en
description: "Classic single-column LaTeX-style resume, popular among CS students"
target_pages: 1
font_family: "Latin Modern Roman"
font_size: 10pt
recommended_for: ["SWE internship", "PhD application"]
required_sections: [personal_info, education, experience]
optional_sections: [projects, skills, additional]
max_bullets_per_section: 4
```

---

## 10. 开发步骤流程

### Day 0：环境准备（必须先完成）

- [ ] 注册 Google Cloud 账号，开通 Agent Builder（可能需等待审批）
- [ ] 注册 MongoDB Atlas，创建免费 cluster，拿到 connection string
- [ ] 安装 Python 3.11、Node.js（MongoDB MCP 可能需要）
- [ ] 安装 Playwright + 浏览器：`playwright install chromium`
- [ ] 创建项目仓库，设置 `.gitignore`、虚拟环境

**requirements.txt**：

```
fastapi>=0.110.0
uvicorn>=0.27.0
pdfplumber>=0.10.0
python-docx>=1.1.0
jinja2>=3.1.0
playwright>=1.41.0
pyyaml>=6.0
pydantic>=2.6.0
streamlit>=1.32.0
pymongo>=4.6.0
python-multipart>=0.0.9
google-cloud-aiplatform>=1.42.0
```

### Day 1：跑通最小回路

**目标**：证明 Agent Builder 能调用自定义工具，能调用 MongoDB MCP

**任务**：
1. 启动 MongoDB MCP Server
2. 在 Agent Builder 创建一个 "hello world" Agent
3. 写一个最简 FastAPI endpoint `/echo`，注册为工具
4. 在 Agent Builder 注册 MongoDB MCP
5. 在 Playground 测试：让 Agent 调 `/echo`，再让 Agent 调 `mongodb.save_document` 存数据

**验收**：能在 MongoDB Atlas 后台看到 Agent 通过 MCP 写入的数据

### Day 2：实现 parse_resume

**任务**：
1. 写 `tools/parse_resume.py`
2. 用 `pdfplumber` 提取 PDF 文本
3. 设计 prompt 让 LLM 提取结构化字段
4. 输出 ResumeJSON
5. 暴露为 FastAPI endpoint
6. 用 3-5 份真实简历测试

**验收**：能正确提取你自己简历的所有字段

### Day 3：实现模板渲染

**任务**：
1. 写 `tools/render_template.py`
2. 创建 `templates/jakes_resume_en/`，参考 Jake's Resume 原版
3. 测试：传入测试 ResumeJSON，输出 PDF
4. 暴露为 FastAPI endpoint

**验收**：生成的 PDF 视觉效果接近 Jake's Resume 原版

### Day 4：实现 check_formatting 和 rubric

**任务**：
1. 写 `config/structure_rules.yaml`，至少 10 条规则
2. 写 `config/rubric.yaml`，bullet quality 标准
3. 写 `tools/check_formatting.py`
4. 写 `tools/check_bullet_rubric.py`（被 rewrite_bullet 内部调用）

**验收**：对一份故意写差的简历，能正确报告所有 violations

### Day 5：实现 analyze_jd_match 和 rewrite_bullet

**任务**：
1. 写 `tools/analyze_jd_match.py`
2. 写 `tools/rewrite_bullet.py`，**包含 3 次重试的验证循环**
3. 全部暴露为 FastAPI endpoints

**验收**：
- 给定简历和 JD，能生成 5-8 条具体建议
- rewrite_bullet 能成功改写一条弱 bullet

### Day 6：Agent Builder 配置完整 Agent

**任务**：
1. 写 Agent system prompt（见 §11）
2. 在 Agent Builder 注册所有自定义工具
3. 确保 MongoDB MCP 已注册
4. 在 Playground 完整测试端到端流程

**验收**：不带 UI，Playground 内能跑通完整流程

### Day 7-8：前端 Streamlit 开发

**任务**：
1. 写 `frontend/app.py`
2. 实现双栏布局
3. 实现文件上传、JD 输入
4. 实现对话区（连接 Agent endpoint）
5. 实现简历预览区
6. 实现模板选择、保存版本表单
7. 实现历史版本列表 + 加载 + 对比

**验收**：用户能在浏览器里完成所有 Demo 操作

### Day 9：整合 + Happy Path 调试

**任务**：
1. 完整跑 demo 场景 3 遍
2. 修复 prompt 问题、UI 卡顿、边界 case
3. 优化 Agent 对话流畅度
4. 录制初版 demo 视频自我检查

**验收**：3 分钟内能流畅演示所有核心功能

### Day 10：录制 Demo 视频

1. 写视频脚本
2. 录制 + 剪辑
3. 加字幕、配旁白

### Day 11：Devpost 提交材料

1. 写项目描述
2. 整理 GitHub repo，加 MIT License、README、架构图
3. 截图配图
4. 视频上传到 YouTube

### Day 12：缓冲日

预留时间应对意外。所有材料在截止前提交完毕。

---

## 11. Agent System Prompt

```
You are a resume editing assistant specialized in helping SWE internship candidates
tailor their resumes to specific job descriptions. You follow a structured workflow.

PHASE 1 — INTAKE
When the user provides a resume and a target JD:
1. Call parse_resume to extract structured content
2. Call analyze_jd_match to compute fit and suggestions
3. Present the match score and top suggestions to the user
4. DO NOT modify the resume yet

PHASE 2 — CLARIFICATION LOOP
Ask clarifying questions to surface hidden information:
- "I notice this experience could benefit from quantification — do you have any
   metrics on impact, scale, or performance?"
- "This experience seems less aligned with the JD — would you like to downplay it?"
- "Are there projects or contributions not on your resume that could strengthen it?"

EXIT this loop when:
- User explicitly says they're ready to apply changes
- User expresses urgency ("just apply what you have")
- All open clarification questions are addressed

PHASE 3 — APPLY
1. Present the final consolidated suggestion list with checkboxes
2. Wait for user selection
3. For each selected suggestion, call the appropriate tool (rewrite_bullet, etc.)
4. Each tool internally validates and retries up to 3 times
5. After all suggestions are applied, call check_formatting on the full draft
6. Show the working draft to the user

PHASE 4 — REFINEMENT LOOP
The user can request further changes on the working draft:
- "Make this bullet more specific"
- "Move projects above experience"
- "Add a section for open source contributions"

EXIT this loop only when the user explicitly says they want to save.

PHASE 5 — SAVE
1. Prompt user for tags (company, role, optional notes)
2. Call mongodb.save_document to persist the version
3. Call render_template to produce final PDF
4. Provide download link

GUIDING PRINCIPLES
- Never auto-apply changes without user selection
- Respect urgency: if user wants to ship, don't insist on more iteration
- Be specific in feedback (cite which bullet, which JD keyword)
- When in doubt, ask rather than assume
- Acknowledge limitations ("I tried to add quantification but the original
  doesn't have data — can you provide any?")

AVAILABLE TOOLS
- parse_resume(raw_text, source_format)
- analyze_jd_match(resume_json, jd_text)
- check_formatting(resume_json, template_name?)
- rewrite_bullet(original_bullet, instruction, context)
- render_template(resume_json, template_name, output_format)
- compare_versions(version_a_id, version_b_id)
- mongodb.save_document(collection, document)
- mongodb.find_documents(collection, filter)
- mongodb.get_document(collection, id)

For each user message, decide:
1. Which phase are we in?
2. What is the appropriate next action?
3. Which tool (if any) to call?
```

---

## 12. Demo 视频脚本（3 分钟）

| 时间 | 内容 |
|---|---|
| 0:00 - 0:20 | 痛点开场：屏幕显示几份格式混乱的简历，旁白讲投实习的痛苦 |
| 0:20 - 0:35 | 打开应用 → 上传简历 PDF + 粘贴 Google Backend SWE Intern JD |
| 0:35 - 1:00 | Agent 显示分析：匹配度 72%，列出 8 条建议 |
| 1:00 - 1:30 | 澄清对话循环：Agent 问 ResNet 项目数据 → 用户答 "94% accuracy, 50k images" → Agent 问 Heap allocator 量化 → 用户答 "reduced fragmentation by 18%" |
| 1:30 - 1:50 | 用户勾选要应用的建议 → Agent 改写 → 显示 working draft |
| 1:50 - 2:15 | 精修循环：用户 "把项目经历移到工作经历前面" → Agent 调整。用户 "这条 bullet 再具体些" → Agent 改写 |
| 2:15 - 2:30 | 用户 "好了，保存" → 填标签 "Google Backend SWE Intern 2026" → 保存到 MongoDB（屏幕显示 Atlas 后台数据写入） |
| 2:30 - 2:55 | 切换场景：投 Meta ML 岗 → 调出历史版本 → 重新分析 → 对比两版差异 |
| 2:55 - 3:00 | 收尾：展示版本列表，强调持续可管理 |

---

## 13. 项目文件结构

```
resume-agent/
├── README.md
├── requirements.txt
├── .gitignore
├── LICENSE
├── config/
│   ├── structure_rules.yaml
│   ├── rubric.yaml
│   └── templates/
│       ├── jakes_resume_en/
│       │   ├── template.html
│       │   ├── styles.css
│       │   └── meta.yaml
│       └── simple_modern_zh/
│           ├── template.html
│           ├── styles.css
│           └── meta.yaml
├── tools/
│   ├── __init__.py
│   ├── parse_resume.py
│   ├── analyze_jd_match.py
│   ├── check_formatting.py
│   ├── check_bullet_rubric.py
│   ├── rewrite_bullet.py
│   ├── render_template.py
│   └── compare_versions.py
├── server/
│   ├── main.py             # FastAPI 入口
│   ├── routes.py           # 工具 endpoints
│   └── schemas.py          # Pydantic 数据模型
├── agent/
│   ├── system_prompt.txt
│   └── agent_config.yaml   # Agent Builder 配置
├── frontend/
│   ├── app.py              # Streamlit 入口
│   ├── components/
│   │   ├── chat_panel.py
│   │   ├── resume_preview.py
│   │   └── version_history.py
│   └── client.py           # 调 Agent endpoint
├── tests/
│   ├── test_parse_resume.py
│   ├── test_check_formatting.py
│   └── fixtures/
│       └── sample_resumes/
└── docs/
    ├── architecture.md
    └── demo_script.md
```

---

## 14. 风险与应对

| 风险 | 应对 |
|---|---|
| Google Cloud Agent Builder 审批延迟 | Day 0 立即申请，备用方案用 Python SDK 直接跑 Gemini + 手写循环 |
| MongoDB MCP Server 配置复杂 | 提前阅读官方文档，Day 1 先把这个跑通 |
| 简历解析准确率低 | 准备 5 份不同风格简历做测试集，prompt 迭代 |
| Playwright 环境问题 | 备用 WeasyPrint（纯 Python，不需要浏览器） |
| 时间紧 | 把"中文模板"、"Word 输入"放 future work，先保 happy path |

---

## 15. 提交清单

提交前确认：

- [ ] GitHub repo 公开，含 MIT License、README、架构图
- [ ] Demo 视频 3 分钟以内，上传到 YouTube
- [ ] 项目可访问 URL（部署或本地启动指令）
- [ ] Devpost 表单填写完整：项目描述、技术栈、团队成员、视频链接、repo 链接
- [ ] 在 **MongoDB 赛道**提交

---

## 16. 关键技术能力清单

完成本项目你将掌握：

1. **Agent 开发**：理解 Agent 循环、工具调用、状态管理
2. **MCP 协议**：使用 MCP Server 简化外部服务集成
3. **Google Cloud Agent Builder**：配置和部署生产级 Agent
4. **LLM 提示工程**：写 system prompt、设计 rubric、控制 LLM 输出
5. **LLM 输出验证**：guard rails、validation loop、graceful failure
6. **FastAPI**：暴露工具为 HTTP endpoint
7. **MongoDB + MCP**：通过 MCP 操作数据库
8. **Streamlit**：快速构建 AI 应用前端
9. **HTML/CSS + Playwright**：动态生成 PDF
10. **PDF 解析**：从结构化和非结构化文档提取信息
