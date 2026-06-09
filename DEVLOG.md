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

## 2026-06-03（晚）— session state 重构（第一期，已写完待端到端验证）

### 动机
MALFORMED + schema 漂移同一个根因：resume_json 当 function-call 参数反复传/被 agent 重写。解法 = 简历在会话里只存一份，放 ADK 的 `tool_context.state`，工具从 state 读，agent 不再传/重写。

### 关键机制（调研确认）
- ADK 靠**类型注解** `tool_context: ToolContext` 自动注入该参数，且**对 Gemini 不可见**（不算模型要填的参数）。所以工具加这个参数后，模型调用时根本不用传简历。
- `tool_context.state` 就是个 delta-aware dict，直接 `state['resume_json'] = ...` 读写。

### 改了什么（5 个工具 + agent.py）
- parse_resume：加 `tool_context`，解析成功后 `state['resume_json'] = resume_json`（唯一写入点 / 入口）。
- analyze_jd_match / check_formatting / render_template / save_resume_version：**去掉 resume_json 参数**，改从 `state.get('resume_json')` 读；没有就返回 "No resume found in session" 优雅降级。
- 手法：check/render 函数体不动，只在开头把 state 的值绑给同名局部变量 `resume_json`。
- agent.py：AVAILABLE TOOLS 更新签名（不再传简历）+ 修正过时的 mongodb.* 名；加 SESSION STATE 段，明确禁止 agent 重构/内联整份简历。

### 验证
- 离线单测（假 tool_context，.state=dict，跑在 asyncio.run 里模拟 adk web）：parse→analyze(score 68)→check(passed)→save(version_id)→render(PDF 含项目名) **整条链全绿**，全程无工具收 resume_json 参数；空 ctx 兜底返回 "No resume found"。✅
- **待办**：adk web 端到端重测（下次）——确认 save+render 双调用不再 MALFORMED、PDF 不漂移。
- 注：第一期不含「rewrite 结果写回 state」（编辑回写留第二期）。当前 rewrite 仍是独立 bullet 进出，改写后的内容尚未合并回 state 里的简历。

### 概念：为什么"背着 resume_json 跑"会拖慢——context 滚雪球
- **LLM 没有记忆**。每一轮对话，模型唯一知道的就是"这次把整段对话历史重新发给它"的内容。
- 所以 resume_json 一旦进了对话历史，就**每一轮都被重新发给模型一次**，像雪球越滚越大——尤其当 agent 还反复重写整份简历时，context 里堆了好几份。
- **慢在哪**：不是"重新读文件"（那是 IO，微秒级，可忽略）。是模型每轮要把整个 context 的 token **重新处理一遍**（技术上叫 prefill：生成回复前先把所有输入 token 算一遍）。resume_json 是一大坨 token，每轮 prefill 都重算它 → 慢、贵，还稀释系统指令的注意力权重（PHASE 2"脱缰"就是连带效应）。
- **session state 为何治本**：把 resume_json 从"对话历史"挪到 state 后，它**不再进 context、不发给模型、不参与 prefill**。工具要用时由**代码**从 state 取（微秒级，不经过模型）。context 变小 → 快、省、不漂移、指令不被稀释。一箭四雕。

### 概念：系统里有两个 Gemini（双层结构）——建议是谁提的
- **主控 agent（编排器，agent.py）**：决定"该调哪个工具"，跟用户对话。**看不到** resume_json（在 state 里）。
- **工具内部的临时 Gemini（如 analyze_jd_match 内部）**：真正分析简历、提建议。**看得到** resume_json——因为是**工具代码主动 `json.dumps(resume_json)` 塞进它的 prompt** 的，用完即弃。
- 结论：修改建议**不是主控 agent 提的**，是 analyze_jd_match 内部那个吃了 resume_json + 内部 prompt 的临时 Gemini 提的。→ 这解释了之前所有怪现象（乱建议 summary、保留 C 项目自我合理化）都该改**工具内部 prompt**，不是改主控 instruction。
- 也解释了 state 里的 resume_json "模型为什么还能用"：**模型本身不理解它**，理解/处理它的是**代码**（Jinja2 渲染、规则检查、塞进内部 prompt）。LLM 负责决策(orchestration)，代码负责执行(deterministic work)——这是 agent 设计的核心分工。
- 读/写回：只读工具（analyze/check/render/save）拿出来用即可，不回写；要改简历的操作（rewrite）才需"取→改→写回 state"，那是第二期。

---

## 2026-06-04 — session state 第二期：rewrite 编辑回写 + schema 漂移确定性兜底

### 第二期：rewrite_bullet 改完写回 state
- **问题**：第一期 rewrite 仍是纯函数（bullet 进出），生成的好句子从没写进 state 里的简历 → render/save 拿到的还是旧 bullet，"改了个寂寞"。
- **改法（方案 A，直接回写）**：
  - 签名 `original_bullet` → `bullet_id` + 加 `tool_context`。原句**从 state 按 id 读**，模型不再传 bullet 文本——又关掉一条漂移路径（同第一期思路）。
  - 新增 `_find_bullet()` 扫 `experience[]` + `projects[]` 两处 bullets。
  - 生成-校验循环不动，改完 `bullet["content"]=new_bullet` 后**重新赋值 `state["resume_json"]=resume_json`** 强制 ADK 记录 delta（光改嵌套 dict 可能不被持久化，同 parse 的唯一写入点写法）。
  - 兜底：无简历 / id 不存在 → 优雅 error；已达标 → attempts=0 不写；跑满 3 次仍不过 → 写回最佳尝试 + warning（措辞改进不丢）。
- **为什么选 A 不选 B（暂存+显式 apply）**：
  - 性能/漂移**都不是** A vs B 的决策依据——两者都把简历挡在模型外。读写 state 是代码层微秒级 IO，不进 prefill；回写是**只追加历史、从不重写**，整份简历只在 parse 返回里进 context 一次、之后靠 prompt 缓存命中（缓存友好），不再每轮重发。真正拖慢的老雪球是"模型反复把简历当 function-call 参数吐出来"，回写恰好消灭它。
  - 既然性能打平，只剩产品问题"要不要落库前预览闸门"。A 把"生成"和"落库"焊成一个原子调用 → 给不了真正的预览（用户看到时已改完）；B 的 staging 能预览但多一个 apply 工具 + pending 状态。结论：**设计成本和用户体验都差不多 → 选 A，决定闸门靠 PHASE 3 勾选那一下**。
- **验证**（asyncio 模拟 adk web + 假 tool_context + 真 Gemini）：_find_bullet 跨两段/未命中、无简历→error、坏 id→error、已达标→attempts=0 不写、弱 bullet 真改写并写回 state，全绿。

### schema 漂移：从"概率压制"升级到"代码保证"
- **重新核实，结论先行**：当前**没有结构性漂移**。parse prompt 已硬化（点名禁 `title`/`institution`/`item`/`text`），模板只读 canonical 键（`.content`/`.school`/`.name`/`.tech_stack`），rewrite 读 `content`——三处契约一致。DEVLOG 旧待办是 prompt 硬化前写的，已被覆盖。
- **残余风险**：parse 输出键由 Gemini 概率生成，prompt 约束非确定性。回写让 rewrite 现在**硬依赖 `content`**（漂成 `text` → 原句读空 → 改写空串），这是漂移现在唯一会真咬人的点。
- **修法**：parse `json.loads` 后加 `_normalize_schema()`——section-targeted 改名（`institution→school`、`title→name`、`text/item/description→content`），**不做盲目递归**以免误伤 skills/links 里的同名键。漂了也兜回 canonical，确定性。
- 验证：漂移输入全部归一、canonical 输入不动、空/缺 section 不崩。✅

---

## 2026-06-07 — Task 9 端到端联调通过（session state 两期 + MALFORMED 全部验证）

### 怎么测的：用 `adk api_server` 代替浏览器，REST 直接打
- `adk web` 没法脚本驱动浏览器，但 `adk api_server` 是**同一套 async FastAPI**（同样的事件循环、同样的编排器 `gemini-2.5-pro`），能复现当初 MALFORMED / Playwright-async 的全部风险。
- 流程：`POST /apps/my_agent/users/u1/sessions/s1` 建会话 → 多次 `POST /run` 发消息 → `GET …/sessions/s1` 读 `state` 验回写。

### 结果：四次 /run 全 200，三个核心待办端到端确认
1. **parse**：`parse_resume` 真实调用，`state.resume_json` 写入，键全 canonical（`content`/`name`/`tech_stack`），无漂移。
2. **analyze**：`analyze_jd_match` 调用参数**只有 `jd_text`**（简历从 state 读，不再内联进 function call）→ score 50 + 7 建议，**无 MALFORMED**。
3. **save + render 双调用**（当初连 pro 都崩的点）：同一轮两工具都成功，参数只有 `label`/`output_format`；PDF 110KB，John Doe/MIT/Google/PyTorch/**2023(日期)**/caching 全在 → **字段无漂移**；async 服务器里 subprocess-Playwright 正常（方案 A 站住了）。
4. **rewrite 回写（第二期）**：先**追问真实数据**（TRUTHFULNESS 守住没编数字）；给真实指标后 `rewrite_bullet` 只传 `bullet_id`，attempts=1，`state` 里 bul1 从 "Worked on backend caching" → "Implemented a Redis caching layer … reducing latency by 30%"，**回写确认生效**。

### 日志扫描：唯一 traceback 是已知无害的 403
- `cloudresourcemanager` SERVICE_DISABLED（SDK 启动想把 project 编号转 ID，`.env` 已给 project → 兜底继续跑，结果照常）。**无 MALFORMED、无 Playwright async 报错、无 schema 漂移。**
- 教训：验证 LLM 编排器的行为（MALFORMED 这种）必须走**真实 Runner / api_server**，离线假 tool_context 测不出来——它绕过了编排器拼 function call 这一步，而 bug 恰恰在那。

### ⚠️ 流程教训：动手前没做同类产品调研（下次必做）
- **现象**：整个 Resume Agent 从 Task 1 直接开干，**没先调研市面上同类 resume builder / resume agent**（开源仓库、Claude/GPT 的 resume skill、现成 SaaS）就开始造。直到接近收尾才想起来"网上有现成的 skill"。
- **代价**：可能重复造轮子、错过更好的 schema / prompt / 模板设计、也没有对标的功能基线来判断自己缺什么。
- **下次铁律**：**做任何新东西之前，先花 30 分钟扫一遍同类产品** —— 看它们的功能清单、数据结构、prompt 套路、踩过的坑。能借鉴的借鉴，能避的坑提前避，再决定自己造什么、怎么造。
- **提醒**：调研 ≠ 抄。目的是「站在别人肩膀上定边界」，避免闭门造车。这条已同步进长期记忆，下次开工会自动提醒。

---

## 2026-06-07（下午）— 前端 PDF 上传卡死 + parse_resume 的 pdf 分支是死代码/陷阱

### 现象
Streamlit 前端（frontend/app.py）上传 PDF 后，"Parsing resume…" 转圈不返回。

### 定位（隔离实验是关键）
- 用同样的 Runner 发一条**短文本**消息 → 7.6s 正常返回 1 个 event。→ **排除** Streamlit↔ADK Runner 的 asyncio 集成死锁，也**排除**前后端没接好。
- 卡住时进程 **0% CPU、零模型请求、无 traceback** = 在等模型吐一大坨东西，不是在算。
- **根因**：前端把整个 PDF base64 塞进一条文本消息发给编排器（app.py:118-121），编排器要调 `parse_resume(raw_text=<整段base64>)` 就得把几万 token 的 base64 原样"背诵"进函数调用参数 → 极慢/超输出上限/MALFORMED。**这是"大数据穿过 LLM"的老病**（resume_json 当年用 session state 治过，但 PDF 这条入口还在硬穿模型）。

### 连带结论：parse_resume 的 `source_format=='pdf'` 分支
- 全仓**只有前端 app.py:121 用 `source_format='pdf'`**，别处都没有；adk web 里 LLM 默认走 text。
- 即该分支**唯一被触发的途径就是上面这条卡死的路**。
- docstring 还明写"pdf 时传 base64"（parse_resume.py:45-47）→ **主动诱导 LLM 接收 base64**，是个陷阱，不只是死代码。

### 决定（方向 A，**未动手**，明天做）
- 前端用 pdfplumber **本地抽文本**，只发文本（走已验证的 text 路）。
- `parse_resume` 砍成纯文本工具：**删 pdf 分支 + docstring 去掉 base64**，消灭"base64 穿 LLM"陷阱。
- 后端其他工具不动。

### 过程教训（记给自己）
- 提"前端抽文本"这个修法时，**当时就该一并说清它的下游影响**：pdf 分支会变死代码 + docstring 会把 LLM 引回坑。等用户追问才补，是没把一个改动的连带后果一次讲透。下次提方案 = 同时给出它"删/废/影响"了什么。

---

## 2026-06-09 — 隔夜服务器"假卡死" + PDF 上传卡死定位 + 方向 A 落地

### 教训：隔夜的 dev server + 机器睡眠 = 假卡死，别 debug，直接重启
- 现象：前端"页面一直加载不出来"。查下来服务器 health 200、2ms、进程 0% CPU idle —— 后端好好的。
- 真相：那个 Streamlit 进程 `ELAPSED` 已 20 小时（隔了一夜），机器睡过 → Streamlit 赖以渲染界面的 **websocket 长连接断了**，旧标签一直重连失效 session → 卡在加载。
- 解法：杀掉隔夜进程、重启、用带参数的全新 URL（`?fresh=1`）绕过赖着不刷新的旧标签。**长命 dev server 不值得 debug。**

### PDF 上传卡死 = 2026-06-07 诊断的 base64 穿 LLM（隔离实验复现）
- probe 隔离：`parse_resume(text)` 单独跑 16s 正常；完整 Runner 路径 22.8s 正常调 parse 并成功 → **证明后端没问题**，卡的是 PDF 入口（前端把 base64 塞进消息让编排器"背"进 function call）。
- 也顺带证伪："编排器只给简历不给 JD 就不 parse"是错的——probe 里 7.1s 就调了 parse。

### 方向 A 落地（终于动手）
- `frontend/app.py`：上传后 **pdfplumber 本地抽文本**，只发纯文本（走已验证的 text 路）；import 去 base64、加 io/pdfplumber。
- `parse_resume`：删 pdf 分支 + **去掉 source_format 参数**（砍成纯文本工具）+ 清掉 io/base64/pdfplumber 孤儿 import + docstring 去 base64；`agent.py` 工具签名同步成 `parse_resume(raw_text)`。
- 验证：真 PDF(52KB) → 抽 546 字符 → parse 12.4s 成功，端到端通。

### 顺带量化：换编排器模型治不了"慢"
- 编排器 pro vs flash **都 ~23s**，一样慢。瓶颈是**两层 LLM**（编排器决策 + 工具内部各一次 Gemini 调用）+ 2.5-flash 默认 thinking + 冷启动；关 thinking 只省 ~1s；2.0-flash 在本 project/region 404 不可用。
- UX 真正的解药 = **流式工具进度**：`runner.run()` 本就逐个 yield function_call/response 事件，但前端 `chat()` 现在把中间事件全扔了。把它们实时显示成"📄 正在解析…/🖼 正在渲染…"，时间没变但不再像死掉。待做。

---

## 2026-06-09 — 能力缺口 → 统一编辑器 edit_resume（替代 piecemeal）

### 现象：agent 反复"提了建议、用户批了、却做不到"，还编假借口
- 加 GitHub 链接：agent 说"渲染步骤会把链接丢掉"——**纯属瞎编**（模板第 20-22 行明确渲染 github，parse 也抓得到）。又一次 hallucinated rationalization（老毛病）。
- 往 skills 加 "Software Engineering"：直接 "could not be applied"。

### 根因：指令开了工具兑现不了的空头支票
- instruction 把 "edit skills/additional"、"编辑联系方式" 列为**允许操作**，但后端能改数据的工具只有 `rewrite_bullet`（只改 bullet）。**指令承诺的能力没有工具支撑。**

### 弯路 → 修正：先 piecemeal，被叫停后改为"先勘察再统一"
- 先加了 `edit_personal_info`（只补联系方式）。用户："别一个单元一个单元地改"——对。
- 改为：**先勘察 template 到底渲染了哪些内容**（标量 / 字符串列表 / bullet 三种形状），再设计**一个统一编辑器**。

### 方案：`edit_resume(path, value, operation)`
- 删 `edit_personal_info`，新增 `edit_resume`：**路径式扁平参数**（`skills.other` / `personal_info.links.github` / `experience[ex1].end_date`）—— 不传嵌套结构 → 避免 MALFORMED。
- `set` 改标量，`add`/`remove` 改字符串列表，覆盖模板里**除 bullet 外所有字段**；bullet 仍归 `rewrite_bullet`（它带 rubric）。
- **白名单校验**：越界路径（如 `personal_info.summary`）直接拒绝 → 守住"无 summary"纪律；错 entry id 返回有效 id 让 Gemini 自我纠正。
- `agent.py` 指令 3 处引用更新 + **明令禁止再编"加不了/渲染会丢"的借口**。

### 教训
- **工具面必须对齐模板渲染面**——别让指令承诺没工具支撑的能力（这是这一串"做不到"的总根）。
- 统一路径式编辑器 > N 个 per-section 工具；路径+扁平参数是"穿过 ADK/Gemini 改嵌套数据"的 MALFORMED-safe 写法。
- 踩坑：在**单引号** instruction 字符串里写了单引号 `'skills.tools'` → 字符串提前截断 → 语法错。改双引号。编辑那个巨型单引号串时内部只能用双引号。

---

## 待办 / 待定疑问

- [x] ~~**前端 PDF 上传卡死 → 方向 A**~~ ✅ 2026-06-09 落地：前端 pdfplumber 本地抽文本只发文本；`parse_resume` 删 pdf 分支 + 去 source_format 参数。真 PDF 端到端验证通过（见上）。
- [ ] **流式工具进度（UX）**：把 `runner.run()` 的中间 function_call 事件实时显示（"正在解析/渲染…"），让 ~25s 阻塞不像死掉。事件已有，只需改前端 `chat()`。真正提速（关 thinking / parse 不走编排器）另议。
- [ ] **统一编辑器后续（结构性 CRUD）**：`edit_resume` 已覆盖字段/列表项；新增/删除整条 experience/project entry、reorder 顺序、add/remove bullet 暂未做（当时选了最小范围 A）。需要再补。
- [ ] **min_bullets_per_experience 阈值**：spec 是 `< 2`（只有1条才算少），但觉得太死板，2 条也算少。倾向改成 `< 3`。待定。
- [ ] **rewrite has_quantification 是否放宽**（见上）。待定。
- [x] ~~**MALFORMED_FUNCTION_CALL 治本**~~ ✅ session state 第一期已实现，2026-06-07 经 `adk api_server` 端到端确认：save+render 双调用 200、无 MALFORMED（见上）。
  - 背景：临时方案（换 pro）已到头，save+render 双调用连 pro 都崩；schema 漂移真源头是 agent 重写简历，非 parse_resume。
  - [x] ~~第二期：rewrite 结果写回 state（编辑回写）~~ ✅ 方案 A 直接回写，离线验证通过（2026-06-04，见上）。
- [ ] **stale session 并发冲突**：pro 慢响应期间重复点发送/刷新 → 两请求抢同一会话 → ADK 报 `last_update_time earlier than storage`（乐观锁冲突），取消该次运行，但会自愈。操作提醒：pro thinking 时别重复操作。`.adk/session.db` 是运行时产物，已加 .gitignore。
- [ ] **PHASE 2 不守工作流**：长对话里第二轮起跳出澄清循环、自由发挥。已在 instruction 加强制停留 + 明确退出条件改善，但 LLM 不保证 100% 遵守。治本方向（未来）：把 PHASE 拆成 sub-agent 用状态控制流转，而非单段长 instruction。
- [x] ~~**schema 漂移**：parse_resume 输出键名（text/institution）与 spec（content/school）不一致~~ ✅ prompt 已硬化 + 加 `_normalize_schema()` 确定性兜底（2026-06-04，见上）。
- [x] ~~Task 6 `rewrite_bullet.py`~~ ✅ 完成并验证
- [x] ~~Task 7 `compare_versions.py`~~ ✅ 完成并验证（含相同-id 提前返回优化）
- [x] ~~Task 8 agent.py 注册 11 个工具~~ ✅ Total: 11
- [x] ~~Task 9 `adk web` 端到端联调~~ ✅ 2026-06-07 经 api_server 全链路通过（parse→analyze→save+render→rewrite 回写），MALFORMED 已消除（见上）。
