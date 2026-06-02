# Resume Agent — 实现作业

> 每个任务完成后用对应的验收命令检验，通过再进入下一题。
> 卡住了随时问。不要跳题。

---

## 环境准备

每次开终端，先 cd 到项目根目录，所有命令在这里运行：

```bash
cd /Users/alexlyk/Desktop/Google_hackathon_Agent
```

验证环境正常：

```bash
python -W ignore -c "from google.adk.agents import LlmAgent; print('env ok')"
```

---

## Task 1 — `parse_resume.py`

**文件**：`my_agent/tools/parse_resume.py`

**你要实现**：`parse_resume(raw_text, source_format)` 函数体。

### 步骤

**Step 1**：处理 PDF 输入。

如果 `source_format == "pdf"`，`raw_text` 是一个 base64 编码的 PDF 文件字节。
你需要：
1. 用 `base64.b64decode(raw_text)` 解码成 bytes
2. 用 `pdfplumber.open(io.BytesIO(pdf_bytes))` 打开
3. 遍历所有页，对每页调用 `.extract_text()`，用 `"\n".join(...)` 拼成纯文本
4. 将结果赋值给 `raw_text`（覆盖原来的参数）

**Step 2**：调用 Gemini 提取结构化 JSON。

```python
model = GenerativeModel("gemini-2.0-flash")
response = model.generate_content(your_prompt)
text = response.text.strip()
```

**Step 3**：构造 prompt。

Prompt 里需要告诉模型：
- 返回 ONLY 纯 JSON，不要 markdown 代码块
- 必须包含字段：`personal_info`, `education`, `experience`, `projects`, `skills`, `additional`
- 给每个 experience、project、education 条目、以及每个 bullet 分配一个短 ID（如 "e1", "b2"）
- 缺失字段用 `null`

**Step 4**：解析 JSON，处理错误。

```python
try:
    resume_json = json.loads(text)
    return {"resume_json": resume_json, "parse_warnings": []}
except json.JSONDecodeError as exc:
    return {"resume_json": None, "parse_warnings": [f"JSON parse error: {exc}"]}
```

> 注意：模型有时会在 JSON 前后加 ` ```json ` 代码块标记。
> 加个清理步骤：如果 `text` 以 ` ``` ` 开头，把第一行和最后一行剔掉。

### 验收

```bash
python -W ignore -c "
from my_agent.tools.parse_resume import parse_resume
result = parse_resume('John Doe\njohn@example.com\n\nEducation\nMIT, BS CS, 2020-2024\n\nExperience\nGoogle, SWE Intern\n- Built search indexing pipeline')
print('resume_json keys:', list(result['resume_json'].keys()))
print('warnings:', result['parse_warnings'])
"
```

期望输出包含：`personal_info`, `education`, `experience` 等 key，warnings 为空列表。

---

## Task 2 — `mongo_tools.py`

**文件**：`my_agent/tools/mongo_tools.py`

**你要实现**：`_get_db()`、`save_resume_version()`、`list_resume_versions()`、`load_resume_version()`。

### 步骤

**`_get_db()`**：

使用 module-level 的 `_client` 变量做懒加载（lazy initialization）。

```python
# Java 类比：单例模式的 getInstance()
global _client
if _client is None:
    _client = MongoClient(os.getenv("MONGO_URI"))
return _client[os.getenv("MONGO_DB", "resume_agent")]
```

**`save_resume_version()`**：

1. 调用 `_get_db()` 获取 db
2. 构造 document dict，包含：`user_session`, `label`, `template_used`, `created_at`（用 `datetime.now(timezone.utc)`），`resume_json`
3. 调用 `db["resume_versions"].insert_one(doc)`
4. 返回 `{"version_id": str(result.inserted_id), "created_at": doc["created_at"].isoformat()}`

**`list_resume_versions()`**：

1. 查询 `{"user_session": user_session}`，**排除** `resume_json` 字段（projection `{"resume_json": 0}`）
2. 按 `created_at` 降序排列，限制 20 条
3. 遍历结果：把每条的 `_id` 转为字符串并重命名为 `version_id`，`created_at` 转为 ISO 字符串
4. 返回 `{"versions": [...]}`

**`load_resume_version()`**：

1. 用 `ObjectId(version_id)` 查询。注意：`ObjectId()` 会在 ID 格式错误时抛异常，用 `try/except` 捕获
2. 如果找不到文档，返回 `{"error": f"Version {version_id} not found"}`
3. 找到了：同样把 `_id` → `version_id`，`created_at` → ISO string

### 验收

```bash
python -W ignore -c "
from my_agent.tools.mongo_tools import save_resume_version, list_resume_versions, load_resume_version

# 保存一个假版本
fake_resume = {'personal_info': {'name': 'Test'}, 'experience': []}
result = save_resume_version(fake_resume, label='Test v1')
print('saved:', result)

# 列出版本
versions = list_resume_versions()
print('versions count:', len(versions['versions']))

# 加载刚保存的版本
loaded = load_resume_version(result['version_id'])
print('loaded label:', loaded['label'])
"
```

期望：能在 MongoDB Atlas 后台看到 `resume_versions` 集合里出现了新文档。

---

## Task 3 — `render_template.py`

**文件**：`my_agent/tools/render_template.py`

**你要实现**：`render_template(resume_json, template_name, output_format)` 函数体。

### 步骤

**Step 1**：检查模板目录是否存在。

```python
template_dir = TEMPLATES_DIR / template_name
if not template_dir.exists():
    return {"file_path": None, "html_preview": None, "error": f"Template '{template_name}' not found"}
```

**Step 2**：用 Jinja2 渲染 HTML。

```python
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader(str(template_dir)))
template = env.get_template("template.html")
html = template.render(resume=resume_json)
```

**Step 3**：如果只要 HTML，直接返回。

```python
if output_format == "html":
    return {"file_path": None, "html_preview": html}
```

**Step 4**：用 Playwright 把 HTML 转成 PDF。

```python
from playwright.sync_api import sync_playwright

output_path = f"/tmp/resume_{uuid.uuid4().hex[:8]}.pdf"
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content(html, wait_until="networkidle")
    page.pdf(path=output_path, format="Letter",
             margin={"top": "0in", "bottom": "0in", "left": "0in", "right": "0in"})
    browser.close()

return {"file_path": output_path, "html_preview": html}
```

### 验收

```bash
python -W ignore -c "
from my_agent.tools.render_template import render_template

fake_resume = {
    'personal_info': {'name': 'Jane Doe', 'email': 'jane@test.com', 'phone': '555-1234', 'location': 'NYC', 'links': {}},
    'education': [{'id': 'ed1', 'school': 'MIT', 'degree': 'BS', 'major': 'CS', 'gpa': '3.9', 'start_date': '2020-09', 'end_date': '2024-05', 'location': 'Cambridge MA', 'details': []}],
    'experience': [{'id': 'e1', 'company': 'Google', 'role': 'SWE Intern', 'location': 'NYC', 'start_date': '2023-06', 'end_date': '2023-08', 'bullets': [{'id': 'b1', 'content': 'Built a distributed caching layer reducing latency by 40%'}]}],
    'projects': [], 'skills': {'languages': ['Python', 'Java'], 'frameworks': [], 'tools': [], 'other': []}, 'additional': {}
}

result = render_template(fake_resume, output_format='pdf')
print('PDF saved to:', result['file_path'])
print('HTML length:', len(result['html_preview']))
"
```

期望：PDF 文件路径显示在 `/tmp/` 下，用 `open /tmp/resume_xxxxxxxx.pdf` 打开看排版效果。

---

## Task 4 — `analyze_jd_match.py`

**文件**：`my_agent/tools/analyze_jd_match.py`

**你要实现**：`analyze_jd_match(resume_json, jd_text)` 函数体。

### 步骤

**Step 1**：构造 Gemini prompt。

Prompt 里要包含：
- 两段内容：resume（用 `json.dumps(resume_json, indent=2)` 转字符串）和 jd_text
- 明确要求返回以下 JSON 结构（只返回 JSON，不要 markdown）：
  ```json
  {
    "match_score": 72,
    "keyword_coverage": {"covered": ["Python", "REST"], "missing": ["Kubernetes"]},
    "experience_relevance": [{"experience_id": "e1", "score": 85, "reason": "..."}],
    "suggestions": [
      {"id": "s1", "description": "...", "target": "b1", "type": "rewrite", "impact_score": 9}
    ]
  }
  ```
- 要求 5-8 条 suggestions，按 impact_score 降序
- `type` 必须是：`rewrite | reorder | add | remove | quantify` 其中之一

**Step 2**：调用模型，清理输出，解析 JSON（和 Task 1 一样的模式）。

**Step 3**：处理 JSON 解析失败，返回带 `"error"` key 的空结构。

### 验收

```bash
python -W ignore -c "
from my_agent.tools.analyze_jd_match import analyze_jd_match
import json

resume = {'personal_info': {'name': 'Alex'}, 'experience': [{'id': 'e1', 'company': 'Amazon', 'role': 'SWE', 'bullets': [{'id': 'b1', 'content': 'Worked on backend services'}]}], 'skills': {'languages': ['Python']}}
jd = 'We are looking for a software engineer with experience in distributed systems, Python, Go, Kubernetes, and REST APIs.'

result = analyze_jd_match(resume, jd)
print('match_score:', result.get('match_score'))
print('missing keywords:', result.get('keyword_coverage', {}).get('missing'))
print('suggestion count:', len(result.get('suggestions', [])))
"
```

期望：`match_score` 是 0-100 的整数，`missing` 包含 "Kubernetes" 或 "Go" 之类的词，suggestions 有 5+ 条。

---

## Task 5 — `check_formatting.py`

**文件**：`my_agent/tools/check_formatting.py`

**你要实现**：`check_formatting(resume_json, template_name)` 函数体。

### 规则清单（全部硬编码，不需要读 YAML，YAML 只是参考文档）

| rule_id | severity | 检查逻辑 |
|---|---|---|
| `required_sections` | error | `resume_json.get("personal_info")` 或 `resume_json.get("education")` 为空/None |
| `personal_info_email` | error | `resume_json["personal_info"]["email"]` 为空/None |
| `max_page_estimate` | warning | `len(json.dumps(resume_json)) > 3500` |
| `max_bullets_per_experience` | warning | 任意 experience 的 bullets 数量 > 5 |
| `min_bullets_per_experience` | warning | 任意 experience 的 bullets 数量 > 0 但 < 2 |
| `max_bullets_per_project` | warning | 任意 project 的 bullets 数量 > 4 |
| `consistent_date_format` | warning | 任意 `start_date`/`end_date` 不匹配正则 `^\d{4}-\d{2}$` 且不等于 `"Present"` |

每条 violation 是一个 dict：
```python
{
    "rule_id": "required_sections",
    "severity": "error",
    "target": "education",          # 哪个字段或条目出了问题
    "message": "...",               # 人类可读的描述
    "suggestion": "...",            # 建议怎么修
}
```

`passed` = 没有任何 `severity == "error"` 的 violation（warnings 不影响 passed）。

### 验收

```bash
python -W ignore -c "
from my_agent.tools.check_formatting import check_formatting

# 故意写一个有问题的简历
bad_resume = {
    'personal_info': {'name': 'Test', 'email': None},
    'experience': [{'id': 'e1', 'company': 'X', 'role': 'Y', 'bullets': [
        {'id': 'b1', 'content': 'bullet1'},
        {'id': 'b2', 'content': 'bullet2'},
        {'id': 'b3', 'content': 'bullet3'},
        {'id': 'b4', 'content': 'bullet4'},
        {'id': 'b5', 'content': 'bullet5'},
        {'id': 'b6', 'content': 'bullet6'},  # 6 bullets, should warn
    ]}]
}

result = check_formatting(bad_resume)
print('passed:', result['passed'])
for v in result['violations']:
    print(f'  [{v[\"severity\"]}] {v[\"rule_id\"]}: {v[\"message\"]}')
"
```

期望：`passed: False`（因为 email 缺失是 error），violations 包含 `personal_info_email` 和 `max_bullets_per_experience`。

---

## Task 6 — `rewrite_bullet.py`（最难）

**文件**：`my_agent/tools/rewrite_bullet.py`

**你要实现**：`_check_bullet_rubric(bullet)` 和 `rewrite_bullet(original_bullet, instruction, context)`。

### Part A：`_check_bullet_rubric(bullet)`

三个检查（用 ACTION_VERBS 常量和 re 模块）：

1. **`has_action_verb`**：`bullet.strip().split()[0].lower().rstrip(",")` 是否在 `ACTION_VERBS` 列表里
2. **`has_quantification`**：是否包含数字或百分比，用正则 `re.search(r"\d+%?|\d+[kKmMbB]?\b", bullet)`
3. **`within_length`**：`len(bullet) <= 180`

返回：
```python
{
    "passed": True/False,           # 三个全过才是 True
    "checks": {
        "has_action_verb": True/False,
        "has_quantification": True/False,
        "within_length": True/False,
    },
    "violations": ["具体哪条没过的说明", ...]
}
```

### Part B：`rewrite_bullet(original_bullet, instruction, context)`

核心是**带自我纠错的重试循环**（这是整个项目最重要的 Agent 模式）：

```
for attempt in range(1, MAX_RETRIES + 1):
    1. 构造 prompt（包含 original_bullet、instruction、context 里的 role/tech_stack/jd_text）
    2. 调用 Gemini，strip 得到 new_bullet
    3. 调用 _check_bullet_rubric(new_bullet)
    4. 如果 passed → 直接 return {"new_bullet", "validation", "attempts": attempt}
    5. 如果没过 → 把 violations 追加到 instruction 后面，进入下一轮
循环结束后（3次都没过）→ return 最后一次的结果 + "warning" key
```

Prompt 要求 Gemini 做到：
- 以强动词开头（Built / Reduced / Implemented...）
- 包含量化指标
- 不超过 180 字符
- 只返回 bullet 文本本身，不要引号或解释

### 验收

```bash
python -W ignore -c "
from my_agent.tools.rewrite_bullet import _check_bullet_rubric, rewrite_bullet

# 先测 rubric checker
bad = 'Worked on backend stuff'
good = 'Reduced API latency by 35% by implementing Redis caching layer'
print('bad bullet passes?', _check_bullet_rubric(bad)['passed'])
print('good bullet passes?', _check_bullet_rubric(good)['passed'])

# 再测整个 rewrite（会真实调 Gemini，需要几秒）
result = rewrite_bullet(
    original_bullet='Helped with search feature',
    instruction='Make it stronger and add quantification',
    context={'experience_role': 'SWE Intern', 'tech_stack': ['Python', 'Elasticsearch']}
)
print('new bullet:', result['new_bullet'])
print('passed rubric?', result['validation']['passed'])
print('attempts:', result['attempts'])
"
```

期望：bad bullet fails，good bullet passes，rewrite 输出的 bullet 以动词开头且包含数字。

---

## Task 7 — `compare_versions.py`

**文件**：`my_agent/tools/compare_versions.py`

**你要实现**：`compare_versions(version_a_id, version_b_id)` 函数体。

### 步骤

1. 调用 `load_resume_version(version_a_id)` 和 `load_resume_version(version_b_id)`
2. 如果任意一个返回有 `"error"` key，直接 return `{"error": "Version A/B: " + error_message}`
3. 构造 prompt，包含两份简历的 JSON 和 label，要求返回以下 JSON（只返回 JSON）：
   ```json
   {
     "summary": "...",
     "diff": {
       "modified_bullets": [{"before": "...", "after": "...", "section": "..."}],
       "added": ["..."],
       "removed": ["..."],
       "reordered": ["..."]
     }
   }
   ```
4. 调用 Gemini，解析 JSON，处理失败（返回空 diff + error key）

### 验收

先确保 Task 2 的验收已经在 MongoDB 里存了至少一个版本。用 `list_resume_versions()` 拿到两个不同 version_id（如果只有一个，再用 `save_resume_version` 存一个），然后：

```bash
python -W ignore -c "
from my_agent.tools.mongo_tools import list_resume_versions
versions = list_resume_versions()
ids = [v['version_id'] for v in versions['versions']]
print('available version IDs:', ids[:3])
"
```

```bash
python -W ignore -c "
from my_agent.tools.compare_versions import compare_versions
result = compare_versions('VERSION_A_ID_HERE', 'VERSION_B_ID_HERE')
print('summary:', result.get('summary'))
print('modified bullets:', len(result.get('diff', {}).get('modified_bullets', [])))
"
```

---

## Task 8 — `agent.py` 注册

**文件**：`my_agent/agent.py`

你要做两件事：

**Step 1**：在文件顶部 import 你写的所有工具：

```python
from .tools.parse_resume import parse_resume
from .tools.mongo_tools import save_resume_version, list_resume_versions, load_resume_version
from .tools.render_template import render_template
from .tools.analyze_jd_match import analyze_jd_match
from .tools.check_formatting import check_formatting
from .tools.rewrite_bullet import rewrite_bullet
from .tools.compare_versions import compare_versions
```

**Step 2**：把它们加进 `root_agent` 的 `tools=[]` 列表里（直接传函数对象，不需要包装）。

### 验收

```bash
python -W ignore -c "
from my_agent.agent import root_agent
tool_names = []
for t in root_agent.tools:
    name = getattr(t, 'name', None) or getattr(getattr(t, 'func', None), '__name__', repr(t))
    tool_names.append(name)
print('Registered tools:', tool_names)
print('Total:', len(tool_names))
"
```

期望：输出的列表包含你所有工具函数的名字，Total 为 11。

---

## Task 9 — 跑起来

全部实现完毕后：

```bash
adk web
```

浏览器打开 `http://localhost:8000`，选 `Resume_Builder`，在对话框里粘贴一段简历文字：

```
John Doe | john@example.com | github.com/johndoe

Education: MIT, BS Computer Science, GPA 3.8, 2020-2024

Experience:
Google, Software Engineer Intern, June 2023 - Aug 2023
- Worked on backend caching
- Helped improve search latency

Projects:
Image Classifier, Python, PyTorch
- Did machine learning on images
```

然后发送：`"Please parse my resume."`

在 ADK 的 **Events 面板**（右侧）观察：
- 看到 `parse_resume` 工具被调用了吗？
- 返回的 JSON 结构是否正确？

这是你第一次看到 Agent Loop 的真实运作。

---

## 完成标准

| Task | 验收条件 |
|---|---|
| 1 parse_resume | 能解析纯文本简历，返回含 personal_info/experience 的 JSON |
| 2 mongo_tools | 能存入 MongoDB Atlas，能查出来，Atlas 后台可见文档 |
| 3 render_template | 能生成 PDF 文件，`open /tmp/resume_xxx.pdf` 可以打开看 |
| 4 analyze_jd_match | 返回 match_score + 5条以上 suggestions |
| 5 check_formatting | 对 bad resume 正确报告 violations |
| 6 rewrite_bullet | rubric checker 能区分好坏 bullet，rewrite 输出有动词+数字 |
| 7 compare_versions | 能对两个 MongoDB 版本返回 diff summary |
| 8 agent.py | Total 工具数 = 11 |
| 9 adk web | Events 面板能看到 parse_resume 工具调用事件 |
