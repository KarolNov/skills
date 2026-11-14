# Tickets

Where a blueprint's tasks become tickets, set by `tickets.tracker` in `blueprint.json`. The brief stays the source of truth for *what* each task is; the ticket is where its *progress* lives, in the tool the team already watches. Read only the section for the configured tracker.

Rules for every tracker:

- **One ticket per task**, created when the brief is approved, never while it is a draft. Creating tickets is outward-facing: list them (title, labels, where) and create them after the user's yes.
- **Title**: `<task text>`, short. **Body**: one paragraph of what done looks like, the spec requirements it satisfies, and links to the brief and the review. The ticket points at the brief instead of copying it.
- **The brief links each ticket** from its task line: `- [ ] 1. <task> → <ticket link>`.
- **Done = the ticket is closed or done.** Apply closes it when the task is built and ticks the brief's checkbox in the same step. When apply or sync starts, read the tickets' states and tick any brief checkbox whose ticket someone closed by hand.
- Use the tracker's own conventions found during setup (area labels, milestones, a "ready for agent" label) rather than inventing parallel ones.

## `github`

**Set up**: create a `blueprint` label in the repo if missing (ask first; it is visible to anyone who can see the repo). Note the repo's area labels and open milestones.

**Create**: `gh issue create --label blueprint [--label <area>] [--milestone <existing milestone>] --title … --body …`. Add an area label or milestone only when one clearly fits the task. If the repo uses sub-issues, a tracking issue per blueprint titled `<change title>` with the task issues as its sub-issues works well; otherwise skip it. The docs side's `Tickets` link is the filtered list: `https://github.com/<owner>/<repo>/issues?q=label:blueprint+"<change id>"`, so put `Blueprint: <change id>` in every body.

**Done**: `gh issue close <n> --comment "<what was built, commit or PR>"`.

## `linear`

**Set up**: the team (and project, if the team uses projects) from the survey; a `blueprint` label on the team if missing.

**Create**: one issue per task in that team and project, labelled `blueprint`, in the team's first unstarted state. A parent issue titled `<change title>` with the tasks as sub-issues, when the team uses parent issues.

**Done**: move the issue to the team's first completed state.

## `jira`

**Set up**: the project key and its issue types; a `blueprint` label.

**Create**: an epic titled `<change title>`, and one story or task per brief task as its children, labelled `blueprint`.

**Done**: transition to the project's done status, adding a comment with the commit or PR.

## `notion`

Either an existing tasks database the team already uses (found in the survey), or a new `Tasks` database for blueprints, when the team has none or the user asks for one. Record its `collection://` data source as `tickets.location.tasks`.

**Set up, existing database**: read the database's schema: the title property, the status property and its "complete" group, and any project or relation property. A `Blueprint` relation from tasks to the Blueprints database makes each blueprint show its tickets, but adding it changes the team's database: propose it and add it only on a yes. Without it, tasks link the review in their body.

**Set up, new database**: create it under the `Specs & blueprints` root, beside Specs and Blueprints, after the docs databases exist:
`CREATE TABLE ("Task" TITLE, "Status" STATUS('To do':gray:to_do, 'In progress':blue:in_progress, 'Done':green:complete), "Blueprint" RELATION('<blueprints data source>', DUAL 'Tasks'), "Order" NUMBER, "PR" URL)`
Add a board view grouped by Status if the user wants one. Each blueprint row then lists its tasks through the `Tasks` relation, and the docs side's tickets link is the Blueprint row itself.

**Create**: one row per task, title = the task, status = the first "to do" option, `Order` = the task number (new database), and the relation or project properties the database uses.

**Done**: set the status to the first option of its "complete" group, and fill `PR` when there is one.

## `none`

Tasks stay as checkboxes in the brief. Apply ticks them there; nothing else to do.
