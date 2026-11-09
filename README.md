# Skills

A collection of [Claude Code](https://claude.com/claude-code) skills I use day to day.

## Install

### As a plugin marketplace (recommended)

In Claude Code:

```
/plugin marketplace add KarolNov/skills
/plugin install karolnov-skills@karolnov-skills
```

### Manually

Copy any skill folder into your personal or project skills directory:

```bash
git clone https://github.com/KarolNov/skills.git
cp -r skills/skills/<skill-name> ~/.claude/skills/        # all projects
cp -r skills/skills/<skill-name> .claude/skills/          # one project
```

## Skills

| Skill | Description |
| ----- | ----------- |
| _coming soon_ | |

## Repository layout

```
.claude-plugin/marketplace.json   # plugin marketplace manifest
skills/<skill-name>/SKILL.md      # one folder per skill
template/SKILL.md                 # starting point for new skills
```

## Adding a skill

1. Copy `template/` to `skills/<skill-name>/` (lowercase, hyphenated).
2. Fill in the `name` and `description` frontmatter in `SKILL.md`; `name` must match the folder name.
3. Add `"./skills/<skill-name>"` to the `skills` array in `.claude-plugin/marketplace.json`.
4. Add a row to the table above.

## License

[MIT](LICENSE)
