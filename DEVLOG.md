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

## 待办 / 待定疑问

- [ ] **min_bullets_per_experience 阈值**：spec 是 `< 2`（只有1条才算少），但觉得太死板，2 条也算少。倾向改成 `< 3`。待定。
- [ ] **rewrite has_quantification 是否放宽**（见上）。待定。
- [x] ~~Task 6 `rewrite_bullet.py`~~ ✅ 完成并验证
- [ ] Task 7 `compare_versions.py` 待实现
- [ ] agent.py 注册 7 个工具 → `adk web` 联调
