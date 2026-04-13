#!/usr/bin/env python3
"""
OpenClaw Photo Agents Creator
自动创建双 Agent 摄影工作流系统

使用 openclaw agents add CLI 注册 Agent，
然后写入 BOOTSTRAP.md 种子文件（合并了所有关键约束）。

架构：
  🎬 PhotoArtist  — 艺术总监（编排执行、与用户对话）
  🎨 PhotoCurator — 策展师（选片、排版、调色方案）
"""

import argparse
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


def write_file(path: Path, content: str):
    """写入文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  📝 {path.name}")


def create_agent_via_cli(agent_id: str, workspace_dir: Path, agent_type: str, vars_dict: dict) -> bool:
    """通过 openclaw CLI 创建 Agent，然后写入 BOOTSTRAP.md

    折中方案：不再写 IDENTITY/SOUL/AGENTS/TOOLS 等分散文件，
    而是把关键约束合并到一个 BOOTSTRAP.md 种子文件中。
    Agent 首次启动时从 BOOTSTRAP.md 读取种子知识。

    Args:
        agent_id: Agent ID（如 photoartist）
        workspace_dir: Agent 工作区绝对路径
        agent_type: "artist" 或 "curator"
        vars_dict: 模板变量字典

    Returns:
        是否创建成功
    """
    is_artist = agent_type == "artist"
    name_key = "ARTIST_NAME" if is_artist else "CURATOR_NAME"
    emoji_key = "ARTIST_EMOJI" if is_artist else "CURATOR_EMOJI"

    emoji = vars_dict[emoji_key]
    name = vars_dict[name_key]

    print(f"\n{emoji} 创建 Photo{agent_type.capitalize()} Agent ({name})...")

    # Step 1: 通过 openclaw agents add 注册 Agent
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

    # Step 3: 写入 BOOTSTRAP.md（种子文件，合并了所有关键约束）
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
    """为 Agent 场景创建合并配置（根目录 config.toml）"""
    config_path = skills_dir / "config.toml"
    example_path = skills_dir.parent.parent.parent / ".allinone-skill" / "config.example.toml"

    if config_path.exists():
        print(f"  ⏭  config.toml 已存在，跳过")
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


def interactive_config(args):
    """交互式配置"""
    print("\n" + "=" * 50)
    print("🦞 OpenClaw Photo Agents Creator - 配置")
    print("=" * 50)

    config = {}

    # Artist 配置
    print("\n🎬 PhotoArtist (艺术总监 — 编排执行)")
    config["artist_name"] = input(f"  昵称 [{DEFAULTS['artist_name']}]: ").strip() or DEFAULTS["artist_name"]
    config["artist_emoji"] = input(f"  Emoji [{DEFAULTS['artist_emoji']}]: ").strip() or DEFAULTS["artist_emoji"]
    config["artist_id"] = input(f"  ID [{DEFAULTS['artist_id']}]: ").strip() or DEFAULTS["artist_id"]

    # Curator 配置
    print("\n🎨 PhotoCurator (策展师 — 选片调色)")
    config["curator_name"] = input(f"  昵称 [{DEFAULTS['curator_name']}]: ").strip() or DEFAULTS["curator_name"]
    config["curator_emoji"] = input(f"  Emoji [{DEFAULTS['curator_emoji']}]: ").strip() or DEFAULTS["curator_emoji"]
    config["curator_id"] = input(f"  ID [{DEFAULTS['curator_id']}]: ").strip() or DEFAULTS["curator_id"]

    # 用户名
    config["user_name"] = input(f"\n👤 你的称呼 [{DEFAULTS['user_name']}]: ").strip() or DEFAULTS["user_name"]

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

    # 确定配置
    if args.yes:
        config = DEFAULTS.copy()
        for key in [
            "artist_name",
            "artist_emoji",
            "artist_id",
            "curator_name",
            "curator_emoji",
            "curator_id",
            "user_name",
        ]:
            arg_name = key.replace("_", "-")
            val = getattr(args, key, None)
            if val is None:
                val = getattr(args, arg_name, None)
            if val:
                config[key] = val
    else:
        config = interactive_config(args)

    # 路径处理
    base_dir = Path(os.environ.get("OPENCLAW_STATE_DIR", "~/.openclaw")).expanduser()

    artist_workspace = base_dir / f"workspace-{config['artist_id']}"
    curator_workspace = base_dir / f"workspace-{config['curator_id']}"

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
    print(f"\n配置:")
    print(f"  Artist:  {config['artist_emoji']} {config['artist_name']} (ID: {config['artist_id']})")
    print(f"  Curator: {config['curator_emoji']} {config['curator_name']} (ID: {config['curator_id']})")
    print(f"  工作区基目录: {base_dir}")

    if not args.yes:
        confirm = input("\n确认创建? [Y/n]: ").strip().lower()
        if confirm and confirm not in ("y", "yes"):
            print("已取消")
            return

    # Step 1: 通过 openclaw CLI 创建两个 Agent
    ok_a = create_agent_via_cli(config["artist_id"], artist_workspace, "artist", vars_dict)
    ok_c = create_agent_via_cli(config["curator_id"], curator_workspace, "curator", vars_dict)

    if not (ok_a and ok_c):
        print("\n⚠️  Agent 注册失败，请检查 OpenClaw 是否已安装并运行")
        return

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

    if do_setup:
        skills = ["photo-toolkit", "photo-screener", "photo-grader"]
        for skill in skills:
            setup = skills_target / skill / "scripts" / "setup_deps.sh"
            if setup.exists():
                print(f"\n📦 初始化 {skill}...")
                subprocess.run(["bash", str(setup)], cwd=str(setup.parent))
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
    print("✅ 创建完成!")
    print("=" * 50)
    print(f"\n已注册:")
    print(f"  {config['artist_emoji']} PhotoArtist ({config['artist_name']}):")
    print(f"     工作区: {artist_workspace}")
    print(f"     ID:     {config['artist_id']}")
    print(f"  {config['curator_emoji']} PhotoCurator ({config['curator_name']}):")
    print(f"     工作区: {curator_workspace}")
    print(f"     ID:     {config['curator_id']}")

    next_step = 1
    print(f"\n下一步:")
    print(f"  {next_step}. 配置 {skills_target}/config.toml 的照片输入/输出目录")
    next_step += 1
    print(f"  {next_step}. 重启 OpenClaw gateway: openclaw gateway restart")


if __name__ == "__main__":
    main()
