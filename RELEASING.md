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
- [ ] `CHANGELOG.md` 已写入对应条目（见下文）
- [ ] 跨 skill 兼容性已确认（creator 的 SKILL.md 中"配套版本"文字已对齐）
- [ ] `bash scripts/publish.sh <skill> --dry-run` 通过
- [ ] 已签入 ClawHub：`clawhub whoami` 返回正确身份

---

## 四、CHANGELOG 维护

仓库根维护一份 `CHANGELOG.md`（首次发版时由维护者创建），格式建议参考 [Keep a Changelog](https://keepachangelog.com/)：

```markdown
# Changelog

## [Unreleased]

### Added

- ...

## [1.1.0] - 2026-05-15

### photo-grader

- Fix: HSL hue mapping for skin tones (1.0.0 → 1.0.1)

### photo-toolkit

- Feat: deflicker 支持 8-bit 输入 (1.0.0 → 1.1.0)

### openclaw-photo-agents-creator

- Bump to 1.1.0 to match repo tag; updated compatibility notes for photo-toolkit ≥ 1.1
```

**约定**：

- `[Unreleased]` 段持续累积，发版时移到具体版本号下并打 git tag
- 按 skill 分组，方便后续直接复制到 `clawhub skill publish --changelog`

---

## 五、发版流程（手动版，Day-1 起步）

### 场景 A — 单 skill patch 修复

只动了 `photo-grader/scripts/grade.py` 的 bug：

```bash
# 1. bump version（只改 SKILL.md，VERSION 由 hook 自动同步）
sed -i '' 's/^version: 1.0.0$/version: 1.0.1/' photo-grader/SKILL.md

# 2. 把 CHANGELOG [Unreleased] 中的 photo-grader 段落转为 [1.0.1]
vim CHANGELOG.md

# 3. commit（pre-commit hook 跑 sync 自动同步 VERSION 并 git add 进来）
git commit -am "release(grader): 1.0.1"
git push

# 4. dry-run（publish.sh 自动从 SKILL.md 读 version、从 CHANGELOG.md 提取段落）
bash scripts/publish.sh photo-grader --dry-run

# 5. 正式发布
bash scripts/publish.sh photo-grader
```

> ⚠️ **不要打 git tag**——仓库 tag 只在 creator 同步发版（场景 C）时才打。

### 场景 B — 多 skill 同步发版

比如 `config.toml` 重构同时影响 4 个 skill：

```bash
# 1. bump 4 个 SKILL.md 的 version
for d in photo-toolkit photo-screener photo-grader openclaw-photo-agents-creator; do
    sed -i '' 's/^version: 1.0.0$/version: 1.1.0/' "$d/SKILL.md"
done

# 2. CHANGELOG 写入 [1.1.0] 段（按 skill 分组，方便 publish.sh 自动提取）
vim CHANGELOG.md

# 3. commit（hook 自动同步 4 个 VERSION 文件）
git commit -am "release: unify config schema, all skills bumped to 1.1.0"

# 4. 逐个 dry-run + 发布（也可以用 clawhub sync 批量；publish.sh 更稳）
for s in photo-toolkit photo-screener photo-grader openclaw-photo-agents-creator; do
    bash scripts/publish.sh "$s" --dry-run || break
done

for s in photo-toolkit photo-screener photo-grader openclaw-photo-agents-creator; do
    bash scripts/publish.sh "$s" || break
done
```

> 也可以用 `clawhub sync --root . --all --bump minor`——但它**不会经过 publish.sh 的一致性校验**。推荐 publish.sh 逐个发，更可控。

### 场景 C — 套件整体发版（creator 跟仓库 tag）

`openclaw-photo-agents-creator` 自身有变更，或者你想给"整套 photo-skills"打一个发行版（即便底层 skill 没全改）：

```bash
# 1. bump creator 的 version 到目标 tag 版本
sed -i '' 's/^version: .*/version: 1.2.0/' openclaw-photo-agents-creator/SKILL.md

# 2. CHANGELOG 写入完整 [1.2.0] 段
vim CHANGELOG.md

# 3. commit（hook 同步 VERSION）
git commit -am "release: v1.2.0"

# 4. 打 git tag（策略 C 的核心：仓库 tag = creator 版本号）
git tag -a v1.2.0 -m "photo-skills v1.2.0"
git push origin master v1.2.0

# 5. 发布 creator
bash scripts/publish.sh openclaw-photo-agents-creator --dry-run
bash scripts/publish.sh openclaw-photo-agents-creator

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

> 推论：**`--dry-run` 必须养成习惯**。配合下文的 GitHub Actions PR-dry-run 把关。

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
- [ ] 在 4 个 skill 各跑一次 `bash scripts/publish.sh <skill> --dry-run`，确认无报错
- [ ] 创建仓库根 `CHANGELOG.md` 并写入 `[1.0.0]` 段
- [ ] 打 `v1.0.0` tag
- [ ] 按场景 C 流程发布 creator + 三个底层 skill
- [ ] 在 ClawHub 网页确认 4 个条目已上线、可搜到、metadata 正确

---

## 参考

- [ClawHub 发布文档](https://docs.openclaw.ai/clawhub/publishing)
- [Skill format](https://docs.openclaw.ai/clawhub/skill-format)
- [ClawHub CLI reference](https://docs.openclaw.ai/clawhub/cli)
- [Keep a Changelog](https://keepachangelog.com/)
