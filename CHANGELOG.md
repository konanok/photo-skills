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

To unblock release we'll need to rename the skill — the leading candidate is
`photo-agents-creator`, which also lines up nicely with the other three
`photo-*` skills. That rename touches the directory name, `SKILL.md` `name`,
several scripts, and inter-skill references in changelogs / READMEs, so it's
deferred until we're ready to do it cleanly.
