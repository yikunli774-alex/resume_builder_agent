# HANDOFF — 给下一次的自己

> 最后更新：2026-06-12（演示视频已录完，收尾提交）。这是"我离开时的状态"，工程细节看 [DEVLOG_CN.md](DEVLOG_CN.md)（英文版 [DEVLOG_EN.md](DEVLOG_EN.md)）。

---

## ⚠️ 一句话现状（先看这条）

**功能全部完成，浏览器实测过，演示视频已录制。** 全部工作在 `feat/streaming-progress` 分支并已 push + 合并 main。剩下的事只有：① 提交 hackathon（视频 + repo）；② 将来要公网部署时走下面的部署清单。

---

## 当前 git 状态

- 全部工作已 commit 并 push 到 `github.com/yikunli774-alex/resume_builder_agent`
- `feat/streaming-progress` 已合并进 `main`（README/DEVLOG 在 main 上对评委可见）
- `.env` 从未进过 git（.gitignore 第一天就有），clone 的人要自己配

## 最后两个会话做了什么（06-11 ~ 06-12）

1. **流式工具进度**落地 + 修 st.status 嵌套崩溃 + 标题/正文去重
2. **禁止 agent 在聊天贴 HTML**（instruction 是 adk web 时代遗物，右栏会自动显示预览）
3. **Prompt 全面审计**：10 处"instruction/docstring 承诺 vs 真实工具面/UI"矛盾一次清掉（教训：docstring 也是 prompt）
4. **edit_resume 结构性 CRUD**：add_entry（两步走）/ remove_entry / move + bullets add/remove；离线 25/25；起因是 agent 把经历挂到别的项目名下（misattribution 事故，见 DEVLOG）
5. **missing_dates 规则** + instruction 要求转告所有 violations（治"不问项目时间也能过"）
6. **模板链接显示真实 URL**（原来可见文字写死 "GitHub"）
7. **load_resume_version 写回 state**（双模式：工具调用恢复草稿、代码调用不变）——数据库闭环：存→列→取回→对比→下载
8. **Version history 每条版本 ⬇ 直接下载 PDF**（零 LLM，按需渲染+缓存）
9. **aiohttp 3.10→3.14**：治频繁 "(no text response)"（genai 重试逻辑引用 3.11 才有的类）；requirements.txt 已加下限
10. Version history 直连工具函数渲染右栏（不走编排器）；README 全文 + DEVLOG 双语化

---

## 怎么跑起来 + 坑

- 启动：`/opt/anaconda3/bin/python -m streamlit run frontend/app.py --server.headless true`（后台跑），开 `http://localhost:8501/?fresh=N`（**带参数绕过赖着不刷新的旧标签**）。
- **Streamlit 只热重载 `frontend/app.py`**；改了 `my_agent/*` 必须**重启服务器**。
- Python 用 `/opt/anaconda3/bin/python`，装包用 `python -m pip`（裸 pip 装错环境）。
- `.env` 在 `my_agent/.env`（GOOGLE_GENAI_USE_VERTEXAI / PROJECT / LOCATION / MONGO_URI / MONGO_DB）。
- **隔夜服务器 + 机器睡眠 = 假卡死**（websocket 断）→ 别 debug，杀掉重启 + 全新标签。
- 编辑 agent.py **巨型单引号 instruction 字符串**时，内部**只能用双引号**。
- 日志里 `Cloud Resource Manager API ... 403` traceback **无害**（SDK 兜底，照常跑）。
- 频繁 "(no text response)" = 查 aiohttp 版本（≥3.11），已修但换环境会复发。

---

## 架构关键事实（快速重建心智模型）

- **两层 Gemini**：编排器 root_agent（gemini-2.5-pro）+ 每个工具内部自己的 Gemini。慢（~23s/turn）是两层叠加的架构地板，流式进度让它"感觉"不卡。
- **resume_json 只存 session state**，绝不进 function-call 参数（治 MALFORMED 的根）。
- **大数据/确定性操作不穿 LLM**：PDF 前端本地抽文本；version history、版本 PDF 下载都是前端直连工具函数。
- **edit_resume 六种 operation**：set / add / remove（字段与列表）+ add_entry / remove_entry / move（结构）+ bullets 的 add/remove；白名单挡 schema 外路径；bullet 润色仍归 rewrite_bullet（带 rubric）。
- **load_resume_version 双模式**：agent 调用（有 ctx）→ 写回 state 当工作草稿、返回不带简历；代码调用（compare）→ 返回数据不碰 state。
- 模板 [config/templates/jakes_resume_en/template.html](config/templates/jakes_resume_en/template.html)：无 summary 字段（instruction 硬禁）；链接显示真实 URL。
- **docstring 也是 prompt**：工具 docstring 是 Gemini 的说明书，改能力必须同步 docstring + instruction（成对开关）。

---

## 待办（详见 DEVLOG 末尾）

- [ ] **部署清单（公网部署前必做）**：user_session 多用户接线（schema 有字段、前端有 uuid，差接线且别让 Gemini 填）、Clear history 按钮、.env → Secret Manager、Atlas IP 白名单、Playwright 进容器镜像、InMemorySessionService → 持久 session。结论维持：Cloud Run 比 AWS 摩擦小。
- [ ] PHASE 2 工作流不守（长对话跳澄清循环）——治本要把 PHASE 拆 sub-agent 状态机
- [ ] 真正提速（区别于流式"感觉快"）：关 thinking（省~1s）/ 首次上传直接调 parse 不走编排器（省~12s）
- [ ] `min_bullets_per_experience` 阈值 `<2` 改 `<3`（待定）；rewrite `has_quantification` 放宽（待定）
