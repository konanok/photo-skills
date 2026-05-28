---
name: photo-previewer
version: 1.0.0
# Note: photo-previewer is **not** published to ClawHub — it is a repo-only
# local tool. The `version:` field above is a human-readable label only;
# scripts/sync_versions.sh does not check this skill against a VERSION file.
description: |
  Web-based preview server for photo grading sessions.
  Replaces static layout_preview.jpg with an interactive browser UI supporting
  per-style tabs, full-grid graded↔original toggle, and mobile gestures.

  Use when the user wants to:
  - Quickly preview a freshly graded session in the browser (replaces sending a static
    composite jpg)
  - Compare multiple styles side-by-side within a single grading session
  - Re-visit historical sessions of a project from a phone or laptop
  - Tap once to flip the entire grid between graded and original thumbnails for
    instant before/after judgement

  Triggers: User mentions previewing graded photos, comparing styles, viewing a session
  in the browser, mobile preview, replacing layout_preview.jpg with an interactive UI.

  Dependencies:
    Python: stdlib only (Python 3.8+); tomllib for config.toml on 3.11+, optional tomli
            on 3.8-3.10.
    Network: one free TCP port on 127.0.0.1.
    Check: bash scripts/setup_deps.sh
---

# Photo Previewer

启动一个本地 HTTP server，在浏览器里查看 `photo-grader` 调色后的成片。两种模式由
**输入路径深度自动判定**：

- **单 session 模式** —— 路径含 `grading_params.json`，直入九宫格视图。
  PhotoArtist agent 在 pipeline 末端用，替代 `layout_preview.py --grid` 的静态合成图。

  ```bash
  python3 scripts/preview.py <session_dir> [--port N] [--external-url URL] [--config PATH]
  ```

- **浏览模式** —— 路径不含 `grading_params.json`，但其子目录含。列出该项目下所有
  session（按时间倒序），点进去看任意一个。供用户手动回看历史。

  ```bash
  python3 scripts/preview.py <project_dir> [--port N] [--external-url URL] [--config PATH]
  ```

`--port` 默认从 `config.toml` 的 `port` 字段读，未设则 OS 自动分配空闲端口。
`--external-url` 是用户最终看到的 URL（用于反向代理场景），未设时打印内部
`http://127.0.0.1:<port>/`，仅适合本地调试。两个值都可以在 `config.toml`
配（见 `config.example.toml`），CLI 优先于 config，config 优先于内置默认。

## 部署形态

photo-previewer **始终 bind `127.0.0.1`**，自身不对公网开放。把 server 暴露给
端用户是部署方的事，典型方式：

- **本地调试**：直接访问 `http://127.0.0.1:<port>/`（或 SSH port forward）
- **OpenClaw 云部署**：把服务器上的 nginx / OpenClaw gateway / k8s ingress 配
  一条 `/preview/...` → `http://127.0.0.1:<port>/` 的反代规则，把外部 URL
  填到 `config.toml` 的 `external_url`。Agent 启动时打印的就是这个 URL，
  直接发给用户。
- **agent 透传**：bootstrap 模板里的 Step 7（PhotoArtist）会读 server stdout
  第一行 `Preview ready: <url>`，把 `<url>` 原样转给用户。所以 agent 不需要
  知道反向代理细节，只需要 `external_url` 已经在 config 里配好。

## 核心交互

- 点网格任意位置 → 9 张瞬间整体切到原图；再点 → 切回调色版
- 顶部 style tab 切换不同 style 的网格
- 双击 cell 进入全屏单图模式（捏合可缩放，再双击退出）
- 移动端左右滑切 style；纵向滑不触发，让浏览器正常滚动
- 键盘：空格 = 切原图/调色，`←/→` = 切 style，`1-9` = 跳到对应 style

## 与 layout_preview.py 的关系

`photo-toolkit/scripts/layout_preview.py` 仍是**静态合成图兜底**——SSH、无浏览器、
agent 远端容器等场景下用。photo-previewer 是**交互式主入口**：调试期同 session 多
style 横向比对、移动端回看、即时切换 graded↔original。

## Requirements

- Python 3.8 或以上（stdlib only，无 pip 运行时依赖）
- 一个空闲 TCP 端口在 `127.0.0.1`（默认让 OS 自动分配，需要时用 `--port` 指定）
- 反向代理（部署方提供，例如 nginx / OpenClaw gateway）把外部 URL 转发到该
  端口；本地调试场景可以省略

## 配套版本

photo-previewer 依赖以下 skill 的产出（这些 skill 本身发布到 ClawHub，
photo-previewer 仅作为本仓库内的本地工具使用，**不发布**）：

- `photo-toolkit ≥ 1.0` —— 提供 `convert.py` 生成的 thumbnails（作为"原图"显示）
- `photo-grader ≥ 1.0` —— 提供 `graded/` 目录与 `grading_params.json` 文件结构

仓库内多 skill 协同时手工对齐即可，无版本一致性校验。

## 手动验收清单 (Manual verification)

发版前在真实环境跑过一遍，每条都打勾。单元测试已经覆盖路由/扫描/CLI fail-fast，但浏览器 UX 必须人眼/手指验证。

### 桌面（Chrome / Safari / Firefox）

- [ ] **单 session 模式**：直接打开 URL → 进入九宫格视图，第一个 style 高亮
- [ ] 顶部 mode indicator 显示 `MODE: GRADED`
- [ ] 网格任意位置点一下 → 整个网格瞬间切到 thumbnails，indicator 变 `MODE: ORIGINAL`（蓝字）
- [ ] 再点一下 → 切回 graded
- [ ] 点 style tab → 切到该 style 的网格，模式重置为 GRADED
- [ ] **键盘**：空格切原图/调色；`←/→` 切 style tab；`1-9` 跳到对应 style
- [ ] 双击网格 cell → 进入全屏单图，`object-fit: contain` 完整显示
- [ ] 全屏内单击 → 该图切原图/调色（不影响背后网格状态）
- [ ] 全屏内双击 → 退出回网格，网格状态保留
- [ ] ESC 键 → 退出全屏
- [ ] 点全屏的黑色 backdrop → 退出全屏

### 桌面 - 浏览模式

- [ ] 输入项目根路径启动 → `/` 列出所有 session（按 session_id 倒序）
- [ ] indicator 显示 `BROWSE`
- [ ] 点某个 session 链接 → 加载该 session 的九宫格视图
- [ ] URL 直接改成 `/api/manifest/<不存在的 sid>` → 返回 404 JSON

### 移动（实机或浏览器 DevTools 设备模拟器）

- [ ] 网格按桌面规则布局，但**最多 3 列**（小屏断点 600px）：9 张是 3×3 九宫格（朋友圈式），16 张是 3×6 滚动
- [ ] 单击网格切原图/调色
- [ ] 在网格内**水平滑动**（>50px）→ 切到上/下一个 style；同时不会触发 graded↔original 切换
- [ ] 在网格内**垂直滑动**（>30px 垂直分量）→ 浏览器正常滚动，不切 style
- [ ] 双击 cell → 进入全屏，全屏内可**捏合缩放**
- [ ] 全屏内单击切原图/调色，双击退出
- [ ] 顶部 style tab 区域单击切 style → **不会**顺手把网格切成 original

### 边界

- [ ] **11 张照片**：桌面网格 4 列（含一行 3 张），移动端走 3 列上限
- [ ] **单 style**：tab 区域只有 1 个 chip，左/右滑动到边界不报错（原地不动）
- [ ] **中文路径**：`<session_dir>` 含中文、style 名是中文 → URL encoding 正确，图片能加载
- [ ] **graded 缺失**：手动 `rm graded/<某张>_<style>.jpg` → 该 cell 显示深色占位 + `(graded missing)`，其余 cell 不受影响
- [ ] **thumbnail 缺失**：切到 ORIGINAL 模式，没生成过 thumbnail 的 cell 显示 `(thumbnail missing — run convert.py first)`
- [ ] **broken session**（`graded/` 空）在浏览模式下：列表里能看到，点进去得到错误信息但不导致整个 server 崩
- [ ] **config.toml**：`port = 8765` + `external_url = "https://your-host.com/preview/"` 写入后启动 server，stdout 第一行打印的是 `external_url` 而非 `127.0.0.1:8765`；CLI `--port 9000` 同时给时实际 bind 在 9000

## 已知 trade-offs

- **RAW 用户的 thumbnail 分辨率与 graded 不对等**：thumbnail 由 `convert.py` 压到 ≤2048px / quality 80-85，graded 是 RT 全分辨率渲染，切原图时会感觉糊一点。要看像素级细节请用 RawTherapee 自带 viewer。
- **移动端单击 250ms 延迟**：为了区分单击/双击，移动端的"切原图/调色"会有 ~250ms 等待。桌面无影响。
- **双击进全屏会闪一下**：双击 cell 进入全屏时，浏览器会先派发两次 click 再派发 dblclick，所以网格会先切到 ORIGINAL 再被回退。视觉上能看到一次短暂的闪烁。功能正确——全屏单图按用户原本看到的 mode 显示——只是过程不优雅。修这个要给单击加 ~250ms 延迟以等待 dblclick 仲裁，会牺牲桌面端"瞬间切换"的体验，权衡之下接受当前行为。
- **style 名含下划线 + stem 不含下划线**：极少数命名组合（例如 `IMG.NEF` × style `warm_spring`）会因为 `rpartition('_')` 解析方向错位而被误报 graded missing。规避方案：style 名避免下划线。详见 `build_session_manifest` 的 docstring。
