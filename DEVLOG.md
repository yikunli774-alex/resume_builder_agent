# 工程日志 / DEVLOG

记录踩过的坑、做过的技术决策、待解决的疑问。
代码改动看 git，应该做什么看 ASSIGNMENT.md / spec —— 这里只记「为什么」和「教训」。

---

## 2026-05-31 ~ 06-01 — Task 1-5 实现

### 踩坑：MongoDB 连不上，报 `'X509' object has no attribute 'get_extension'`
- **现象**：`save_resume_version` 测试时 `ServerSelectionTimeoutError`，连 Atlas 30s 超时。
- **原因**：`service_identity` 还是 2018 年的 18.1.0，它调用了新版 `pyOpenSSL` 已经删掉的 `X509.get_extension` 方法。不是我的代码错。
- **解法**：`python -m pip install --upgrade service_identity`（18.1.0 → 26.1.0）。
- **教训**：Python 的 TLS/SSL 报错，十有八九是依赖版本互相打架，先查包版本，别急着改自己的代码。

### 踩坑：mongo_tools 集合名拼错
- `save` 写进 `"resume_vesion"`（漏字母、单数），但 `list`/`load` 读 `"resume_versions"` → 存了读不出。
- 已统一成 `"resume_versions"`。

### 决策：Gemini 返回的 JSON 老被 markdown 代码块包裹，`json.loads` 解析失败
- 两个方案：A) 给模型加 `response_mime_type="application/json"`（治本）；B) 字符串剥掉 ```` ```json ```` 外壳（治标）。
- **选了 A**，输出就是干净 JSON，解析代码不用动。

### 决策：suggestion 排序不靠模型，靠代码
- 模型即使被要求「按 impact_score 降序」也经常不照做。
- 在代码里 `.sort(key=..., reverse=True)` 兜底，确定性逻辑不该交给模型。

### 踩坑：playwright 装了包还跑不起来
- `pip install playwright` 之后还要 `python -m playwright install chromium` 下载浏览器本体（类似 Selenium 要 driver）。

### 环境教训：必须用 `python -m pip`，不能用裸 `pip`
- 裸 `pip` 和 `/opt/anaconda3/bin/python` 不是同一个环境，包会装错地方。

### check_formatting 的边界处理（Task 5）
- 用 `.get(k, default)` 而不是 `obj[k]`，缺字段不崩。
- 最外层包一个 try/except 兜畸形输入，返回 `internal_error`，但每条规则内部独立，避免一条炸了后面全不跑。

---

## 2026-06-01 — Task 6 `rewrite_bullet.py` 完成

### 模式：Generator-Validator（生成-校验自我修正循环）
- `rewrite_bullet` 调 Gemini 生成 → `_check_bullet_rubric` 纯代码校验 → 不过就把 violations 追加进下一轮 prompt，最多 MAX_RETRIES(3) 次，成功立即 return。
- **为什么不是低效**：① 校验是本地代码不花 LLM call ② 成功即退出，实测好 bullet attempts=1（不是 3）③ 粒度是单句不是整篇。3 是上限不是常态。
- 实测：`"Helped with search feature"` → `"Optimized search ... by 15%"`，attempts=1，一次过。

### 踩坑：action verb 检查对标点太脆
- `bullet.split()[0]` 拿到的首词可能带标点（`"-"`、`"Reduced,"`、`'"Reduced'`），跟 ACTION_VERBS 永远不相等 → 误判"没动词" → 逼出无谓重试。
- **解法**：比对前 `re.sub(r"[^a-zA-Z]", "", word)` 把非字母剥掉。

### 决策：用 yaml 驱动 bad 短语检查
- 新增 `no_weak_phrase` 检查，从 rubric.yaml 读 `bad` 列表（"Worked on"/"Responsible for"…），剥前导符号后看开头是否弱短语。
- `_load_bad_phrases()` 包 try/except，读不到就退化空表，不连累其他检查（同 check_formatting 兜底思路）。
- 顺带让 `yaml` / `RUBRIC_PATH` 两个原本的死 import 派上用场。

### 待定：rubric 的 has_quantification 是硬性要求
- 不可量化的 bullet（如 "Collaborated with design team on UX"）3 次都加不出真实数字 → 必然跑满 3 次且最终标记失败。有 MAX_RETRIES 兜底不会死循环，但浪费 call。
- 是否放宽（"有数字 **或** 有具体技术名"就算过）是产品决策，待定。

### 架构理解：工具入参由 Gemini 生成、ADK 递送
- `original_bullet`/`instruction`/`context` 在代码里从未被赋值——它们是 Gemini 运行时按 docstring「填表」生成、由 ADK 框架传进函数的。docstring = 给 Gemini 的工具说明书。
- 注意区分两个 `instruction`：`LlmAgent(instruction=)` 是 agent 系统提示；`rewrite_bullet(instruction=)` 是单次调用参数。同名不同物。

---

## 2026-06-03 — Task 7 `compare_versions.py` + Task 8 注册工具

### Task 7：版本对比
- 加载两个版本 → 拼 prompt → Gemini 输出结构化 diff（summary + modified/added/removed/reordered）。
- **优化：相同 id 提前返回**。`if version_a_id == version_b_id` 直接返回空 diff，连数据库和 LLM 都不碰——省一次无谓 prompt（同 rewrite 的 early-exit 思路）。
- **测试避坑**：一开始用两个相同 id 测，必然得「identical」=假阳性，没验证到 diff 主路。改用 v1(只有名字) vs v2(补邮箱+地址+一段 experience+2 条 bullet) 真测，Gemini 准确列出 5 条 added，diff 逻辑确认可用。

### 踩坑：Vertex 初始化报 403 Cloud Resource Manager API disabled
- SDK 想把 project 编号转 project ID，去调 cloudresourcemanager API，没启用 → 打印一大段 403 红字。
- **但无害**：`.env` 已直接给了 `GOOGLE_CLOUD_PROJECT`，SDK 兜底继续跑，结果照常返回。
- 根治（可选）：`gcloud services enable cloudresourcemanager.googleapis.com`。不治也不影响功能。

### Task 8：agent.py 注册
- 9 个工具函数直接传函数对象进 `tools=[]`（不用包装），加上 2 个 sub-agent(Google Search/URL context) = 共 11 个。
- 验收脚本输出 Total: 11 ✅。至此 docstring→Gemini 工具说明书的闭环真正接通。

---

## 2026-06-03 — Task 9 `adk web` 联调踩坑

### 模型选择：编排器 pro vs flash 的权衡
- 三个 agent 初始都是 `gemini-2.5-pro` → 单次 LLM 调用 13~21s，一个「parse」要 2~3 次叠加，慢到以为卡死。
- 全换 `flash` 后快了（2~4s），但**编排层 flash 出现 `MALFORMED_FUNCTION_CALL`**：analyze_jd_match 要把整份 resume_json + 整段 JD 内联进一句 function call，flash 拼大而深的结构化调用时写坏了 JSON。
- **当前折中**：root_agent（编排器）用 `pro`（拼大调用更稳），两个搜索 sub-agent 保持 `flash`。pro 慢但稳。
- **真正治本（待办）= session state**：把 resume_json 存进 ADK 会话状态，下游工具从 state 读，不再当 function-call 参数传。big data 不进 function call，flash 也不会崩。是中等重构（改 4~5 个工具签名+docstring，偏离 ASSIGNMENT 原始签名），暂缓。

### 踩坑：LLM 建议脱离 schema（agent 老让加 professional summary）
- 现象：analyze_jd_match 反复建议「加 professional summary」，但 resume schema 根本没这个字段，template 也没渲染位 → 建议无法落地（空建议）。
- 根因：工具内的 Gemini 是「通用简历顾问」，凭常识说话，**不知道我们 schema 支持哪些字段**。模型通用知识 ≠ 系统可执行的操作，是 LLM agent 典型脱节。
- **修法（已做）**：在 analyze_jd_match 的 prompt 里加约束——只能针对 schema 支持的 section（personal_info/education/experience/projects/skills/additional）和已有 bullet 提建议，明确禁止 summary/objective/cover letter 这类 schema 外建议。**管住模型的嘴，让建议可执行**。
- 决策：**不**为 summary 加功能（学生简历本就不需要 summary，加它是 feature creep）。

### 踩坑：LLM 建议保守、不敢砍、还自我合理化
- 现象：面对 AI 方向岗位，agent 仍建议**保留并润色** C 底层系统项目（cache/heap/malloc），不建议删除或下沉，还声称这能"反映观察能力"——典型套话式自我辩护(hallucinated rationalization)。
- 根因：① analyze_jd_match 本质是**关键词 diff**（covered/missing），只有战术视角（润色 bullet），没有战略视角（项目组合方向对不对）；② prompt 把任务框成 "improvement suggestions" → 模型偏向 add/rewrite，几乎不用已有的 remove/reorder；③ LLM 天生讨好、不愿否定用户已做的东西。
- **本质局限**：战略性职业建议正是 LLM 最弱、最爱说套话的地方，prompt 能改善（加"领域相关性、敢建议 remove"框架）但治不好根。
- 也违背自身设计原则 "agent suggests; user decides"——留不留某项目是**人**的战略决策，agent 只该摆事实，不该替用户拍板还自夸。
- 决策：战略判断交给用户；agent 定位为战术润色。是否调 prompt 让它敢建议砍跑题项目，待定。

### 红线踩坑：幻觉编造用户经历（编出"用了 LangChain"）
- 现象：用户口述的经历很笼统，agent 直接捏造具体技术栈（LangChain）填进 bullet。
- 性质：**简历造假**，比没这功能更危险（面试一问就穿帮 + 诚信问题）。根因是 LLM 本能"宁可编个合理的也不留白"，叠加 rewrite 的隐含目标是"更 impressive"——真实性和 impressive 打架，设计偏错了边。
- **修法（已做）**：① rewrite_bullet prompt 加 "CRITICAL TRUTHFULNESS RULE"：只用输入里的事实，禁止编造技术/数字/框架；② agent instruction GUIDING PRINCIPLES 置顶 "TRUTHFULNESS IS ABSOLUTE"：缺信息就追问，绝不编。
- **诚实局限**：prompt 能大幅压制但**不能 100% 根除**幻觉。真正防线是人逐条核对（再次呼应 "agent suggests; user decides"）。

### 踩坑：date 等字段在工具间搬运时丢失
- 现象：经过 agent 多轮处理后，简历某些 date 字段消失。
- 根因：同 schema 漂移——resume_json 当 function-call 参数反复传，模型重新生成时没原样保留字段。和 text/institution 键名漂移是同一个病根。
- 治本仍是 session state（已推迟）。临时缓解可在 prompt 强调"保留输入所有字段"，但不可靠。

### 认知：这些 prompt 改动属于 context engineering / behavioral steering
- 改 instruction/约束 = 用系统指令引导模型行为，是**概率性引导**不是确定性控制（区别于代码里的 if/else 硬控制流）。
- 想确定性守流程 → 得把 PHASE 拆 sub-agent 用状态机（大改）。
- 改进**无法凭几次手测量化**：需要 eval harness（定指标 + 测试用例 + 改动前后对照违规率）。当前样本量~1，不能声称"提升 X%"。诚实表述只能是"通过系统指令约束 agent 多轮行为"。

### 集成 bug：sync Playwright 在 adk web 的 async 环境里崩
- 现象：save 成功后生成 PDF 报 `You are using Playwright Sync API inside the asyncio loop. Please use the Async API instead.`
- 根因：render_template 用的是 Playwright **同步 API**（sync_playwright），但 adk web 是 **asyncio 异步服务器**。Playwright 硬性禁止 sync API 在运行中的事件循环里跑（会阻塞循环）。单独跑脚本时没有事件循环，所以单测通过；一进 adk web 就炸——典型「单元测试过、集成才暴露」。
- **修法（方案 A，subprocess 隔离）**：把 HTML→PDF 那段抽成 `_html_to_pdf()`，用 `subprocess` 起一个干净子进程跑 sync Playwright（子进程没有事件循环，sync API 正常）。主函数其余逻辑不动，加 try/except 兜底。
- **验证**：专门在 `asyncio.run()` 里调 render_template 复现 adk web 环境 → 修复后 error=None、PDF 生成成功。
- 备选方案 B（改 async_playwright + async def）更正统但牵连面大（要改函数签名和单测方式），hackathon 选了 A。

### 待办：schema 漂移
- 实测 parse_resume 输出的 bullet 用了键 `text`（spec/下游 rewrite_bullet 期望 `content`）、education 用了 `institution`（spec 是 `school`）。模型自由发挥导致键名漂移，下游可能对不上。待对齐。

---

## 待办 / 待定疑问

- [ ] **min_bullets_per_experience 阈值**：spec 是 `< 2`（只有1条才算少），但觉得太死板，2 条也算少。倾向改成 `< 3`。待定。
- [ ] **rewrite has_quantification 是否放宽**（见上）。待定。
- [ ] **MALFORMED_FUNCTION_CALL 治本（升级为必做）**：上 session state，不再把 resume_json 当 function-call 参数传。
  - 2026-06-03 更新：临时方案（换 pro）**已到头**。当 agent 想一次 save+render（双调用 + 双份完整简历内联）时，**连 pro 都崩 MALFORMED**。数据量够大谁都救不了。
  - 同时发现：**schema 漂移的真正源头不在 parse_resume**——是 agent 在对话里凭记忆**重新攒整份简历**去 save，绕过了 parse 的 schema 约束，又冒出 institution/title/text/大写 skills。prompt 锁 parse 的键名治不了这个。
  - 两个问题（MALFORMED + 漂移）**同一个解**：resume_json 存 session state，唯一一份，工具从 state 读，agent 不再内联/重写它。
- [ ] **stale session 并发冲突**：pro 慢响应期间重复点发送/刷新 → 两请求抢同一会话 → ADK 报 `last_update_time earlier than storage`（乐观锁冲突），取消该次运行，但会自愈。操作提醒：pro thinking 时别重复操作。`.adk/session.db` 是运行时产物，已加 .gitignore。
- [ ] **PHASE 2 不守工作流**：长对话里第二轮起跳出澄清循环、自由发挥。已在 instruction 加强制停留 + 明确退出条件改善，但 LLM 不保证 100% 遵守。治本方向（未来）：把 PHASE 拆成 sub-agent 用状态控制流转，而非单段长 instruction。
- [ ] **schema 漂移**：parse_resume 输出键名（text/institution）与 spec（content/school）不一致，待对齐。
- [x] ~~Task 6 `rewrite_bullet.py`~~ ✅ 完成并验证
- [x] ~~Task 7 `compare_versions.py`~~ ✅ 完成并验证（含相同-id 提前返回优化）
- [x] ~~Task 8 agent.py 注册 11 个工具~~ ✅ Total: 11
- [ ] Task 9 `adk web` 端到端联调（进行中：模型已调，schema 约束已加，待重测确认 MALFORMED 是否消除）
