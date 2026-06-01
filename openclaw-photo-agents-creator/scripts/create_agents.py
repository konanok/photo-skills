#!/usr/bin/env python3
"""
OpenClaw Photo Agents Creator
自动创建/升级双 Agent 摄影工作流系统

执行步骤：
  1. `openclaw agents add` 注册 Agent（升级模式跳过）
  2. **AGENTS.md upsert**（主路径）：把业务硬约束块插入到 workspace 的
     AGENTS.md 里一个带 marker 的 section（OpenClaw 始终注入 AGENTS.md，
     是真理之源）。保留 OpenClaw 默认 seed 的通用工作区行为 + 用户自定义内容
  3. **BOOTSTRAP.md**（仅首次创建）：写一次性 first-run 引导文档。升级模式
     跳过——OpenClaw 会在 setup 完成后主动 fs.rm 删除它（见
     reconcileWorkspaceBootstrapCompletionState），反复写没有意义

架构：
  🎬 PhotoArtist  — 艺术总监（编排执行、与用户对话）
  🎨 PhotoCurator — 策展师（选片、排版、调色方案）
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

# 默认配置
DEFAULTS = {
    "artist_id": "photoartist",
    "artist_name": "照片艺术总监",
    "artist_emoji": "🎬",
    "curator_id": "photocurator",
    "curator_name": "照片策展师",
    "curator_emoji": "🎨",
    "user_name": "用户",
}

# Per-workspace state 文件名 — 记录"该 workspace 的 agent 由本工具创建，
# 上次创建用了哪些参数"。更新时无需用户重新提供参数。
CREATOR_STATE_FILENAME = ".creator-state.json"
CREATOR_STATE_SCHEMA_VERSION = 1


def write_creator_state(
    workspace: Path, agent_id: str, role: str, name: str, emoji: str, user_name: str, peer_agent_id: str
):
    """在 workspace 根目录写入 .creator-state.json。

    每个 workspace 一份；记录该 agent 的全部参数 + 跨 agent 的全局参数（user_name）
    + 互指对方 ID（peer_agent_id），这样从任一 workspace 都能拼出完整 artist+curator 对。

    覆盖式写入：creator 流程结束时调用，保留最新参数。
    """
    state = {
        "schema_version": CREATOR_STATE_SCHEMA_VERSION,
        "created_by": "openclaw-photo-agents-creator",
        "updated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent": {
            "id": agent_id,
            "role": role,  # "artist" 或 "curator"
            "name": name,
            "emoji": emoji,
        },
        "shared": {
            "user_name": user_name,
            "peer_agent_id": peer_agent_id,
        },
    }

    # 保留首次 created_at（如果存在）
    state_path = workspace / CREATOR_STATE_FILENAME
    if state_path.exists():
        try:
            existing = json.loads(state_path.read_text(encoding="utf-8"))
            if "created_at" in existing:
                state["created_at"] = existing["created_at"]
        except (json.JSONDecodeError, OSError):
            pass
    state.setdefault("created_at", state["updated_at"])

    # 原子写入：tmp + os.replace（POSIX 原子）— 防止 Ctrl-C / 磁盘满 / 并发跑导致
    # 截断的 JSON 文件落盘。后果在自定义 ID 用户上特别严重：state 损坏 → discover
    # 跳过该 workspace → fallback 仅识别默认 ID → agent 被识别为新建 → agents add 撞错。
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp_path, state_path)


def read_creator_state(workspace: Path):
    """读取 workspace 的 .creator-state.json，失败返回 None。

    任何异常（文件不存在 / JSON 损坏 / 权限错）都返回 None，
    让调用方退化到"当作未由本工具创建过"。
    """
    state_path = workspace / CREATOR_STATE_FILENAME
    if not state_path.exists():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        # 最低有效性检查：必须是 dict
        if not isinstance(state, dict):
            return None
        # 前向兼容防护：如果 state 是被更新版工具写的（schema 更高），老工具不应贸然解释
        # —— 退化为 None 让调用方走"未识别"路径，比错误读取破坏文件更安全
        if state.get("schema_version", 0) > CREATOR_STATE_SCHEMA_VERSION:
            print(
                f"  ⚠️  {state_path} schema_version={state.get('schema_version')} 高于本工具支持的 {CREATOR_STATE_SCHEMA_VERSION}，已忽略。"
            )
            return None
        # 必须有 agent.id 和 agent.role
        agent = state.get("agent", {})
        if not agent.get("id") or agent.get("role") not in ("artist", "curator"):
            return None
        return state
    except (json.JSONDecodeError, OSError):
        return None


def discover_existing_agents(base_dir: Path):
    """扫描 base_dir 下所有 workspace-*/.creator-state.json，找出已注册的 artist/curator。

    返回 {"artist": state_dict_or_None, "curator": state_dict_or_None}。
    每个 state_dict 额外注入 "_workspace" 字段方便上层使用。

    冲突处理：如果发现多个 artist 或多个 curator（多次 create 用了不同 ID），
    选 updated_at 最新的那个；同时打印警告。
    """
    found = {"artist": [], "curator": []}

    # is_dir() 而不是 exists() — 防止 base_dir 被误用作文件路径时下面的 iterdir 报 NotADirectoryError
    if not base_dir.is_dir():
        return {"artist": None, "curator": None}

    for child in base_dir.iterdir():
        if not child.is_dir() or not child.name.startswith("workspace-"):
            continue
        state = read_creator_state(child)
        if state is None:
            continue
        role = state["agent"]["role"]
        if role not in found:
            continue
        state["_workspace"] = child
        found[role].append(state)

    def pick_latest(candidates):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # 多个候选 — 选 updated_at 最新的
        candidates.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        ids = [c["agent"]["id"] for c in candidates]
        print(f"  ⚠️  发现多个候选 agent: {ids}，选用最新更新的: {candidates[0]['agent']['id']}")
        print(f"     如需切换，请显式传入 --artist-id / --curator-id")
        return candidates[0]

    return {
        "artist": pick_latest(found["artist"]),
        "curator": pick_latest(found["curator"]),
    }


def fallback_default_id_recovery(base_dir: Path):
    """state 文件全缺时的兜底发现 — 仅识别默认 ID 对。

    设计理由：升级机制基于 .creator-state.json 自动发现，但 state 是新加的——
    现存用户首次升级时还没有 state 文件，会被识别为"创建"，导致 `agents add` 报错。
    本函数针对"上次用默认 ID（photoartist + photocurator）创建"这一最常见情况兜底。

    严格条件（必须同时满足）：
    1. 默认 ID 的 workspace 目录都存在（workspace-photoartist + workspace-photocurator）
    2. `openclaw agents list --json` 中两个默认 ID 都已注册
    3. 两个 workspace 都没有 .creator-state.json（避免覆盖正常发现路径）

    自定义 ID 用户不命中本兜底，需手动传 --artist-id / --curator-id 跑一次过渡。
    这是有意的设计：宁可让少数用户多传一次参数，也不引入 ID 子串猜测的脆弱逻辑。

    Returns:
        (artist_workspace, curator_workspace) 都是 Path；不命中返回 (None, None)。
    """
    artist_id = DEFAULTS["artist_id"]
    curator_id = DEFAULTS["curator_id"]

    artist_ws = base_dir / f"workspace-{artist_id}"
    curator_ws = base_dir / f"workspace-{curator_id}"

    # 条件 1: 默认 workspace 目录都存在
    if not (artist_ws.is_dir() and curator_ws.is_dir()):
        return (None, None)

    # 条件 3: state 文件不存在（避免与正常发现路径冲突）
    if (artist_ws / CREATOR_STATE_FILENAME).exists() or (curator_ws / CREATOR_STATE_FILENAME).exists():
        return (None, None)

    # 条件 2: 两个默认 ID 都在 OpenClaw 中已注册
    artist_real_ws = get_existing_agent_workspace(artist_id)
    curator_real_ws = get_existing_agent_workspace(curator_id)
    if artist_real_ws is None or curator_real_ws is None:
        return (None, None)

    # 条件 2 进一步确认：openclaw 报告的 workspace 与默认路径一致
    # （如果用户当初用了 --workspace 别的路径，文件还是写到 OpenClaw 实际加载那份）
    return (artist_real_ws, curator_real_ws)


def get_template_dir():
    """获取模板目录"""
    return Path(__file__).parent.parent / "templates"


def load_template(name):
    """加载模板文件"""
    template_path = get_template_dir() / name
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    return None


def render_template(template_content, variables):
    """渲染模板，支持 {{VARIABLE}} 占位符语法"""
    if template_content is None:
        return ""

    def replacer(match):
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))

    return re.sub(r"\{\{([^}]+)\}\}", replacer, template_content)


def run_cmd(cmd, description=""):
    """执行 shell 命令"""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ⚠️ {description or ' '.join(cmd)} 失败:")
        print(f"     {result.stderr.strip()}")
    else:
        print(result.stderr.strip())
    return result.returncode == 0


def get_existing_agent_workspace(agent_id: str):
    """通过 `openclaw agents list --json` 查询已存在 agent 的真实 workspace 路径。

    Returns:
        Path：已注册 → 返回真实 workspace 绝对路径
        None：未注册 / openclaw CLI 不可用 / 输出解析失败 — 调用方应继续走"新建"路径

    设计：失败时返回 None 而非抛错，避免 openclaw CLI 输出格式变化时硬挂。
    fallback 行为是退化到默认 workspace 路径计算，最差情况等同于改造前。
    """
    try:
        result = subprocess.run(
            ["openclaw", "agents", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        agents = json.loads(result.stdout)
        for agent in agents:
            if agent.get("id") == agent_id:
                workspace = agent.get("workspace")
                if workspace:
                    return Path(workspace).expanduser()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        # 已知的"环境未就绪"类异常 — 安静降级到默认路径计算
        return None
    except Exception as e:
        # 未知异常（如 schema 漂移导致 AttributeError）— 不沉默吞，否则会被误判为
        # "agent 未注册" 进入 `agents add` 路径并撞错。打印让用户能看见。
        print(f"  ⚠️  解析 `openclaw agents list --json` 失败: {type(e).__name__}: {e}")
        print(f"     退化到默认路径计算；如反复出现请提 issue。")
        return None


def write_file(path: Path, content: str):
    """写入文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  📝 {path.name}")


# ── AGENTS.md marker-based upsert ───────────────────────────────
#
# Why marker-based:
#   OpenClaw `ensureAgentWorkspace` (workspace-DNgRLjQy.js:381) seeds a default
#   `AGENTS.md` via `writeFileIfMissing` when an agent first starts a session
#   (First Run / Session Startup / Memory / Red Lines, ~7-8KB of general
#   workspace behavior). Users may also hand-edit AGENTS.md with personal notes.
#
#   We need to inject photo-skills business hard-constraints (must spawn curator,
#   schema requirements, session layout) WITHOUT clobbering either.
#
# Protocol:
#   - Our block is delimited by sentinel comments:
#       <!-- BEGIN: photo-skills-{role}-rules:v1 -->
#       ... our rendered template ...
#       <!-- END: photo-skills-{role}-rules:v1 -->
#   - On upsert:
#       * If file doesn't exist → write the full template (already starts and
#         ends with our markers from the template itself)
#       * If file exists AND contains our markers → replace the block in place
#       * If file exists but no markers → append a blank line + our block to EOF
#   - Version `v1` lets us deprecate cleanly later (a `v2` template can
#     leave old `v1` blocks for users to compare or delete manually).

_AGENTS_MARKER_BEGIN_FMT = "<!-- BEGIN: photo-skills-{role}-rules:v1 -->"
_AGENTS_MARKER_END_FMT = "<!-- END: photo-skills-{role}-rules:v1 -->"


def upsert_agents_md_block(path: Path, role: str, rendered_block: str) -> str:
    """Insert/replace the photo-skills hard-constraints block in workspace/AGENTS.md.

    `rendered_block` is the content rendered from agents-{role}.md template
    AND already wrapped in BEGIN/END markers (the template itself contains
    them, see templates/agents-artist.md). This function passes the rendered
    string through directly when inserting or replacing.

    Returns a one-word action label for logging: "created" / "replaced" / "appended".
    """
    begin = _AGENTS_MARKER_BEGIN_FMT.format(role=role)
    end = _AGENTS_MARKER_END_FMT.format(role=role)

    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(rendered_block + "\n", encoding="utf-8")
        return "created"

    existing = path.read_text(encoding="utf-8")
    begin_idx = existing.find(begin)
    end_idx = existing.find(end)

    if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
        # Replace in-place: keep everything before BEGIN and after END.
        before = existing[:begin_idx]
        after = existing[end_idx + len(end):]
        merged = before + rendered_block + after
        path.write_text(merged, encoding="utf-8")
        return "replaced"

    # Markers absent → append at EOF, separated by a blank line.
    separator = "\n\n" if not existing.endswith("\n\n") else ""
    if existing and not existing.endswith("\n"):
        separator = "\n" + separator
    path.write_text(existing + separator + rendered_block + "\n", encoding="utf-8")
    return "appended"


def create_agent_via_cli(
    agent_id: str, workspace_dir: Path, agent_type: str, vars_dict: dict, agent_exists: bool = False
) -> bool:
    """通过 openclaw CLI 创建 Agent，然后写入 workspace 文件。

    文件写入策略（按重要性排序）：
      1. **AGENTS.md upsert**（始终执行）— OpenClaw 永久注入该文件到 system
         prompt，是业务硬约束的真理之源。marker-based upsert 保留 OpenClaw
         默认 seed 的通用工作区行为（First Run / Session Startup / Memory /
         Red Lines）和用户自定义内容。
      2. **BOOTSTRAP.md**（仅首次创建）— 一次性 first-run 引导。setupCompletedAt
         设置后 OpenClaw 会过滤并主动 fs.rm 删除它，所以升级模式跳过。
      3. **prompts/**（仅 curator）— 写 user_prompt_selection / grading 模板，
         调色 prompt 自动注入 LR→RT 映射参考。

    早期版本只写 BOOTSTRAP.md，导致 setup 完成后所有业务约束失效——见
    CHANGELOG 1.0.1 "AGENTS.md marker-based upsert" 一条。

    升级语义：当 agent_exists=True 时跳过 `openclaw agents add` 和 BOOTSTRAP.md
    写入，仅刷新 AGENTS.md（marker block 内容）/ prompts / skills 文件。
    这让"重跑 creator"成为合法的更新通道。

    Args:
        agent_id: Agent ID（如 photoartist）
        workspace_dir: Agent 工作区绝对路径
        agent_type: "artist" 或 "curator"
        vars_dict: 模板变量字典
        agent_exists: True 表示该 agent 已注册，跳过 `agents add`，仅刷新文件

    Returns:
        是否创建/更新成功
    """
    is_artist = agent_type == "artist"
    name_key = "ARTIST_NAME" if is_artist else "CURATOR_NAME"
    emoji_key = "ARTIST_EMOJI" if is_artist else "CURATOR_EMOJI"

    emoji = vars_dict[emoji_key]
    name = vars_dict[name_key]

    action = "更新" if agent_exists else "创建"
    print(f"\n{emoji} {action} Photo{agent_type.capitalize()} Agent ({name})...")

    # Step 1: 注册 Agent（已存在则跳过）
    if agent_exists:
        print(f"  ↻ Agent 已存在，跳过注册，仅刷新 workspace 文件")
    else:
        print(f"  📌 注册 Agent: {agent_id}")
        success = run_cmd(
            ["openclaw", "agents", "add", agent_id, "--workspace", str(workspace_dir), "--non-interactive"],
            f"openclaw agents add {agent_id}",
        )
        if not success:
            return False

    # Step 2: 构建模板变量
    agent_vars = dict(vars_dict)
    agent_vars.update(
        {
            "NICKNAME": name,
            "EMOJI": emoji,
        }
    )

    # Step 3a: AGENTS.md — marker-based upsert (always run)
    #
    # 关键背景：OpenClaw v2026.5.18 的 system prompt 注入逻辑（来自 dist 源码
    # workspace-DNgRLjQy.js 的 loadWorkspaceBootstrapFiles + filterBootstrapFilesForSession）：
    #   - AGENTS.md / TOOLS.md 对 main session / subagent / cron 都注入，无过滤
    #   - BOOTSTRAP.md 在 .openclaw/workspace-state.json 的 setupCompletedAt 已设置时
    #     被 filterCompletedWorkspaceBootstrapFile 丢弃；subagent/cron 永远不注入；
    #     更糟：reconcileWorkspaceBootstrapCompletionState 在 setup 完成时还会
    #     主动 `fs.rm` 掉 BOOTSTRAP.md。所以 BOOTSTRAP 是"一次性礼炮"，不是
    #     持久 SOP。
    #
    # 历史 bug：早期版本只写 BOOTSTRAP.md，假设它一直被注入。结果用户的
    # photoartist 在 setup completed 后丢失了所有业务约束（"必须 spawn curator"
    # 等），自己脑补 grading_params.json schema，触发 grade.py 一连串静默失败，
    # 最终用户拿到"画面死黑"的产物。
    #
    # 修复：把硬约束写到 AGENTS.md 里一个带 marker 的 block，用 upsert 协议
    # 保留 OpenClaw 默认 seed 的通用工作区行为（First Run/Session Startup/
    # Memory/Red Lines）以及用户手动加的自定义内容。
    agents_template = load_template(f"agents-{agent_type}.md")
    if agents_template is not None:
        agents_block = render_template(agents_template, agent_vars)
        action = upsert_agents_md_block(workspace_dir / "AGENTS.md", agent_type, agents_block)
        print(f"  📝 AGENTS.md (photo-skills-{agent_type}-rules:v1 block {action})")
    else:
        # Defensive: 模板缺失时不静默继续，因为缺 AGENTS.md = agent 失去硬约束
        print(
            f"  ⚠️  WARN: templates/agents-{agent_type}.md 未找到，AGENTS.md 未更新。"
            f"\n     这会导致 {agent_type} 在 setupCompletedAt 已设置后失去业务硬约束。"
            f"\n     请检查 openclaw-photo-agents-creator 安装是否完整。",
        )

    # Step 3b: BOOTSTRAP.md — first-run only（升级模式下跳过）
    #
    # 为什么升级模式跳过：OpenClaw 在 setupCompletedAt 已设置的 workspace 上
    # 每次 session 启动都会触发 reconcileWorkspaceBootstrapCompletionState
    # 主动 `fs.rm` 掉 BOOTSTRAP.md（workspace-DNgRLjQy.js:197-241 分支 3）。
    # 我们这里写进去会立刻在下次 agent session 启动时被删，等于无效的写-删
    # 循环。所以升级模式下完全跳过。
    #
    # 首次创建（agent_exists=False）时仍写：那种情况 workspace 还没经历过
    # session 启动，setupCompletedAt 也还没设置，BOOTSTRAP.md 能在 first-run
    # 时被注入一次（承担它"一次性礼炮"的设计本意）。
    if agent_exists:
        print(f"  ⏭  BOOTSTRAP.md 升级模式跳过（OpenClaw 已设置 setupCompletedAt，"
              f"任何新版 BOOTSTRAP.md 都会在下次 session 启动时被 reconcile 删除）")
    else:
        bootstrap = render_template(load_template(f"bootstrap-{agent_type}.md"), agent_vars)
        write_file(workspace_dir / "BOOTSTRAP.md", bootstrap)

    # Curator 额外写入 user-prompt 模板（结构化格式约束，不适合省略）
    if not is_artist:
        user_prompt_sel = load_template("photo-curator-user-prompt-selection.md")
        user_prompt_grad = load_template("photo-curator-user-prompt-grading.md")
        if user_prompt_sel:
            write_file(
                workspace_dir / "prompts" / "user_prompt_selection.md", render_template(user_prompt_sel, agent_vars)
            )
        if user_prompt_grad:
            # Inject LR→RT mapping reference into grading prompt
            rt_mapping = load_template("rt-mapping-reference.md")
            if rt_mapping:
                agent_vars_with_mapping = dict(agent_vars)
                agent_vars_with_mapping["RT_MAPPING_REFERENCE"] = rt_mapping
            else:
                agent_vars_with_mapping = dict(agent_vars)
                agent_vars_with_mapping["RT_MAPPING_REFERENCE"] = (
                    "（映射表文件未找到，请参考 grade.py 的 rt_map_*() 函数）"
                )
            write_file(
                workspace_dir / "prompts" / "user_prompt_grading.md",
                render_template(user_prompt_grad, agent_vars_with_mapping),
            )

    return True


def copy_skills(photo_skills_dir: Path, target_dir: Path):
    """复制 Skill 文件"""
    print("\n📦 复制 Skill 文件...")

    skills = ["photo-toolkit", "photo-screener", "photo-grader"]

    for skill in skills:
        source = photo_skills_dir / skill
        target = target_dir / skill

        if source.exists():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
            print(f"  ✅ {skill}")
        else:
            print(f"  ⚠️  {skill} 未找到")
            target.mkdir(parents=True, exist_ok=True)
            placeholder = target / "README.md"
            placeholder.write_text(f"# {skill}\n\n请手动安装此 Skill。\n", encoding="utf-8")


def _print_photo_grader_dependency_hint():
    print("     photo-grader 需要可用的 RawTherapee CLI。")
    print("     macOS 下请先验证: rawtherapee-cli -h")
    print("     如果是 Agent 自动通过 Homebrew 安装，用户通常还没有显式打开/授权应用或 CLI，")
    print("     可能会被 macOS 安全机制拦截，并在启动前以 exit 133 / SIGTRAP 退出。")
    print("     用户自己提前通过 Homebrew 安装并完成授权也可以使用；否则建议改用官网包中的独立 rawtherapee-cli。")


def run_skill_setups(skills_target: Path, skills=None):
    """运行各 skill 的 setup_deps.sh，并汇总失败项。"""
    skills = skills or ["photo-toolkit", "photo-screener", "photo-grader"]
    failures = []

    for skill in skills:
        setup = skills_target / skill / "scripts" / "setup_deps.sh"
        if not setup.exists():
            continue

        print(f"\n📦 初始化 {skill}...")
        result = subprocess.run(["bash", str(setup)], cwd=str(setup.parent), capture_output=True, text=True)
        if result.stdout.strip():
            print(result.stdout.rstrip())
        if result.stderr.strip():
            print(result.stderr.rstrip())

        if result.returncode != 0:
            failures.append(skill)
            print(f"  ⚠️  {skill} 初始化失败（exit {result.returncode}）")
            combined_output = f"{result.stdout}\n{result.stderr}".lower()
            if skill == "photo-grader" or "rawtherapee" in combined_output or "sigtrap" in combined_output:
                _print_photo_grader_dependency_hint()

    if failures:
        print("\n  ⚠️  以下 skill 依赖初始化失败: " + ", ".join(failures))
        print("     创建流程会继续，但使用对应功能前必须先修复依赖。")
    return failures


def update_openclaw_json(base_dir: Path, artist_id: str, curator_id: str):
    """
    自动更新 openclaw.json，为 PhotoArtist agent 添加 subagents.allowAgents 配置。

    只有 PhotoArtist 需要调用 PhotoCurator 作为子 Agent，
    因此 subagents.allowAgents 只添加到 artist agent 的配置中。

    Args:
        base_dir: OpenClaw 状态目录（如 ~/.openclaw）
        artist_id: Artist Agent ID
        curator_id: Curator Agent ID
    """
    openclaw_json = base_dir / "openclaw.json"

    if not openclaw_json.exists():
        print(f"\n  ⚠️  openclaw.json 未找到: {openclaw_json}")
        print(f"     请手动为 {artist_id} 添加 subagents.allowAgents 配置")
        return False

    try:
        with open(openclaw_json, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"\n  ⚠️  无法读取 openclaw.json: {e}")
        return False

    # 在 agents.list 中找到 artist agent
    agents_list = config.get("agents", {}).get("list", [])
    artist_agent = None
    for agent in agents_list:
        if agent.get("id") == artist_id:
            artist_agent = agent
            break

    if artist_agent is None:
        print(f"\n  ⚠️  在 openclaw.json 中未找到 agent '{artist_id}'")
        print(f'     请手动为 {artist_id} 添加 subagents.allowAgents: ["{curator_id}"]')
        return False

    # 确保 artist agent 有 subagents.allowAgents
    if "subagents" not in artist_agent:
        artist_agent["subagents"] = {}
    if "allowAgents" not in artist_agent["subagents"]:
        artist_agent["subagents"]["allowAgents"] = []

    # 添加 curator ID（如果不存在）
    allow_agents = artist_agent["subagents"]["allowAgents"]
    if curator_id in allow_agents:
        print(f"\n  ℹ️  {artist_id}.subagents.allowAgents 已包含 {curator_id}")
        return True

    allow_agents.append(curator_id)

    # 写回文件
    try:
        with open(openclaw_json, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f'\n  ✅ 已为 {artist_id} 添加 subagents.allowAgents: ["{curator_id}"]')
        print(f"     配置文件: {openclaw_json}")
        return True
    except Exception as e:
        print(f"\n  ⚠️  无法写入 openclaw.json: {e}")
        return False


def create_merged_config(skills_dir: Path):
    """为 Agent 场景创建合并配置（根目录 config.toml）

    升级语义：config.toml 已存在时**绝不覆盖**（保护用户配置）。但如果新版本的
    config.example.toml 增加了字段，用户的旧 config.toml 不会自动迁移，新代码可能
    读不到新字段而出错——所以已存在时打印提示，让用户自己 diff。
    """
    config_path = skills_dir / "config.toml"
    example_path = skills_dir.parent.parent.parent / ".allinone-skill" / "config.example.toml"

    if config_path.exists():
        print(f"  ⏭  config.toml 已存在，跳过（保护用户配置）")
        if example_path.exists():
            print(f"     ⚠️  如新版有 schema 变更，请手动 diff 模板补齐字段：")
            print(f"        diff {config_path} {example_path}")
        return

    # 尝试从 allinone-skill 的模板复制
    if example_path.exists():
        shutil.copy2(str(example_path), str(config_path))
        print(f"  📝 config.toml（合并配置，请编辑设置目录路径）")
    else:
        # 生成最小配置
        config_path.write_text(
            "# 合并配置 — Agent 场景下所有脚本共用\n"
            "# 请设置你的照片输入/输出目录\n\n"
            'raw_dir = ""\n'
            'output_dir = ""\n',
            encoding="utf-8",
        )
        print(f"  📝 config.toml（最小配置，请编辑设置目录路径）")


def interactive_config(baseline=None, is_update=False):
    """交互式配置

    baseline: 各字段的默认提示值。更新场景下传入上次创建时的值，让用户回车即保留；
              首次创建场景下传入 DEFAULTS，行为与改造前一致。
    """
    if baseline is None:
        baseline = DEFAULTS

    print("\n" + "=" * 50)
    title = "更新" if is_update else "创建"
    print(f"🦞 OpenClaw Photo Agents Creator - {title}配置")
    print("=" * 50)
    if is_update:
        print("\n  ↻ 已检测到既有 agent；以下默认值来自上次创建。回车保留，输入新值覆盖。")

    config = {}

    # Artist 配置
    print("\n🎬 PhotoArtist (艺术总监 — 编排执行)")
    config["artist_name"] = input(f"  昵称 [{baseline['artist_name']}]: ").strip() or baseline["artist_name"]
    config["artist_emoji"] = input(f"  Emoji [{baseline['artist_emoji']}]: ").strip() or baseline["artist_emoji"]
    config["artist_id"] = input(f"  ID [{baseline['artist_id']}]: ").strip() or baseline["artist_id"]

    # Curator 配置
    print("\n🎨 PhotoCurator (策展师 — 选片调色)")
    config["curator_name"] = input(f"  昵称 [{baseline['curator_name']}]: ").strip() or baseline["curator_name"]
    config["curator_emoji"] = input(f"  Emoji [{baseline['curator_emoji']}]: ").strip() or baseline["curator_emoji"]
    config["curator_id"] = input(f"  ID [{baseline['curator_id']}]: ").strip() or baseline["curator_id"]

    # 用户名
    config["user_name"] = input(f"\n👤 你的称呼 [{baseline['user_name']}]: ").strip() or baseline["user_name"]

    return config


def main():
    parser = argparse.ArgumentParser(description="自动创建 OpenClaw 双 Agent 摄影工作流系统")
    parser.add_argument("--yes", "-y", action="store_true", help="非交互模式，使用默认配置")

    # 自定义选项
    parser.add_argument("--artist-name", default=None, help="Artist 昵称")
    parser.add_argument("--artist-emoji", default=None, help="Artist Emoji")
    parser.add_argument("--artist-id", default=None, help="Artist ID")
    parser.add_argument("--curator-name", default=None, help="Curator 昵称")
    parser.add_argument("--curator-emoji", default=None, help="Curator Emoji")
    parser.add_argument("--curator-id", default=None, help="Curator ID")
    parser.add_argument("--user-name", default=None, help="用户称呼")

    args = parser.parse_args()

    # 路径处理
    base_dir = Path(os.environ.get("OPENCLAW_STATE_DIR", "~/.openclaw")).expanduser()

    # ── 升级路径发现 ──────────────────────────────────────────────
    # 扫描所有 workspace-*/.creator-state.json，找出"上次由本工具创建的" artist/curator。
    # 命中则进入更新模式：参数 fallback 顺序变成 CLI > state > DEFAULTS。
    # 这样用户更新时一句 `python3 create_agents.py --yes` 就够，不必重传所有参数。
    discovered = discover_existing_agents(base_dir)
    artist_state = discovered["artist"]
    curator_state = discovered["curator"]

    # Fallback: state 全缺时尝试"默认 ID 兜底"——
    # 让现存用户（升级前没有 state 文件）首次升级也能 zero-arg。
    #
    # 语义关键：fallback 只能确认"agent 存在 + ID 是默认值"，**无法**得知用户当初
    # 是否传过 --artist-name "老张" 之类的自定义昵称（state 不存在 = 没有持久化记录，
    # 我们刻意拒绝从 BOOTSTRAP.md 反向 parse）。所以 name/emoji/user_name 字段填 None
    # 表达"未知"——后续 baseline 构建时这些 None 会 fallback 到 DEFAULTS，但语义上跟
    # "用户明确设过 = DEFAULTS"是不同的（前者由 fallback 兜底，后者由 state 携带）。
    if artist_state is None and curator_state is None:
        fb_artist_ws, fb_curator_ws = fallback_default_id_recovery(base_dir)
        if fb_artist_ws is not None and fb_curator_ws is not None:
            print(f"\n  ↻ 兜底识别到默认 ID 的 agent 已注册（{DEFAULTS['artist_id']} + {DEFAULTS['curator_id']}），")
            print(f"     将进入更新流程；本次完成后会写入 .creator-state.json，下次起完全 zero-arg。")
            print(f"     ⚠️  无法恢复你当初的昵称/Emoji（state 文件不存在）。")
            print(f"        如曾自定义过这些参数，请本次显式传入，例如：")
            print(f"        --artist-name 'X' --artist-emoji '🎬' --user-name 'Y'")
            print(f"        否则其他字段保持原状（仅在你显式传入时才会改写 BOOTSTRAP）。")
            # name/emoji/user_name 用 None 表示"未知"——baseline 构建时会忠实退化为 DEFAULTS，
            # 但这里 None 让"fallback 路径"和"正常 state 路径"在数据结构上可区分
            artist_state = {
                "agent": {
                    "id": DEFAULTS["artist_id"],
                    "role": "artist",
                    "name": None,
                    "emoji": None,
                },
                "shared": {"user_name": None, "peer_agent_id": DEFAULTS["curator_id"]},
                "_workspace": fb_artist_ws,
                "_from_fallback": True,
            }
            curator_state = {
                "agent": {
                    "id": DEFAULTS["curator_id"],
                    "role": "curator",
                    "name": None,
                    "emoji": None,
                },
                "shared": {"user_name": None, "peer_agent_id": DEFAULTS["artist_id"]},
                "_workspace": fb_curator_ws,
                "_from_fallback": True,
            }

    is_update = artist_state is not None or curator_state is not None

    # 构建"基线配置"：state > DEFAULTS（CLI 在后续阶段覆盖）
    # 关键：用 `or DEFAULTS[...]` 让 fallback 路径下的 None 字段忠实退化为默认值，
    # 同时不破坏正常 state 路径"用户明确设过 X → 沿用 X"的语义。
    baseline = DEFAULTS.copy()
    if artist_state:
        baseline["artist_id"] = artist_state["agent"]["id"]
        baseline["artist_name"] = artist_state["agent"]["name"] or DEFAULTS["artist_name"]
        baseline["artist_emoji"] = artist_state["agent"]["emoji"] or DEFAULTS["artist_emoji"]
        baseline["user_name"] = artist_state["shared"].get("user_name") or DEFAULTS["user_name"]
    if curator_state:
        baseline["curator_id"] = curator_state["agent"]["id"]
        baseline["curator_name"] = curator_state["agent"]["name"] or DEFAULTS["curator_name"]
        baseline["curator_emoji"] = curator_state["agent"]["emoji"] or DEFAULTS["curator_emoji"]
        # curator 的 user_name 与 artist 的应当一致；以 artist 的为准（artist 通常先创建）
        if not artist_state:
            baseline["user_name"] = curator_state["shared"].get("user_name") or DEFAULTS["user_name"]

    # 应用 CLI 参数（最高优先级）
    if args.yes:
        config = baseline.copy()
        for key in [
            "artist_name",
            "artist_emoji",
            "artist_id",
            "curator_name",
            "curator_emoji",
            "curator_id",
            "user_name",
        ]:
            val = getattr(args, key, None)
            if val:
                config[key] = val
    else:
        # 交互式：把 baseline 作为 prompt 默认值传入（更新场景下显示用户上次的值）
        config = interactive_config(baseline=baseline, is_update=is_update)
        # 交互式中 CLI 显式参数仍优先（用户传 --artist-id 时不再问）
        for key in [
            "artist_name",
            "artist_emoji",
            "artist_id",
            "curator_name",
            "curator_emoji",
            "curator_id",
            "user_name",
        ]:
            val = getattr(args, key, None)
            if val:
                config[key] = val

    # 用 state 中记录的 workspace 路径（如有），保证文件写到 OpenClaw 实际加载那份
    if artist_state and config["artist_id"] == artist_state["agent"]["id"]:
        artist_workspace = artist_state["_workspace"]
        artist_exists = True
    else:
        # CLI 改了 ID 或者首次创建 — 走默认路径计算
        # 仍然查 openclaw 看新 ID 是否已注册（用户可能手工注册过 agent 但没用过本工具）
        existing_ws = get_existing_agent_workspace(config["artist_id"])
        artist_workspace = existing_ws or (base_dir / f"workspace-{config['artist_id']}")
        artist_exists = existing_ws is not None

    if curator_state and config["curator_id"] == curator_state["agent"]["id"]:
        curator_workspace = curator_state["_workspace"]
        curator_exists = True
    else:
        existing_ws = get_existing_agent_workspace(config["curator_id"])
        curator_workspace = existing_ws or (base_dir / f"workspace-{config['curator_id']}")
        curator_exists = existing_ws is not None

    # 重新计算 is_update（CLI 可能切到了一个之前没创建过的 ID）
    is_update = artist_exists or curator_exists

    # 构建模板变量字典
    vars_dict = {
        "ARTIST_ID": config["artist_id"],
        "ARTIST_NAME": config["artist_name"],
        "ARTIST_EMOJI": config["artist_emoji"],
        "CURATOR_ID": config["curator_id"],
        "CURATOR_NAME": config["curator_name"],
        "CURATOR_EMOJI": config["curator_emoji"],
        "USER_NAME": config["user_name"],
        "SKILLS_DIR": f"{artist_workspace}/skills",
    }

    print("\n" + "=" * 50)
    print("🦞 OpenClaw Photo Agents Creator")
    print("=" * 50)
    mode_label = "更新" if is_update else "创建"
    print(f"\n模式: {mode_label}")
    print(f"配置:")
    artist_marker = " [已存在]" if artist_exists else ""
    curator_marker = " [已存在]" if curator_exists else ""
    print(f"  Artist:  {config['artist_emoji']} {config['artist_name']} (ID: {config['artist_id']}){artist_marker}")
    print(f"     workspace: {artist_workspace}")
    print(f"  Curator: {config['curator_emoji']} {config['curator_name']} (ID: {config['curator_id']}){curator_marker}")
    print(f"     workspace: {curator_workspace}")
    print(f"  工作区基目录: {base_dir}")

    if is_update:
        print("\n  ↻ 检测到 Agent 已注册，将刷新 BOOTSTRAP.md / prompts / skills 文件。")
        print("     注意：BOOTSTRAP.md 和 prompts 改动需要重启 gateway 才能被运行中的 agent 加载。")

    if not args.yes:
        prompt_label = "确认更新?" if is_update else "确认创建?"
        confirm = input(f"\n{prompt_label} [Y/n]: ").strip().lower()
        if confirm and confirm not in ("y", "yes"):
            print("已取消")
            return

    # Step 1: 通过 openclaw CLI 创建两个 Agent（已存在则仅刷新文件）
    ok_a = create_agent_via_cli(config["artist_id"], artist_workspace, "artist", vars_dict, agent_exists=artist_exists)
    ok_c = create_agent_via_cli(
        config["curator_id"], curator_workspace, "curator", vars_dict, agent_exists=curator_exists
    )

    if not (ok_a and ok_c):
        print("\n⚠️  Agent 注册失败，请检查 OpenClaw 是否已安装并运行")
        return

    # 写入 .creator-state.json — 让下次重跑能自动发现并进入更新模式。
    # 在 BOOTSTRAP 已写、skills 拷贝之前写：即使后续步骤失败，state 也已落盘，
    # 重跑时 discover 仍能识别这是更新场景。
    write_creator_state(
        artist_workspace,
        agent_id=config["artist_id"],
        role="artist",
        name=config["artist_name"],
        emoji=config["artist_emoji"],
        user_name=config["user_name"],
        peer_agent_id=config["curator_id"],
    )
    write_creator_state(
        curator_workspace,
        agent_id=config["curator_id"],
        role="curator",
        name=config["curator_name"],
        emoji=config["curator_emoji"],
        user_name=config["user_name"],
        peer_agent_id=config["artist_id"],
    )

    # Step 2: 复制 Skills 到 Artist 工作区的 skills/ 子目录
    photo_skills_dir = Path(
        __file__
    ).parent.parent.parent  # scripts/ → openclaw-photo-agents-creator/ → photo-skills/ (monorepo root)
    skills_target = artist_workspace / "skills"
    if (photo_skills_dir / "photo-toolkit").exists():
        copy_skills(photo_skills_dir, skills_target)
        create_merged_config(skills_target)
    else:
        print("  ⚠️  未找到 photo-* skills，请手动复制")

    # Step 3: 初始化环境（各 skill 的 setup_deps.sh 自带检查+安装）
    print("\n" + "━" * 50)
    print("  🔧 环境初始化")
    print("━" * 50)

    # 自动更新 openclaw.json
    update_openclaw_json(base_dir, config["artist_id"], config["curator_id"])

    if args.yes:
        do_setup = True
    else:
        print()
        print("  各 Skill 需要系统和 Python 依赖才能正常工作。")
        print("  初始化会依次检查并安装缺少的依赖。")
        print()
        answer = input("  是否现在初始化环境？[Y/n] ").strip()
        do_setup = not answer or answer.lower() in ("y", "yes", "是")

    setup_failures = []
    if do_setup:
        setup_failures = run_skill_setups(skills_target)
        print()
    else:
        print("\n  ⏭  跳过环境初始化")
        print("     稍后可手动运行各 skill 的 setup_deps.sh：")
        for skill in ["photo-toolkit", "photo-screener", "photo-grader"]:
            setup = skills_target / skill / "scripts" / "setup_deps.sh"
            if setup.exists():
                print(f"       bash {setup}")

    # 输出结果
    print("\n" + "=" * 50)
    action_label = "更新" if is_update else "创建"
    if setup_failures:
        print(f"⚠️  {action_label}完成，但部分依赖初始化失败")
    else:
        print(f"✅ {action_label}完成!")
    print("=" * 50)
    label = "已更新" if is_update else "已注册"
    print(f"\n{label}:")
    print(f"  {config['artist_emoji']} PhotoArtist ({config['artist_name']}):")
    print(f"     工作区: {artist_workspace}")
    print(f"     ID:     {config['artist_id']}")
    print(f"  {config['curator_emoji']} PhotoCurator ({config['curator_name']}):")
    print(f"     工作区: {curator_workspace}")
    print(f"     ID:     {config['curator_id']}")

    next_step = 1
    print(f"\n下一步:")
    if setup_failures:
        print(f"  {next_step}. 先修复依赖初始化失败项: {', '.join(setup_failures)}")
        if "photo-grader" in setup_failures:
            print(
                "     macOS 下请确认 rawtherapee-cli 已放入 PATH，并通过 rawtherapee-cli -h 验证；Homebrew 安装后可能需要用户手动打开/授权"
            )
        next_step += 1
    if is_update:
        # 更新模式：config.toml 已存在不再提示创建；重启 gateway 才是关键
        print(f"  {next_step}. 重启 OpenClaw gateway 让 BOOTSTRAP / prompts 改动生效:")
        print(f"     openclaw gateway restart")
        print(f"     （Self-mode 下请在外部终端执行；改动仅涉及 skills/scripts/*.py 时可不重启）")
    else:
        print(f"  {next_step}. 配置 {skills_target}/config.toml 的照片输入/输出目录")
        next_step += 1
        print(f"  {next_step}. 重启 OpenClaw gateway: openclaw gateway restart")


if __name__ == "__main__":
    main()
