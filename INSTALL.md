# INSTALL — 安装到 OpenClaw

> 主要面向 AI 阅读。AI 只需 `git clone` 本仓库到指定位置，再调用 `openclaw-photo-agents-creator` skill，剩下的部署、初始化、依赖安装、配置生成都由该 skill 自动完成。

---

## 🚨 铁律（AI 必读，违反即停止）

读到这里的 AI 必须先回答两个问题：**我是谁？我能干什么？**

| 模式                 | 判定信号                                                                                                                 | 你能做什么               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------ | ------------------------ |
| 🤖 **Self-mode**     | 你的工作区路径形如 `~/.openclaw/workspace-*` / 启动时加载了 `BOOTSTRAP.md` 或 `AGENTS.md` / 通过 `openclaw agent` 被调起 | 你 = OpenClaw 内的 agent |
| 🛠️ **External-mode** | 你是 Claude Code / Codex / CodeBuddy / Cursor 等外部 AI / 命令通过用户终端执行                                           | 你 = 外部 AI             |

**🤖 Self-mode 的三条铁律，违反任何一条都必须立刻停下、报告用户、不要继续：**

1. **绝不自己执行 `openclaw gateway restart`**——你是 gateway 托管的进程，自重启 = 切断自己会话。任何步骤遇到 `openclaw gateway restart`（包括 SKILL.md「创建后」节的 Step 4、本文档卸载段）都**必须**委托用户去外部终端做。
2. **修改 `~/.openclaw/openclaw.json` / `~/.openclaw/credentials/` / `~/.openclaw/auth-profiles.json` 前必须先取得用户口头确认**。这些是运维域文件，不是工作区资产。`create_agents.py` 自动写入 `subagents.allowAgents` 也属于这一类，需提前告知用户。
3. **不要在收集参数前直接 `--yes`**。Step 2 的参数必须**逐项询问用户**，除非用户明确说"用默认/一键/不要问我"。

🛠️ **External-mode** 不受第 1 条限制（可以直接 `openclaw gateway restart`），但第 2、3 条同样适用。

---

## Step 1 — 克隆仓库

```bash
mkdir -p ~/.openclaw/skills
git clone https://github.com/konanok/photo-skills.git ~/.openclaw/skills/photo-skills
```

> `~/.openclaw/skills/` 是 OpenClaw 官方的"托管 Skills"目录。clone 在别处也能跑，但首选这个位置以便统一维护。

---

## Step 2 — 加载并执行 `openclaw-photo-agents-creator` skill

**SKILL 路径**：`~/.openclaw/skills/photo-skills/openclaw-photo-agents-creator/`
**SKILL 入口**：[`openclaw-photo-agents-creator/SKILL.md`](./openclaw-photo-agents-creator/SKILL.md)

AI 必须按以下方式处理这个 skill：

1. **读取** `openclaw-photo-agents-creator/SKILL.md` 全文
2. **按 SKILL.md 的「使用方法」「执行规范」自主执行**——包括逐项询问用户参数、调用脚本、依赖失败时停下引导用户、以及 SKILL.md 「创建后 — 必须手动完成的步骤」中的全部 Step 1 ~ Step 5
3. **不要让 INSTALL.md 替你决策 skill 的具体执行细节**——参数默认值、命令行形式、`--yes` 的使用条件、依赖故障处理（尤其是 macOS RawTherapee 授权）、`openclaw.json` 的字段配置等，**全部以 SKILL.md 为准**

> INSTALL.md 的角色到这里就结束了——它只负责把 AI 引导到 skill 入口；skill 自身负责完成部署和初始化。

执行 SKILL.md 「创建后」节时，直接按 SKILL.md 字面执行即可——SKILL.md Step 4 (`openclaw gateway restart`) 自身已经按 Self-mode / External-mode 做了分岔处理，与本文档铁律 #1 一致。完成 SKILL.md 全部步骤后，可直接进入本文档 Step 3 验证。

---

## Step 3 — 验证

```bash
openclaw agent --agent <artist-id> --message "你好，介绍一下你能做什么"
```

期望 PhotoArtist 用配置的昵称回应，并能列出"转换缩略图 / 智能选片 / 批量调色 / 前后对比"等能力。回应不符合时，按这个顺序排查：`openclaw agents list` → `~/.openclaw/workspace-<artist-id>/skills/` 是否有三个 photo-\* 目录 → `BOOTSTRAP.md` 是否非空 → 重启 gateway（参考 SKILL.md Step 4 的模式分岔）。

---

## 卸载

```bash
openclaw agents remove <artist-id>
openclaw agents remove <curator-id>
rm -rf ~/.openclaw/workspace-<artist-id> ~/.openclaw/workspace-<curator-id>
rm -rf ~/.openclaw/skills/photo-skills
```

最后同样需要让 gateway 重新加载——参考 [`openclaw-photo-agents-creator/SKILL.md`](./openclaw-photo-agents-creator/SKILL.md) Step 4 的模式分岔执行。

---

## 参考

- [`openclaw-photo-agents-creator/SKILL.md`](./openclaw-photo-agents-creator/SKILL.md)（参数、模型选择、依赖、配置细节的**唯一真理**）
- OpenClaw 官方文档：<https://docs.openclaw.ai/zh-CN/concepts/agent-workspace>
