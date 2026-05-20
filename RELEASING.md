# RELEASING — 发布与更新指南

> 面向**维护者**。指导如何把 `photo-skills` 的 4 个 skill 发布到 [ClawHub](https://clawhub.ai) 并持续更新。
>
> 用户安装文档见 [INSTALL.md](./INSTALL.md)。

---

## 一、ClawHub 发布形态（必读约束）

ClawHub 的硬规定，违反这些约束的发版会失败或留下隐患：

| 约束                                       | 含义                                                                                                         |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| **1 文件夹 = 1 SKILL.md = 1 ClawHub 条目** | 不能把多 skill 打包成一个；本仓库的 4 个 skill 各自独立发布                                                  |
| **强制 `--version` semver**                | 每次 `clawhub skill publish` 必须递增版本号，不能覆盖                                                        |
| **强制 MIT-0 许可证**                      | 所有发布的 skill 自动采用 MIT-0，不支持 per-skill 自定义 license                                             |
| **没有"撤回单版本"命令**                   | 发出去的版本不能 yank，只能发新版修复 + changelog 标注                                                       |
| **不支持 skill-to-skill 硬依赖**           | `requires` 只能声明 env/bins/anyBins/config，**不能**声明对其他 skill 的版本依赖；只能在正文里以文字提示用户 |
| **Bundle ≤ 50 MB**，**仅文本类文件**       | 模型权重、二进制资源不能进 skill 包                                                                          |

---

## 二、版本号策略（策略 C：主从混合）

本项目采用**主从混合**版本策略：

### `openclaw-photo-agents-creator`（套件入口，跟仓库 tag 同步）

- **版本号 = 仓库 git tag**：仓库打 `v1.2.0` → creator 发 `1.2.0`
- 它代表"整套 photo-skills 的发行版本"，是用户看到的**入口版本号**
- 即使 creator 自身代码没改，但底层 3 个 skill 有重大变更时，creator 也要 bump major/minor 同步

### `photo-toolkit` / `photo-screener` / `photo-grader`（独立迭代）

- 各自按自己的变更节奏 semver
- 例：只改了 `photo-grader/scripts/grade.py` → 只 bump `photo-grader` patch；其他三个保持原版本

### 兼容性承诺（用户预期）

| 版本变化                   | 含义                                                                   |
| -------------------------- | ---------------------------------------------------------------------- |
| `1.0.x` → `1.0.y`（patch） | bug fix，向后完全兼容                                                  |
| `1.0.x` → `1.1.0`（minor） | 新功能，向后兼容                                                       |
| `1.x.x` → `2.0.0`（major） | **破坏性变更**——`config.toml` 字段、CLI 参数、JSON schema 改动都属此类 |

### 跨 skill 兼容性（重要）

ClawHub 不支持 skill 间硬依赖，所以**靠纪律**保证 4 个 skill 配合工作：

- `openclaw-photo-agents-creator/scripts/create_agents.py` 与三个底层 skill 的接口耦合紧（读 `setup_deps.sh`、`config.example.toml`）
- **任何会让 creator 旧版无法驱动新版底层 skill 的变更，三个底层 skill 都必须走 major bump**
- creator 的 SKILL.md 在 "Triggers / Requirements" 中**用文字注明**："本工具配套 `photo-toolkit ≥ X.Y` / `photo-screener ≥ X.Y` / `photo-grader ≥ X.Y`"——发布前手工对齐

---

## 二.A、版本号双轨制（SKILL.md ↔ VERSION）

每个 skill 的版本号有两份物理表示：

| 文件                                              | 角色                            | 谁读它                                                   |
| ------------------------------------------------- | ------------------------------- | -------------------------------------------------------- |
| `<skill>/SKILL.md` 的 frontmatter `version:` 字段 | **真理源**                      | ClawHub 官方推荐形态、`publish.sh` 脚本、AI/工具静态扫描 |
| `<skill>/VERSION`                                 | **派生品**（一行版本号 + 换行） | OSS 生态约定、想 `cat VERSION` 简单读取的工具/脚本       |

### 三层防护（机器保证一致）

| 层                     | 机制                                                                          | 谁负责                                       |
| ---------------------- | ----------------------------------------------------------------------------- | -------------------------------------------- |
| **L1 同步脚本**        | `scripts/sync_versions.sh`（默认 sync 模式按 dirty 状态智能同步；冲突时拒绝） | 维护者本地手动跑 / pre-commit hook 自动跑    |
| **L2 pre-commit hook** | `.githooks/pre-commit` 在 commit 前跑 sync，发现冲突拒绝提交                  | `bash scripts/install_hooks.sh` 启用一次即可 |
| **L3 CI 校验**         | `.github/workflows/version-check.yml` 在 PR/push 时跑 `sync --check`          | 自动                                         |

### sync 脚本判定矩阵

设 `S` = SKILL.md frontmatter version，`V` = VERSION 文件内容。`dirty` = 该文件相对最近一次 commit 有改动。

| S vs V | S_dirty | V_dirty | 处置                                                        |
| ------ | ------- | ------- | ----------------------------------------------------------- |
| 相等   | \*      | \*      | ✓ 通过                                                      |
| 不等   | true    | false   | ↻ 用 S 覆盖 V（你改了 SKILL.md，自动同步 VERSION）          |
| 不等   | false   | true    | ↻ 用 V 覆盖 S（你改了 VERSION，自动同步 SKILL.md）          |
| 不等   | true    | true    | ✗ **冲突**，拒绝；用 `--force-from=skill\|version` 显式选边 |
| 不等   | false   | false   | ✗ **历史漂移**（之前 commit 就不一致了），拒绝；手工修复    |

### 常用命令

```bash
# 校验全部（CI 用同款命令）
bash scripts/sync_versions.sh --check

# 智能同步（hook 自动调用，本地也可手动跑）
bash scripts/sync_versions.sh

# 解冲突（场景 4：双方都被改过，告诉脚本以哪边为准）
bash scripts/sync_versions.sh --force-from=skill   # SKILL.md 是真理
bash scripts/sync_versions.sh --force-from=version # VERSION 是真理

# 只处理单个 skill
bash scripts/sync_versions.sh photo-grader
```

### 维护者实际工作流

```bash
# 你只需要改一个地方（推荐改 SKILL.md，因为 ClawHub 直接读它）
vim photo-grader/SKILL.md            # bump frontmatter: version: 1.0.0 → 1.0.1

# 提交（pre-commit hook 自动跑 sync，把 VERSION 同步并 git add 进本次 commit）
git commit -am "release(grader): 1.0.1"
```

物理上**不可能只改一处不改另一处**——hook 会拦截，CI 会再拦一次。

---

## 三、发版前检查清单

每次发版前依次确认：

- [ ] 改动已合入 master
- [ ] 本地 `git pull origin master` 是最新
- [ ] 受影响 skill 的 `SKILL.md` frontmatter `version` 已 bump（VERSION 文件由 hook / `sync_versions.sh` 自动同步，无需手改）
- [ ] `bash scripts/sync_versions.sh --check` 全绿（hook + CI 已经覆盖，但本地养成习惯）
- [ ] `<skill>/CHANGELOG.md` 已写入对应条目（见下文）
- [ ] 跨 skill 兼容性已确认（creator 的 SKILL.md 中"配套版本"文字已对齐）
- [ ] `bash scripts/publish.sh <skill>` dry-run 通过（默认就是 dry-run，不会触达 ClawHub）
- [ ] 已签入 ClawHub：`clawhub whoami` 返回正确身份

---

## 三-2、`publish.sh` 的安全开关（红按钮）

`bash scripts/publish.sh <skill>` **默认运行在 dry-run 模式**——会跑完前 5 步
所有校验、打印将要执行的 `clawhub skill publish` 命令，但**不会真正调用 clawhub**。

要真正发布需要**两个条件同时满足**：

1. 显式追加 `--no-dry-run`
2. 进程的 stdin + stderr 都是 TTY（人在真实终端前敲命令）

```bash
bash scripts/publish.sh <skill>                  # dry-run，安全
bash scripts/publish.sh <skill> --no-dry-run     # 真发，但需要 TTY
```

为什么要 TTY 校验？一句话：**因为光靠 `--no-dry-run` flag 拦不住 AI**。
AI 工具调用、CI 任务、`bash -c "..."`、管道、shell 子进程，都没有真正的 TTY。
TTY 校验把这些非交互场景物理拦下，让"调试中误发布"这条历史路径彻底关闭。

### CI 旁路

GitHub Actions 也是 non-interactive，会被 TTY 检查挡住。需要在 workflow yaml 里
显式设置环境变量：

```yaml
- name: Publish photo-grader
  env:
    CLAWHUB_PUBLISH_I_ACCEPT_IRREVERSIBILITY: "1"
  run: bash scripts/publish.sh photo-grader --no-dry-run
```

这个 env var 名字故意冗长，目的是让它**只能存在于审计可见的 workflow 文件里**——
不会有人无意中把它 export 到日常 shell。每次 workflow 改动都会进 PR review，
等于多一道人眼把关。

### 设计依据

1. `clawhub skill publish` 子命令**没有原生 `--dry-run`**（只有 `clawhub sync` 有）
2. 历史上发生过两次"AI 在调试 / 验证命令格式时不小心真发布"事件——两次都是
   AI 在工具调用里追加 `--no-dry-run` 就触发，纯 flag 拦不住

`--no-dry-run` + TTY 这套组合是"红按钮"——**禁止任何 AI / 自动化脚本绕过**。
合法触发者只有两类：当面操作的发版人（满足 TTY），或带审计 env var 的 CI 任务。

---

## 三-3、调试纪律：先复现，再归因

当任何外部 CLI（`clawhub`、`rawtherapee-cli`、`openclaw` 等）报错时，
**禁止**仅凭报错文本 + 直觉就推断"它内部有 X bug"然后改我们的代码去绕。
流程必须是：

1. **本地最小复现**：把那条命令脱离我们的脚本环境，手工跑一遍，确认能稳定重现。
2. **读源 / 读文档**：clawhub 等 npm 工具的源码就在
   `~/.local/share/fnm/node-versions/*/installation/lib/node_modules/clawhub/dist/`，
   可直接读。RawTherapee、ffmpeg 都有详尽的 `--help` / man page。
3. **做对照实验**：构造一个能区分"是它的 bug"和"是我们用错了"的最小实验。
   例如：怀疑 `commander.js` 解析以 `-` 开头的多行字符串有问题？写 6 行 JS
   直接用 `commander` v12 跑一遍同样的 argv，看到底有没有问题。
4. **再写 fix + commit message**，commit message 里必须包含验证步骤和参考依据
   （源码行号、最小复现命令等）。

### 反面教训

本项目早期发生过一次具体的误诊：撞到 `clawhub skill publish` 报
`Error: Path must be a folder`，没做 root-cause 分析，凭直觉断定
"`clawhub` 用 `commander.js`，应该是 multiline 含 `-` 开头列表的 changelog
被误解析为新 flag"，于是把 CHANGELOG 里的列表前缀 `-` 全替换成 `*`，
还把这条未经验证的"经验"写进了 `scripts/publish.py` docstring 和这份
RELEASING.md。dry-run 看起来"通过了"——但 dry-run 根本不调真 clawhub，
所以这个伪修复无法被证伪。

后来通过读 `clawhub` 源码 + `commander` v12 本地对照实验，发现根本没有什么
"`-` 解析陷阱"，真 root cause 是 `clawhub` 的 `resolveWorkdir()` 在装了
OpenClaw 的机器上 fallback 到 OpenClaw default workspace，跟 changelog 内容
毫无关系。真修复就是 `scripts/publish.py` 里现在的 `--workdir <repo-abs>` +
绝对 path —— 跟 changelog 完全无关。

这套流程跟前面"红按钮"是一脉相承的：**对不可逆 / 难以纠错的操作，多一道纪律**。
误诊不止浪费时间，还会在仓库里留下假"经验"污染未来所有读者。

---

## 四、CHANGELOG 维护

**每个 skill 维护自己的 `CHANGELOG.md`**（与 `SKILL.md` / `VERSION` 同目录）。
仓库根 `CHANGELOG.md` 仅作汇总索引，列出 4 个 skill 的链接和跨 skill 里程碑。

```
photo-skills/
├── CHANGELOG.md                              ← 索引页 + 跨 skill 里程碑
├── photo-toolkit/
│   ├── SKILL.md
│   ├── VERSION
│   └── CHANGELOG.md                          ← 该 skill 的 release notes
├── photo-screener/CHANGELOG.md
├── photo-grader/CHANGELOG.md
└── openclaw-photo-agents-creator/CHANGELOG.md
```

每个 `<skill>/CHANGELOG.md` 格式参考 [Keep a Changelog](https://keepachangelog.com/)：

```markdown
# Changelog — photo-grader

## [Unreleased]

## [1.0.1] - 2026-05-25

### Fixed

- HSL hue mapping for skin tones.

## [1.0.0] - 2026-05-20

### Added

- Initial public release on ClawHub.
```

**约定**：

- 每个 skill 的 `[Unreleased]` 段持续累积，bump version 时把内容移到具体版本号段
- `publish.sh` 自动从 `<skill>/CHANGELOG.md` 提取 `## [VERSION]` 段作为 release notes
- 跨 skill 的同步发版（如 1.0.0 首发）需要 4 份 CHANGELOG 各写一份；可以在根 `CHANGELOG.md` 的 "Cross-skill milestones" 段记一笔

---

## 五、发版流程（手动版，Day-1 起步）

### 场景 A — 单 skill patch 修复

只动了 `photo-grader/scripts/grade.py` 的 bug：

```bash
# 1. bump version（只改 SKILL.md，VERSION 由 hook 自动同步）
sed -i '' 's/^version: 1.0.0$/version: 1.0.1/' photo-grader/SKILL.md

# 2. 把 photo-grader/CHANGELOG.md 的 [Unreleased] 段落转为 [1.0.1]
vim photo-grader/CHANGELOG.md

# 3. commit（pre-commit hook 跑 sync 自动同步 VERSION 并 git add 进来）
git commit -am "release(grader): 1.0.1"
git push

# 4. dry-run（默认行为：publish.sh 不带 --no-dry-run 时只打印，不触达 ClawHub）
bash scripts/publish.sh photo-grader

# 5. 正式发布（红按钮：必须显式 --no-dry-run，AI/自动化禁止自行添加）
bash scripts/publish.sh photo-grader --no-dry-run
```

> ⚠️ **不要打 git tag**——仓库 tag 只在 creator 同步发版（场景 C）时才打。

### 场景 B — 多 skill 同步发版

比如 `config.toml` 重构同时影响 4 个 skill：

```bash
# 1. bump 4 个 SKILL.md 的 version
for d in photo-toolkit photo-screener photo-grader openclaw-photo-agents-creator; do
    sed -i '' 's/^version: 1.0.0$/version: 1.1.0/' "$d/SKILL.md"
done

# 2. 4 份 CHANGELOG 各写入 [1.1.0] 段（publish.sh 从 <skill>/CHANGELOG.md 自动提取）
for d in photo-toolkit photo-screener photo-grader openclaw-photo-agents-creator; do
    vim "$d/CHANGELOG.md"
done

# 3. commit（hook 自动同步 4 个 VERSION 文件）
git commit -am "release: unify config schema, all skills bumped to 1.1.0"

# 4. 逐个 dry-run（默认；不会触达 ClawHub），确认无报错后再加 --no-dry-run 真发
for s in photo-toolkit photo-screener photo-grader openclaw-photo-agents-creator; do
    bash scripts/publish.sh "$s" || break
done

# 4b. 真发布（红按钮，需显式 --no-dry-run）
for s in photo-toolkit photo-screener photo-grader openclaw-photo-agents-creator; do
    bash scripts/publish.sh "$s" --no-dry-run || break
done
```

> 关于 `clawhub sync --root . --all --bump <type>`：它一条命令就能扫全仓库并批量推送，看着确实诱人。
> 但目前我们暂时不走这条路，原因有几条：
>
> - **版本号被 sync 接管**。`--bump patch/minor/major` 是在 ClawHub 当前最新版基础上自动 +1，
>   不读 `SKILL.md` frontmatter 里的 `version`——也就绕开了我们"frontmatter `version` 是真理源
>   - VERSION 派生 + CHANGELOG `## [VERSION]` 段三处对齐"的整套约束。
> - **整批共用一个 changelog**。`--changelog "<text>"` 一传 4 个 skill 都会贴同一段，
>   每 skill 独立的 release notes 用不上。
> - **跳过一致性校验**。`scripts/sync_versions.sh --check`（含 changelog 段校验）和 publish.py 的
>   ClawHub 查重都不会跑。
> - **批量误推风险**。仓库里临时多出来的 WIP skill 目录可能被一起扫上去。
>
> 等 ClawHub CLI 把 publish 的 dry-run、`--changelog-file` 之类补齐，或者我们的 4 个 skill 多到
> 真的需要批量管理时，再回头评估。短期内 publish.py 逐个发更稳。

### 场景 C — 套件整体发版（creator 跟仓库 tag）

`openclaw-photo-agents-creator` 自身有变更，或者你想给"整套 photo-skills"打一个发行版（即便底层 skill 没全改）：

```bash
# 1. bump creator 的 version 到目标 tag 版本
sed -i '' 's/^version: .*/version: 1.2.0/' openclaw-photo-agents-creator/SKILL.md

# 2. 在 openclaw-photo-agents-creator/CHANGELOG.md 写入 [1.2.0] 段
#    （如有底层 skill 同步 bump，也分别更新对应 CHANGELOG）
vim openclaw-photo-agents-creator/CHANGELOG.md

# 3. commit（hook 同步 VERSION）
git commit -am "release: v1.2.0"

# 4. 打 git tag（策略 C 的核心：仓库 tag = creator 版本号）
git tag -a v1.2.0 -m "photo-skills v1.2.0"
git push origin master v1.2.0

# 5. 发布 creator
bash scripts/publish.sh openclaw-photo-agents-creator              # dry-run 默认
bash scripts/publish.sh openclaw-photo-agents-creator --no-dry-run # 真发

# 6. 如果同发行版里也包含底层 skill 变更，按场景 A / B 发它们
```

---

## 六、撤回与紧急止血

ClawHub 没有"撤回单版本"的 CLI 命令。出问题时按严重性升级处理：

| 严重性                      | 处理                                                                                                              |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **轻微 bug**                | 不撤回旧版，直接发 patch（例：1.0.0 含 bug → 发 1.0.1，CHANGELOG 标注 "1.0.0 has known issue, please upgrade"）   |
| **严重 bug / 数据安全问题** | 立即发 patch + 联系 [ClawHub 审核](https://clawhub.ai)，按 `package report` / `package appeal` 流程申请下架旧版本 |
| **机密误传 / 法律问题**     | `clawhub delete <slug> --reason "..."` 软删除整个 skill（核选项；可用 `undelete` 恢复）                           |

> 推论：**默认 dry-run 必须养成习惯**（publish.sh 已经默认就是 dry-run）。配合下文的 GitHub Actions PR-dry-run 把关。

---

## 七、自动化发布（GitHub Actions，推广阶段强烈推荐）

### 价值

- PR 自动 dry-run，避免合并坏版本
- tag push 自动发布，更新节奏可见
- ClawHub `explore --sort updated` / `--sort trending` 是按更新活跃度排序的，自动化 = 持续曝光

### 起步配置

1. **GitHub Secrets** 加入 `CLAWHUB_TOKEN`（在 ClawHub 网页生成 API token）
2. 在 `.github/workflows/clawhub-publish.yml` 写 workflow（参考下方模板）
3. **必须 pin 到稳定 tag**（如 `@v0.12.0`），**禁止用 `@main`**——文档明确这是反模式

```yaml
name: Publish to ClawHub

on:
  pull_request:
    paths:
      - "photo-toolkit/**"
      - "photo-screener/**"
      - "photo-grader/**"
      - "openclaw-photo-agents-creator/**"
  push:
    tags: ["v*"]
  workflow_dispatch:

jobs:
  dry-run:
    if: github.event_name == 'pull_request'
    uses: openclaw/clawhub/.github/workflows/package-publish.yml@v0.12.0
    with:
      dry_run: true

  publish:
    if: github.event_name == 'workflow_dispatch' || startsWith(github.ref, 'refs/tags/')
    permissions:
      contents: read
      id-token: write # Trusted Publishing 需要
    uses: openclaw/clawhub/.github/workflows/package-publish.yml@v0.12.0
    with:
      dry_run: false
    secrets:
      clawhub_token: ${{ secrets.CLAWHUB_TOKEN }}
```

> ⚠️ 上面这个 reusable workflow 是 ClawHub 官方为 **package（plugin）** 设计的，对 **skill 包**的支持需要核验。如果不行，备用方案是手写 workflow 直接调 `clawhub skill publish`：

```yaml
# 备用方案（如果上面的官方 workflow 不接受 skill 包）
- name: Install clawhub CLI
  run: npm i -g clawhub
- name: Login
  run: clawhub login --token "${{ secrets.CLAWHUB_TOKEN }}"
- name: Publish photo-grader
  run: clawhub skill publish ./photo-grader --version "${{ github.ref_name }}" --changelog "..."
# ... 重复其他 skill
```

---

## 八、推广阶段的发版节奏

| 阶段                   | 节奏                                         | 工具                         |
| ---------------------- | -------------------------------------------- | ---------------------------- |
| **alpha**（前 1 个月） | 改一次发一次，`1.0.0-alpha.1`、`alpha.2` ... | 手动 `clawhub skill publish` |
| **beta**（验证期）     | 每周一发，攒 changelog                       | 手动 `sync`                  |
| **stable**（推广期）   | 每 2~4 周发一次小版本，重大变更打 tag        | GitHub Actions tag 触发      |

最忌讳：**更新太频繁**（用户疲于升级）/ **太久不更新**（用户怀疑项目死了）。保持稳定节奏即可。

---

## 九、首次发布 Checklist（仅一次性）

在第一次推上 ClawHub 前完成：

- [ ] 全局安装 `clawhub` CLI：`npm i -g clawhub`
- [ ] `clawhub login` 完成 GitHub OAuth
- [ ] `clawhub whoami` 确认身份
- [ ] 启用 git hooks：`bash scripts/install_hooks.sh`（一次性，本仓库的 `.githooks/pre-commit` 会自动拦截版本号不一致）
- [ ] `bash scripts/sync_versions.sh --check` 输出 4 ✓
- [ ] 4 个 SKILL.md 的 frontmatter 已补齐 ClawHub 推荐字段（参考 [Skill format](https://docs.openclaw.ai/clawhub/skill-format)）：
  - `name` / `description` / `version`
  - `metadata.openclaw.homepage`（指向 GitHub repo）
  - `metadata.openclaw.requires.env` / `requires.bins`（依赖声明）
  - `metadata.openclaw.emoji`
- [ ] 在 4 个 skill 各跑一次 `bash scripts/publish.sh <skill>`（默认 dry-run），确认无报错
- [ ] 4 个 `<skill>/CHANGELOG.md` 写入 `[1.0.0]` 段（根 `CHANGELOG.md` 仅作索引）
- [ ] 打 `v1.0.0` tag
- [ ] 按场景 C 流程发布 creator + 三个底层 skill
- [ ] 在 ClawHub 网页确认 4 个条目已上线、可搜到、metadata 正确

---

## 参考

- [ClawHub 发布文档](https://docs.openclaw.ai/clawhub/publishing)
- [Skill format](https://docs.openclaw.ai/clawhub/skill-format)
- [ClawHub CLI reference](https://docs.openclaw.ai/clawhub/cli)
- [Keep a Changelog](https://keepachangelog.com/)
