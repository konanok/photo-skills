# photo-previewer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> **⚠ Project rule (overrides skill defaults):** Never `git commit` / `git push` etc. without an explicit per-step "提交" / "OK to commit" from the user. Every commit step below MUST stop and ask before running.

**Goal:** 新增第五个 skill `photo-previewer`，提供本地 HTTP server 替代 `layout_preview.py` 静态合成图作为 pipeline 末端预览，支持单 session 模式（agent 自动启动）和浏览模式（用户手动启动看历史 session）。

**Architecture:** stdlib-only Python `http.server.ThreadingHTTPServer`，启动期按输入路径深度自动判定模式，前端单页应用 inline 在 `INDEX_HTML` 字符串常量里。设计文档：`docs/plans/2026-05-28-photo-previewer-design.md`。

**Tech Stack:** Python 3.8+ stdlib（`http.server` / `socketserver` / `unittest`），HTML/CSS/JS（无构建工具，无外部资源），shell（setup_deps）。

---

## Amendments（实施后的设计调整）

实施完成后用户陆续提了 3 条调整，已 in-place 改了代码与文档；本节只列改动来源，不重写正文 task 描述（保留作为历史记录）：

| 日期 | 决定 | 影响范围 |
|---|---|---|
| 2026-05-28 | **不发布到 ClawHub**，photo-previewer 是仓库内部工具 | 删 VERSION/CHANGELOG/openclaw frontmatter；从 sync_versions.sh DEFAULT_SKILLS 去掉；Task 5.3 取消（见下方该 task 段） |
| 2026-05-28 | **删 mobile_breakpoint_px** 与 **auto_open_browser** 配置项；移动端走"3 列上限"而不是"2 列" | 删 `grid_columns_for_mobile()` 纯函数与对应测试；INDEX_HTML 的 CSS media query 改 `repeat(min(3, var(--cols-desktop, 3)), 1fr)`；删 webbrowser.open 调用与 `--no-browser` CLI 参数 |
| 2026-05-28 | **加 config.toml 配置支持**：扁平 `port` + `external_url` 两字段。bind 仍 127.0.0.1，对外暴露由部署方反代（nginx / OpenClaw gateway）负责 | 新增 `load_config()`、`--config` CLI、`--external-url` CLI；优先级 CLI > config > 内置默认；新增 4 个 config-related 测试 |

设计文档（`2026-05-28-photo-previewer-design.md`）已同步反映以上变化。

---

## 前置约定

- **venv**：所有 Python 命令假设 `source .venv/bin/activate` 已执行
- **测试运行**：`python3 -m unittest photo-previewer.scripts.test_preview -v`，从仓库根
- **fixture**：`tempfile.TemporaryDirectory()` 临时造，不依赖任何外部 RAW
- **commit**：每个 commit 步骤先停下问"OK 提交吗？"，得到明确 yes 才跑

---

## Phase 0：骨架与依赖检查

### Task 0.1：创建 skill 目录骨架

**Files:** Create: `photo-previewer/{SKILL.md, VERSION, CHANGELOG.md, config.example.toml, requirements.txt, scripts/setup_deps.sh, scripts/preview.py, scripts/test_preview.py}`

**Steps:**

1. `mkdir -p photo-previewer/scripts`
2. 写 `SKILL.md` —— frontmatter 包含 `name / description / version: 1.0.0 / metadata.openclaw.{homepage, emoji: 🖼️, requires.bins: [python3]}`；正文说明两种模式 CLI、Triggers、Requirements、配套版本要求
3. 写 `VERSION` —— `echo "1.0.0" > photo-previewer/VERSION`
4. 写 `CHANGELOG.md` —— `[Unreleased]` 段 + `[1.0.0] - 2026-05-28` 段，Added 写"Initial release: web-based preview server with single-session and browse modes."
5. 写 `config.example.toml` —— `[previewer]` 段含 `default_port=0`、`auto_open_browser=true`、`mobile_breakpoint_px=600`
6. 写 `requirements.txt` —— 仅注释行 `# stdlib only, no runtime deps`
7. 写 `setup_deps.sh` —— 检查 python3 在 PATH 与版本号，打印 `✓ photo-previewer uses stdlib only — no pip install needed`
8. 写 `preview.py` 占位：shebang + `"""docstring"""` + `if __name__ == "__main__": pass`
9. 写 `test_preview.py` 占位：单个 `Placeholder.test_placeholder` 用例
10. `chmod +x` 两个脚本，跑 `bash photo-previewer/scripts/setup_deps.sh`、`python3 -m unittest photo-previewer.scripts.test_preview -v`，预期都通过
11. 跑 `bash scripts/sync_versions.sh photo-previewer --check`，预期 ✓
12. **Commit（停下问）**：`git commit -m "feat(previewer): scaffold skill directory structure"`

---

### Task 0.2：把 photo-previewer 加进 sync_versions.sh

**Files:** Modify: `scripts/sync_versions.sh:44-49`

**Steps:**

1. 读现有 `DEFAULT_SKILLS` 数组（4 个 skill）
2. 在 `"openclaw-photo-agents-creator"` 后追加一行 `"photo-previewer"`
3. 跑 `bash scripts/sync_versions.sh --check`，预期 5 个 skill 全 ✓
4. **Commit（停下问）**：`git commit -m "chore: add photo-previewer to sync_versions.sh DEFAULT_SKILLS"`

---

## Phase 1：纯函数（启动期扫描的核心逻辑）

每个 task 都按 TDD：① 写测试 → ② 跑 fail → ③ 写最小实现 → ④ 跑 pass → ⑤ commit（停下问）。

### Task 1.1：`detect_mode(path) -> Literal["session", "browse"]`

**Behavior:**

- `<path>/grading_params.json` 存在 → `"session"`
- 否则若 `<path>/*/grading_params.json` 至少有一个 → `"browse"`
- 路径不存在 → `FileNotFoundError`；非目录 → `NotADirectoryError`；都不匹配 → `ValueError`

**Tests (5 cases):** session 模式、browse 模式、neither raises ValueError、不存在 raises FileNotFoundError、文件 raises NotADirectoryError

**Commit msg:** `feat(previewer): add detect_mode() with path-depth detection`

---

### Task 1.2：`match_graded_to_style(filename) -> tuple[str, str | None]`

**Behavior:** `Path(filename).stem.rpartition("_")` —— 无下划线时返回 `(stem, None)`；有则 `(head, tail)`

**Tests (5 cases):**

- `"DSC_0001_暖春丝滑.jpg"` → `("DSC_0001", "暖春丝滑")`
- `"001_DSC_0001_暖春丝滑.jpg"` → `("001_DSC_0001", "暖春丝滑")`
- `"DSC_0001_warm_spring.jpg"` → `("DSC_0001_warm", "spring")`（rpartition 一次）
- `"photo.jpg"` → `("photo", None)`
- `.jpeg` 扩展名同样工作

**Commit msg:** `feat(previewer): add match_graded_to_style() filename parser`

---

### Task 1.3：`grid_columns_for(n)` 与 `grid_columns_for_mobile(n)`

**Behavior:**

- 桌面：`n<=1→1, <=4→2, <=9→3, else→4`
- 移动：`n<=1→1, else→2`

**Tests (4 cases):** 桌面分桶、桌面 0、移动分桶、移动 0

**Commit msg:** `feat(previewer): add grid column calculators`

---

### Task 1.4：`build_session_manifest(session_dir) -> dict`

**Behavior:**

1. 读 `session_dir/grading_params.json`，缺失 `FileNotFoundError`
2. 校验 `session_dir/graded/` 存在且非空，否则 `ValueError`
3. 扫 graded 目录，按 `match_graded_to_style` 建索引 `(stem, style) -> filename`
4. 遍历 params，每条产出 cell：`{stem, graded_filename, graded_missing, original_path}`
5. 处理子目录前缀变体（actual key `001_DSC_0001` 也匹配 params 中的 `DSC_0001`）—— 通过遍历 actual 找 `a_stem.endswith("_" + stem)` fallback
6. 返回 `{session_id, styles: [...], cells_by_style: {style: [cells]}}`

**Tests (4 cases):**

- basic shape：2 styles × 2 photos，断言 styles 集合、cells 数、cell 字段、`graded_missing=False`
- missing graded file：删一张 → 该 cell `graded_missing=True`
- empty graded dir → raises ValueError
- no grading_params.json → raises FileNotFoundError

**Commit msg:** `feat(previewer): add build_session_manifest() core scanner`

---

### Task 1.5：`discover_sessions(project_dir) -> list[dict]`

**Behavior:**

- 扫 `project_dir/*/grading_params.json`，每个匹配子目录返回 `{session_id, path}`
- 按 `session_id` 字典序倒序（YYYYMMDD-HHMMSS 等价于时间倒序）
- 项目根不存在或非目录 → 返回空列表

**Tests (2 cases):** 列出 3 个 session 倒序排（其中 1 个 `no-params` 子目录不应入选）、空目录返回 `[]`

**Commit msg:** `feat(previewer): add discover_sessions() for browse mode`

---

## Phase 2：HTTP server 骨架

### Task 2.1：CLI 入口 + 模式分发 + fail-fast

**Files:** Modify `preview.py` + `test_preview.py`

**Behavior:**

- `argparse` 解析：positional `path`、`--port` (default=0)、`--no-browser` (action=store_true)
- `main(argv)` 调 `detect_mode(path)`，捕获 `(FileNotFoundError, NotADirectoryError, ValueError)` → 打 stderr `error: <msg>`、return 2
- 成功后打印 `mode=<mode> path=<path>` 到 stderr，return 0（**这一步先不真起 server**）

**Tests (4 cases, subprocess 调真脚本):**

- 无参 → 非零退出，stderr/stdout 含 "usage"
- 不存在路径 → 非零退出
- 路径是文件 → 非零退出
- 路径是空目录（neither session nor root）→ 非零退出，stderr 含 "session"

**Commit msg:** `feat(previewer): add CLI entry with mode detection and fail-fast`

---

### Task 2.2：HTTP server 启动 + INDEX 构建

**Files:** Modify `preview.py` + `test_preview.py`

**Behavior:**

1. `build_app(path, mode) -> dict` —— session 模式立即扫 manifest 缓存；browse 模式 list sessions 但每个 manifest=None（懒加载）
2. `make_handler(app)` 返回 closure 进 `BaseHTTPRequestHandler` 子类：含 `_json/_html/_serve_file` 工具方法、`do_GET` 暂只实现 `/api/manifest` 返回 `{"mode": app["mode"]}`
3. `start_server(app, port=0) -> (server, url)` —— 绑 127.0.0.1，返回 ThreadingHTTPServer + URL；用 daemon Thread 跑 `serve_forever`
4. `main()` 调用：`build_app` → 直接 `ThreadingHTTPServer((127.0.0.1, args.port), make_handler(app))` 主线程 `serve_forever()`，捕获 `OSError`（端口占用）→ stderr error + return 2，捕 `KeyboardInterrupt` 优雅退出

**Tests (1 集成 case):** 单 session fixture，调 `build_app + start_server`，curl `/api/manifest` 200 + JSON 含 `mode=session`，`server.shutdown()` 清理

**Commit msg:** `feat(previewer): http server with INDEX construction and basic /api/manifest`

---

### Task 2.3：完整路由实现

**Files:** Modify `preview.py` + `test_preview.py`

**Routes:**

| 路径 | 行为 |
|---|---|
| `GET /` 或 `/index.html` | 返回 `INDEX_HTML`（占位 `<!doctype html><title>preview</title>`，Phase 3 填实） |
| `GET /api/manifest` | session 模式：`{mode, default_session_id, session: <full manifest>}`；browse 模式：`{mode, sessions: [{session_id}, ...]}` |
| `GET /api/manifest/<sid>` | 调 `_ensure_session_scanned(app, sid)` 懒扫描；未知 sid 返回 404 |
| `GET /img/<sid>/graded/<style>/<stem>` | 从 manifest 找 cell，serve `session_path/graded/<filename>`；找不到 404 |
| `GET /img/<sid>/original/<stem>` | 调 `_find_thumbnail(session_path, stem)` 从 grading_params 读原始 RAW 路径，找 `<raw_parent>/thumbnails/<stem>.jpg`；找不到 404 |

**关键辅助函数：**

- `_ensure_session_scanned(app, sid)` —— 用 `entry.setdefault("_lock", threading.Lock())` 守护首次扫描，扫描失败 → `entry["manifest"] = {"error": ..., "broken": True}`
- `_find_thumbnail(session_path, stem)` —— 读 `session_path/grading_params.json`，匹配 `Path(item["file"]).stem == stem`，返回 `Path(item["file"]).parent / "thumbnails" / (stem + ".jpg")` 若存在；`.jpeg` 同样尝试

**Tests (6 cases):** browse fixture (2 sessions × 1 style × 1 photo)：

- `/api/manifest` browse 模式列出 2 session 倒序
- `/api/manifest/<sid>` 200 + `cells_by_style` 含 style "S"
- `/api/manifest/nonexistent` 404
- `/img/<sid>/graded/S/A` 200 + body 等于 fixture bytes
- `/img/<sid>/graded/S/NOPE` 404
- `/img/<sid>/original/A` 404（fixture 没建 thumbnail）

**Commit msg:** `feat(previewer): full HTTP route table with lazy session scan`

---

## Phase 3：前端

### Task 3.1：HTML/CSS 骨架（无 JS 行为）

**Files:** Modify `preview.py` (`INDEX_HTML` 常量) + `test_preview.py`

**HTML 必含：**

- `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`
- `<div id="topbar">` 包 `<div id="mode-indicator">MODE: GRADED</div>` + `<div id="style-tabs"></div>`
- `<div id="grid"></div>`
- `<dialog>` 元素留空（Task 3.3 用）

**CSS 关键：**

- `:root { --bg:#111; --fg:#eee; --accent:#4af; --gap:4px }`
- 全局 `* { box-sizing:border-box; touch-action:manipulation }`
- `html,body { background:var(--bg); color:var(--fg); height:100%; overflow:hidden }`
- `.cell { aspect-ratio:3/2; background:#000; overflow:hidden; position:relative }`
- `.cell img { width:100%; height:100%; object-fit:cover }`
- `.cell.missing::after { content:attr(data-missing); position:absolute; inset:0; display:flex; ... }`
- `@media (max-width: 600px) { #grid { grid-template-columns: repeat(var(--cols-mobile, 2), 1fr) !important } }`

**Tests (1 case):** curl `/`，HTML 含 `id="grid"`、`id="mode-indicator"`、`id="style-tabs"`、`width=device-width`

**Commit msg:** `feat(previewer): HTML/CSS skeleton with mode indicator and tab bar`

---

### Task 3.2：JS — manifest 加载、tab 渲染、网格渲染、graded↔original 切换、键盘

**Files:** Modify `preview.py` (`INDEX_HTML` 内 `<script>`)

**JS 模块结构：**

- `state = {mode, defaultSessionId, sessionManifest, currentStyle, imgMode}`
- `loadManifest()` —— fetch `/api/manifest`，按 `data.mode` 分发到 `initSessionView()` 或 `initBrowseList()`
- `initBrowseList(sessions)` —— 把 `#grid` 改成单列 list，每条 `<a>` 点击触发 `loadSession(sid)`；隐藏 style tabs；`#mode-indicator` 改 "BROWSE"
- `loadSession(sid)` —— fetch `/api/manifest/<sid>`，成功后 `state.sessionManifest = ...`、`mode='session'`、`initSessionView()`
- `initSessionView()` —— 设 `currentStyle = manifest.styles[0]`、`imgMode='graded'`，调 `renderTabs() + renderGrid() + preloadAll()`
- `renderTabs()` —— 清空 `#style-tabs`，每 style 一个 `.tab`，文本 `${style} (${cells.length})`，active class 高亮当前；点击事件 `e.stopPropagation()` + 切 style + 重渲
- `gridColsDesktop(n)` —— 同 Phase 1.3 桌面公式（JS 复制）
- `renderGrid()` —— 设 `gridTemplateColumns: repeat(${cols}, 1fr)`、`--cols-mobile`，遍历 cells 建 `.cell` div：
  - graded mode + `cell.graded_missing` → `.cell.missing` + `data-missing` 文字
  - 否则 `<img src=imgUrl(cell)>`，`onerror` 把 cell 标 missing
- `imgUrl(cell)` —— graded → `/img/<sid>/graded/<style>/<stem>`；original → `/img/<sid>/original/<stem>`，全部 `encodeURIComponent`
- `updateModeIndicator()` —— 文本 `MODE: GRADED/ORIGINAL`，class `original` 切换
- `toggleMode()` —— 翻 `imgMode`，调 `renderGrid()`
- `preloadAll()` —— 当前 style 全部 cells × {graded, original} 各 `new Image(); img.src = ...`
- `document.getElementById('grid').addEventListener('click', toggleMode)`
- `window.addEventListener('keydown', ...)` —— 空格 toggle、`←/→` 切 tab、`1-9` 跳 style
- 启动末调 `loadManifest()`

**Tests (1 case):** `INDEX_HTML` 字符串包含 `loadManifest`、`renderGrid`、`toggleMode`、`addEventListener('click'`

**Commit msg:** `feat(previewer): JS for tabs, grid, graded↔original toggle, keyboard`

---

### Task 3.3：移动手势 — 左右滑切 style + 双击全屏

**Files:** Modify `preview.py` (`INDEX_HTML` 内 `<script>`)

**新增 JS：**

- 触摸滑判定：`touchstart` 记 X/Y/T，`touchend` 算 dx/dy/dt；`|dx|>50 && |dx|>|dy|*1.5 && dt<600` → 切 style 上/下一个，`e.preventDefault()`
- 全屏 dialog：`<dialog id="fs-dialog">` 含 `<img id="fs-img" style="touch-action:pinch-zoom">`，`width:100vw;height:100vh;object-fit:contain`
- `openFullscreen(cell)` —— 设 `fsCell/fsMode`、`dlg.showModal()`
- 全屏 dialog click → 切 `fsMode`，重设 `fs-img.src`
- 全屏 dialog dblclick → `dlg.close()`
- 网格 dblclick → 找 `e.target.closest('.cell')`，算 index，`openFullscreen(cells[idx])`，`e.stopPropagation()`

**Tests (1 case):** `INDEX_HTML` 含 `touchstart`、`touchend`、`dblclick`、`<dialog`

**Commit msg:** `feat(previewer): mobile swipe + fullscreen single-image dialog`

---

## Phase 4：联动既有 pipeline

### Task 4.1：bootstrap-artist 模板加 preview 启动指令

**Files:** Modify `openclaw-photo-agents-creator/templates/bootstrap-artist.md`

**Steps:**

1. `grep -n "layout_preview" openclaw-photo-agents-creator/templates/bootstrap-artist.md` 找到现有调用段
2. 在该段下方追加 photo-previewer 优先调用段。要点：
   - 当 `photo-previewer/scripts/preview.py` 存在时，优先后台启动：`python3 photo-previewer/scripts/preview.py <session_dir> --no-browser &`
   - 捕获 stdout 第一行的 URL（形如 `Preview ready: http://127.0.0.1:54321`），作为给用户的预览链接发出
   - 仍然调用 `layout_preview.py --grid` 生成 jpg 作为兜底
   - server pid 记入 session 的 `progress.json`，session 结束（agent shutdown 钩子）时 `kill <pid>`
3. **Commit（停下问）**：`git commit -m "feat(creator): bootstrap-artist invokes photo-previewer when available"`

---

### Task 4.2：CODEBUDDY.md 加 Preview 分支

**Files:** Modify `CODEBUDDY.md`

**Steps:**

1. 在 Pipeline Flow 末端的 Timelapse Workflow 同级加一节 "Preview"。要点：
   - 单 session 模式 / 浏览模式的 CLI 示例
   - 与 `layout_preview.py` 的关系（preview = 交互式主入口，layout_preview = 静态兜底）
   - 何时该选哪个（有浏览器 → preview；SSH/无浏览器/agent 远端容器 → layout_preview）
2. **Commit（停下问）**：`git commit -m "docs: add photo-previewer to CODEBUDDY.md pipeline flow"`

---

## Phase 5：发布前收尾

### Task 5.1：手动验收清单（写进 SKILL.md，跟 5.2 合并 commit）

清单条目（追加到 `photo-previewer/SKILL.md` 的 "Manual verification" 段）：

**桌面：**

- [ ] 单 session：直入九宫格、style tab 切换、空格切原图、`←/→` 切 tab、`1-9` 跳 style、双击进全屏、ESC 退全屏
- [ ] 浏览模式：根 `/` 列出所有 session、点进合法 session 看到网格、点进 broken session 看到错误信息
- [ ] graded 缺失/thumbnail 缺失场景的占位文字正确

**移动（实机或浏览器设备模拟器）：**

- [ ] 网格 ≤9 张时 2 列
- [ ] 单击网格切原图/调色
- [ ] 左右滑切 style，纵向滑不触发
- [ ] 双击进全屏，全屏内单击切原图/调色，双击退出，捏合可缩放
- [ ] tab 区域单击切 style 不会顺手把网格切成 original

**边界：**

- [ ] 11 张：桌面 4 列、移动 2 列滚动
- [ ] 单 style：tab 仅 1 个，左右滑边界不报错
- [ ] 中文路径：`<session_dir>` 含中文，URL encoding 正确

---

### Task 5.2：版本一致性 final check + SKILL.md 收尾

**Files:** Modify `photo-previewer/SKILL.md`（追加 Manual verification 段）

**Steps:**

1. 把 Task 5.1 清单贴进 `SKILL.md` "Manual verification" 段
2. 跑 `bash scripts/sync_versions.sh --check`，预期 5 个 skill 全 ✓
3. 跑 `python3 -m unittest discover -s photo-previewer/scripts -p "test_*.py" -v`，预期全 pass
4. **Commit（停下问）**：`git commit -m "docs(previewer): add manual verification checklist to SKILL.md"`

---

### Task 5.3：发布 ~~（独立流程，必须用户在场）~~ — **取消**

**决定（2026-05-28，用户拍板）**：photo-previewer **不发布到 ClawHub**，
作为仓库内部本地工具使用。版本一致性校验也不参与（`scripts/sync_versions.sh`
的 `DEFAULT_SKILLS` 不含此 skill）。

**连锁动作（已完成）**：

- 删除 `photo-previewer/VERSION` 与 `photo-previewer/CHANGELOG.md`
- 删除 `photo-previewer/SKILL.md` frontmatter 的 `metadata.openclaw.*` 段
  （保留 `version: 1.0.0` 作为人类可读标签，不严格 semver）
- `scripts/sync_versions.sh` `DEFAULT_SKILLS` 数组从 5 改回 4
- `RELEASING.md` 顶部加说明
- `CODEBUDDY.md` Overview 标注 photo-previewer is repo-only

**未来若要改主意发布**：恢复上述被删/被改的内容，重新加入 `DEFAULT_SKILLS`，
然后按 RELEASING.md 场景 A 走（首发 1.0.0）。

---

## 完成定义

- 4 个发布 skill 在 `sync_versions.sh --check` 全 ✓
- `photo-previewer/scripts/test_preview.py` 全 pass
- 手动验收清单全 ✓
- bootstrap-artist 模板已接入 preview 启动逻辑
- CODEBUDDY.md 已记录新 skill
- ~~ClawHub 已发布 1.0.0~~ — 不发布
