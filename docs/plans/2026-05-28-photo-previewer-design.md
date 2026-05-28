# photo-previewer — 设计文档

> 日期：2026-05-28
> 状态：design 已确认，待落实施计划
> 关联：`photo-toolkit/scripts/layout_preview.py`、`openclaw-photo-agents-creator/templates/bootstrap-artist.md`、`RELEASING.md`

## 背景

photo-skills pipeline 末端目前由 `layout_preview.py --grid` 合成一张 `layout_preview.jpg`（九宫格）发给用户。在同一个 session 里反复尝试不同 style 的工作流下，静态合成图的局限是：

- 一次只能看一个 style，多 style 之间横向比对要么开多张图、要么合大图导致缩略
- 看不到"调色前 vs 调色后"的瞬时对照——现有 BEFORE|AFTER 模式占双倍屏幕
- 不便在手机上快速回看

## 目标

新增 `photo-previewer` skill，提供一个**按需启动的本地 HTTP server**，在浏览器（含移动端）里替代静态合成图，专注**单 session 内同组照片 × 多 style 横向比对**这一核心场景。

## 范围与非目标

**范围内**：

- **单 session 模式**（输入 `<session_dir>`，agent 自动启动用）：直入九宫格视图
- **浏览模式**（输入 `<output_root>/<RAW-root-name>/`，用户手动启动用）：列出该项目下所有 session，点进去看
- 模式切换由**输入路径深度自动判定**——含 `grading_params.json` = 单 session 模式；不含 = 浏览模式
- 多 style 切换（顶部 tab）
- 整网格点击切原图/调色（核心交互）
- 单图全屏 + 捏合缩放
- 移动端适配（触摸、左右滑、自适应网格）
- agent 自动启动并把 URL 回报给用户

**非目标**（明确不做）：

- **跨项目浏览**（即跨多个 `RAW-root-name`）—— 浏览模式仅扫单项目下的 session 列表
- 编辑功能（仅查看）
- RAW 现场解码（用 thumbnails 兜底，分辨率不对等是已知 trade-off）
- 实时 reload / websocket（session 是不可变快照）
- PWA、离线缓存、三指/四指手势

## 关键决定（设计依据）

| 议题 | 选项 | 决定 | 依据 |
|---|---|---|---|
| 预览粒度 | 单 session / 单项目 / 全 root | **路径深度自动判定**：session 路径=单 session 模式，项目根路径=浏览模式（列出该项目所有 session） | agent 用例零负担（仍传 session 路径）；用户手动想浏览历史时换个路径就行，无需 flag |
| 多 style 承载 | tab / 纵向堆叠 / 单 style / style 间切换 | 顶部 style tab | "点击切原图/调色"是单组九宫格内部行为，style 切换是外部导航，职责分离 |
| 部署形态 | 静态 HTML / 本地 server / 常驻 server | 本地按需 server | RAW 路径与 session 不在同一棵树，浏览器 file:// 跨目录限制；server 一句路由解决 |
| 启动方式 | agent 自动 / 给命令 / 完全独立 | agent 自动启动并给 URL | 真正"代替合成图发给你"——只换形态不增加用户负担 |
| 网格策略 | 严格 9 格 / 自适应 / 复用 layout_preview | 自适应 | "九宫格"是直觉表达，本质是"一屏看完整组"。1/2/2×2/3×3/4×4 阶梯 |
| 原图来源 | 复用 thumbnails / 现场 RAW 解码 / 混合 | 复用 thumbnails | 调试期分辨率差异不影响风格判断；rawpy + 缓存 + 并发会把复杂度抬一个量级 |
| 移动手势 | 最小 / 全开 | 全开（单击/双击/左右滑/捏合） | 用户明确诉求：在沙发上单手刷手机回看 |

## 架构

### 模块定位

新增 **第五个 skill**：`photo-previewer`，与 `photo-toolkit` / `photo-screener` / `photo-grader` 平级。

不改 `layout_preview.py` —— 静态合成图作为兜底（SSH / 无浏览器 / 远端 agent 容器场景）保留。

### 进程模型

- 单进程，stdlib only
- `http.server.ThreadingHTTPServer` + 自定义 `BaseHTTPRequestHandler`
- 启动期：单 session 模式扫一个 session；浏览模式只扫 session 元信息（`grading_params.json` 头），具体 graded/thumbnail 走懒扫描
- INDEX 内存字典——所有写操作仅发生在启动期或懒扫描首次访问时（用 `threading.Lock` 守护单 session 的"首次扫描"，避免并发请求重复扫）
- 前台运行，`Ctrl-C` 退出

### CLI

```bash
# 单 session 模式（agent 自动启动，pipeline 末端用）
python3 photo-previewer/scripts/preview.py <session_dir> [--port N] [--external-url URL] [--config PATH]

# 浏览模式（用户手动启动，回看历史）
python3 photo-previewer/scripts/preview.py <project_dir> [--port N] [--external-url URL] [--config PATH]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `<path>` | 必填 | 路径深度自动判定模式：含 `grading_params.json` 即视为 session；否则视为项目根，扫其下所有 `YYYYMMDD-HHMMSS/` 子目录 |
| `--port N` | 来自 config | 默认从 `config.toml` 读 `port`，未设则 0（OS 分配）。CLI > config > 0 |
| `--external-url URL` | 来自 config | 启动 banner 打印的用户可达 URL（用于反向代理场景）。CLI > config > internal `http://127.0.0.1:<port>/` |
| `--config PATH` | `<skill>/config.toml` 或 `<repo-root>/config.toml` | 显式指定 config.toml 路径 |

**模式判定逻辑**（启动期 fail-fast 前置校验）：

1. 路径必须存在且为目录，否则 fail-fast
2. 若 `<path>/grading_params.json` 存在 → **单 session 模式**
3. 否则扫 `<path>/*/grading_params.json`，匹配到 ≥1 个 → **浏览模式**
4. 0 个匹配 → fail-fast，提示路径既不是 session 也不是项目根

启动后 stdout 打印 `Preview ready: http://127.0.0.1:54321/`，stderr 打印日志（含模式标识：`mode=session` 或 `mode=browse, sessions=N`）。

### 数据流（启动期扫描）

**单 session 模式**：

1. 读 `<session_dir>/grading_params.json` → `[{file, style, ...}, ...]`
2. 按 `style` 字段 group → `styles = {"暖春丝滑": [item1, item2, ...], ...}`
3. 在 `<session_dir>/graded/` 复用 `layout_preview.py` 已验证的 stem 匹配逻辑（`DSC_0001_暖春丝滑.jpg` → 原 stem `DSC_0001` + style `暖春丝滑`）反查 `(style, stem) → graded_jpg_path`
4. 在 toolkit `convert.py` 约定的 thumbnail 位置（`{raw_root}/thumbnails/`）查找 `stem → thumbnail_path`
5. 缺失项标 `missing` flag，不阻塞启动；启动期日志打印缺失统计

**浏览模式**：

1. 扫 `<project_dir>/*/grading_params.json`，每个匹配到的子目录视为一个 session
2. 对每个 session 走单 session 模式的步骤 1-5，结果存进 `INDEX[session_id]`（`session_id` = 子目录名，例如 `20260322-143052`）
3. **不预扫所有 session 的图片细节**（只读 grading_params.json 拿元信息）；用户实际点进某个 session 时**懒扫描**该 session 的 graded/thumbnail，结果缓存进 `INDEX`。这样 100 个 session 的项目启动也只是读 100 个 JSON，秒级
4. 顶层 `INDEX[<session_id>] = {scanned: false, params_path, graded_dir, ...}`，单 session 模式下 INDEX 永远只有一项

### HTTP 路由

| 方法+路径 | 单 session 模式 | 浏览模式 |
|---|---|---|
| `GET /` | 直入九宫格视图（前端读 `default_session`） | 列出所有 session（按时间倒序），点击由前端 JS 客户端跳转加载该 session（不刷新 URL） |
| `GET /api/manifest` | 返回当前（唯一）session manifest | 返回 session 列表元信息 |
| `GET /api/manifest/<session_id>` | 仅当 id 匹配时返回；否则 404 | 返回该 session 的完整 manifest（含 styles 与 cells），首次触发懒扫描 |
| `GET /img/<session_id>/graded/<style>/<stem>` | 仅当 id 匹配 | graded jpg 文件流 |
| `GET /img/<session_id>/original/<stem>` | 仅当 id 匹配 | thumbnail 文件流；缺失返回 404 |

**统一带 `<session_id>` 的路由 schema**：单 session 模式下也用 `/s/<id>/`，只是 `<id>` 唯一。这样前端代码两个模式共用同一套，不需要分支；agent 启动时给的 URL 是 `http://127.0.0.1:54321/`（根路径自动判定/重定向到唯一 session 视图）。

### 前端工作流

- 加载 → `fetch('/api/manifest')` → 渲染 style tab + 当前 tab 的网格
- 点 tab：切数据源、切 mode 回 `graded`
- 点网格区：toggle `mode` 状态（`graded` ↔ `original`），所有 cell 同步 swap `<img src>`
- 预加载：tab 切换时立刻 `new Image()` 预加载该 tab 全部 graded + original，确保切换瞬时
- 不轮询、不 websocket、不 fade transition

### 自适应网格

桌面端：

| 张数 | 列数 |
|---|---|
| 1 | 1 |
| 2 | 2 |
| 3-4 | 2 |
| 5-9 | 3 |
| 10-16 | 4 |
| >16 | 4（滚动） |

移动端（`max-width: 600px` media query 强制覆盖）：3-9 张走 2 列，>9 走 2 列滚动。

## 交互细节

### 模式分层

避免手势冲突的核心：

**网格模式**（默认）

- 单击：全网格切原图/调色
- 双击 cell：进入该 cell 的全屏单图模式
- 左右滑（deltaX > 50px）：切上/下一个 style
- 垂直滑（deltaY > 30px）：放过给浏览器（页面滚动）
- 不允许缩放（`touch-action: manipulation`）

**全屏单图模式**

- 单击：切这一张的原图/调色
- 双击：退出回网格
- 捏合：自由缩放（`touch-action: pinch-zoom`）
- 左右滑：切到组内上/下一张
- ESC（桌面）/ 点遮罩：退出

实现：用 `<dialog>` + `dialog.showModal()` 原生支持。

### 单击 vs 双击判定

- 桌面：`click` + `dblclick` 原生事件，零延迟
- 移动：单一 `click` + 250ms 延迟计时——首次 click 不立即执行，等 250ms 内有无第二次。这是已知 trade-off，桌面无影响

### 键盘快捷键

- `空格`：切原图/调色
- `←` / `→`：切 style tab
- `1`-`9`：跳到对应 style（≤9 个时）
- `ESC`：退出全屏单图

### 视觉

- Cell 纯图，无烧字标签
- 顶部固定一行 mode 指示器：`MODE: GRADED` / `MODE: ORIGINAL`
- Style tab 显示 `<style 名> (<张数>)`，例如 `暖春丝滑 (7)`
- 切换无 fade（CSS transition 任何过渡都违背"瞬间"诉求）

## 错误处理

| 故障 | 行为 |
|---|---|
| 输入路径不存在 / 不是目录 | server fail-fast，stderr 提示 |
| 输入路径既不是 session（无 `grading_params.json`）也不是项目根（其下无 `*/grading_params.json`） | server fail-fast，提示路径预期 |
| 单 session 模式：`graded/` 目录空 | server fail-fast |
| 浏览模式：某个子 session `graded/` 空 | 懒扫描时该 session 标 `broken: true`，列表页显示但点进去显示错误信息；不影响其他 session |
| 某张 graded jpg 丢失 | manifest 标 `missing: true`，前端深色占位 + "(graded missing)"；其他 cell 不受影响 |
| 某张 thumbnail 丢失 | `/img/<session_id>/original/<stem>` 返回 404，前端在 original mode 下占位 + "(thumbnail missing — run convert.py first)" |
| `--port` 显式指定但被占 | fail-fast，提示用 `--port 0` |

per-file isolation 与现有 skill 一致。

## 依赖

| 层 | 依赖 |
|---|---|
| Python | stdlib only：`http.server`、`socketserver`、`json`、`pathlib`、`webbrowser`、`urllib.parse`、`mimetypes`、`socket`。`tomllib`（3.11+）/ `tomli` fallback 仅读 `config.toml` 时用 |
| 前端 | 零外部资源，HTML/CSS/JS 全部 inline 在 `INDEX_HTML` 字符串常量 |
| 系统 | 一个空闲 TCP 端口 |

## 目录结构

```
photo-previewer/
├── SKILL.md
├── VERSION
├── CHANGELOG.md
├── config.example.toml      # 扁平字段 port=0, external_url=""
├── requirements.txt         # 空文件 + 注释 "# stdlib only, no runtime deps"
└── scripts/
    ├── preview.py           # 主脚本 ~500 行
    ├── test_preview.py      # 单元 + 集成测试
    └── setup_deps.sh        # 仅检查 python3 ≥ 3.8
```

## 测试

### 单元

`preview.py` 拆出纯函数：

- `detect_mode(path) -> Literal["session", "browse"]`
- `discover_sessions(project_dir) -> list[SessionMeta]`
- `build_manifest(session_dir) -> dict`
- `match_graded_to_style(filename) -> (stem, style)`
- `grid_columns_for(n) -> int`

每个 4-6 条 `unittest` 用例，放 `photo-previewer/scripts/test_preview.py`。

### 集成

构造两套 fixture：

1. **单 session**：2 张照片 × 2 style + 假 thumbnails，启动 server 验 `/`、`/api/manifest/<id>`、`/img/<id>/graded/...`
2. **浏览模式**：1 个项目根下 3 个 session（其中 1 个 `graded/` 空触发 `broken: true`），启动 server 验 `/` 列表页 JSON、点进合法 session 拿到 manifest、点进 broken session 拿到错误信息

### 手动检查清单（写进 SKILL.md）

桌面单击/双击/键盘 → 移动单击/双击/左右滑/捏合 → style 不足 3 时左右滑边界 → 单 style 时 tab 区域 → >16 张滚动 → 各类缺失场景。

## Pipeline 接入

### bootstrap-artist 模板

在 `openclaw-photo-agents-creator/templates/bootstrap-artist.md` 中"调用 `layout_preview.py --grid` 生成 jpg 并发给用户"那段**下方追加**：当 `photo-previewer` 可用时优先启动 server，把 URL 发给用户。**保留** layout_preview 作为兜底。

### CODEBUDDY.md

Pipeline Flow 末端追加一节 "Preview" 分支，与 "Timelapse Workflow" 同级。

### sync_versions.sh

`DEFAULT_SKILLS` 数组加入 `photo-previewer`，让发布工作流自动覆盖。

### photo-previewer/SKILL.md triggers

明确"调试期同 session 多 style 横向比对、移动端回看"，让 agent 知道该选它而非 layout_preview。

## 版本与发布

按 `RELEASING.md` 策略 C：

- 首发 `1.0.0`，走"场景 A — 单 skill"流程
- 是否同步 bump `openclaw-photo-agents-creator` 取决于 bootstrap 模板的修改是否被认为是 creator 的接口变更——按 §三 checklist 决定

## 风险与待解

| 风险 | 缓解 |
|---|---|
| RAW 用户的 thumbnail 分辨率与 graded 不对等，切换时"原图糊一点" | 已接受为 trade-off；要看像素级细节本应用 RawTherapee viewer。SKILL.md 显式说明 |
| 移动端单击 250ms 延迟感 | 已接受为 trade-off；桌面无影响。后续若用户反馈强烈再考虑用 `pointerdown` + 自定义判定 |
| `<session_dir>` 路径含中文/空格 | URL 编码 + `Path.resolve()`；测试 fixture 含中文路径用例 |
| 同时启动多个 preview server | 端口各自分配（`--port 0`），互不影响。但浏览器 tab 切换时只看到 URL 难分辨——SKILL.md 写一笔，必要时未来在页面 title 加 session 名 |
| Agent 启动 server 后没退出，残留进程 | bootstrap 模板要求 agent 用 `&` 后台启动，session 结束时显式 kill；进程自身不实现"超时自杀"（YAGNI） |

## 后续

- 设计文档落地后，进 `writing-plans` 出实施计划，分步骤实现
- 实施计划应至少覆盖：skill 骨架搭建 → 启动期扫描 → HTTP 路由 → 前端骨架 → 移动手势 → 测试 → bootstrap 模板接入 → 发布
