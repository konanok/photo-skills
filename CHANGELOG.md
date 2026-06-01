# Changelog

This monorepo ships **four independently versioned ClawHub skills**.
Each skill maintains its own changelog. Update the skill-specific file
when you bump that skill's `VERSION` / `SKILL.md` frontmatter.

| Skill                         | Version source                                                                     | Changelog                                                                                    |
| ----------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| photo-toolkit                 | [`photo-toolkit/VERSION`](./photo-toolkit/VERSION)                                 | [`photo-toolkit/CHANGELOG.md`](./photo-toolkit/CHANGELOG.md)                                 |
| photo-screener                | [`photo-screener/VERSION`](./photo-screener/VERSION)                               | [`photo-screener/CHANGELOG.md`](./photo-screener/CHANGELOG.md)                               |
| photo-grader                  | [`photo-grader/VERSION`](./photo-grader/VERSION)                                   | [`photo-grader/CHANGELOG.md`](./photo-grader/CHANGELOG.md)                                   |
| openclaw-photo-agents-creator | [`openclaw-photo-agents-creator/VERSION`](./openclaw-photo-agents-creator/VERSION) | [`openclaw-photo-agents-creator/CHANGELOG.md`](./openclaw-photo-agents-creator/CHANGELOG.md) |

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning rules and release flow live in [RELEASING.md](./RELEASING.md) (strategy C).

## Cross-skill milestones

### 2026-06-02 — 1.0.1 patch round

Coordinated patch across three skills. Triggered by a user report of
"all 9 graded photos came out near-black" on real-server deployment.
Root-caused to **two independent latent bugs that masked each other**:

| Layer | Bug | Fix in skill |
|---|---|---|
| Engine (`grade.py`) | `--auto-match` wrote wrong PP3 field (DCP toggle instead of `[Exposure] HistogramMatching`); `raw.auto_bright` silently dropped; bad-schema JSON silently dropped fields | photo-grader 1.0.1 |
| Architecture (`create_agents.py`) | Hard constraints lived only in `BOOTSTRAP.md`, which OpenClaw silently filters and deletes once `setupCompletedAt` is set — leaving agents without "must spawn curator" rule, who then wrote broken JSON schema that hit the engine bugs above | openclaw-photo-agents-creator 1.0.1 |
| Toolkit (`find_by_date.py`) | EXIF read failures returned empty list silently on fuse/COS mounts, leading agents to abandon the script | photo-toolkit 1.0.1 |

End-to-end verification: same NEF + same params, mean luma 32.65 → 82.68
(2.5× brighter, matches in-camera JPG contrast). See each skill's CHANGELOG
for technical details.

| Skill                         | Version    | Published to ClawHub                  |
| ----------------------------- | ---------- | ------------------------------------- |
| photo-toolkit                 | 1.0.0 → 1.0.1 | not yet                             |
| photo-screener                | 1.0.0 (unchanged) | —                                |
| photo-grader                  | 1.0.0 → 1.0.1 | not yet                             |
| openclaw-photo-agents-creator | 1.0.0 → 1.0.1 | still blocked by slug namespace (see below) |

### 2026-05-20 — Initial public release on [ClawHub](https://clawhub.ai)

| Skill                         | ClawHub                                                                   | Status                        |
| ----------------------------- | ------------------------------------------------------------------------- | ----------------------------- |
| photo-toolkit                 | [konanok/photo-toolkit@1.0.0](https://clawhub.ai/konanok/photo-toolkit)   | published                     |
| photo-screener                | [konanok/photo-screener@1.0.0](https://clawhub.ai/konanok/photo-screener) | published                     |
| photo-grader                  | [konanok/photo-grader@1.0.0](https://clawhub.ai/konanok/photo-grader)     | published                     |
| openclaw-photo-agents-creator | —                                                                         | not published, see note below |

**`openclaw-photo-agents-creator` is not on ClawHub yet.** ClawHub reserves the
`openclaw-` prefix and `-openclaw` suffix as a protected slug namespace for the
official OpenClaw publisher. Our slug currently starts with `openclaw-` and
gets rejected at publish time:

> ✖ "openclaw-photo-agents-creator" uses the protected "openclaw" slug
> namespace. Choose a slug that does not start with "openclaw-" or end
> with "-openclaw".

### TODO: rename + republish

This is deferred — pending decision on the new slug. Notes for whoever
picks this up next (you, future-me, or an AI):

**Slug candidates (all namespace-compliant)**:

- `photo-agents-creator` — short, lines up with the other three `photo-*`
  skills. Loses the "OpenClaw-only" hint in the slug, but `SKILL.md`
  description and `metadata.openclaw.requires.bins: [openclaw]` already
  carry that information very clearly.
- `oc-photo-agents-creator` — keeps an "OpenClaw" hint via the `oc-`
  abbreviation, but `oc-` is ambiguous (Open Compute? Open Container?).
- `claw-photo-agents` / `photo-agents-claw` — uses `claw-`/`-claw`
  (allowed since `openclaw` is reserved but not `claw`); risks confusion
  with ClawHub-the-platform itself.

The leading candidate is **`photo-agents-creator`**, but the final call
is intentionally left open.

**Estimated change size (rename to any new slug)**:

- ~57 lines across ~12 files (~33 of which are mechanical
  `sed -i '' 's/old/new/g'` substitutions in README / INSTALL / RELEASING
  / CODEBUDDY etc.)
- 1 `git mv` for the directory
- ~10 lines of "real" thinking-required edits: `KNOWN_SKILLS` /
  `DEFAULT_SKILLS` / workflow path filter / `SKILL.md name:` field /
  this very CHANGELOG status section.

**Validation strategy (zero irreversible operations)**:

After renaming, run `bash scripts/publish.sh <new-slug>` (default
dry-run). Step `[4/6] checking ClawHub for existing version` calls
`clawhub inspect <slug> --json`, which is read-only — if the new slug
is also rejected by the namespace check, this step will surface it
without any publish happening. Only flip to `--no-dry-run` once the
inspect step returns "first publish".
