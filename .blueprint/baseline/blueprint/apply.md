## Purpose

Builds an approved blueprint one task at a time, keeps its tickets and brief current, and then folds its spec delta into the capability specs, so the specs change together with the code.

## Requirements

### Requirement: Change selection

`/blueprint apply` SHALL build the change named in its arguments. With no name, it SHALL pick the only change marked `approved` or `building`, or list them and ask when there are several.

- **Scenario: Two changes in flight**
  - **GIVEN** two changes marked `approved`
  - **WHEN** the user runs `/blueprint apply`
  - **THEN** both are listed and the user picks one

### Requirement: Resume from tracker state

At the start, apply SHALL read the tickets and tick each brief task whose ticket was closed by hand. It SHALL then put any new review comments to the user as proposed brief changes, and settle Open questions, before building.

- **Scenario: Ticket closed by hand**
  - **GIVEN** someone closed task 2's ticket
  - **WHEN** apply starts
  - **THEN** task 2 is ticked in the brief and building starts at the next open task

### Requirement: Drift checked before building

Apply SHALL check drift for every capability the change touches. It SHALL send drifted ones to `blueprint-drift` or `blueprint-sync` before building on them.

- **Scenario: Touched spec edited**
  - **GIVEN** a touched capability's spec was edited since it was last synced
  - **WHEN** apply starts
  - **THEN** the user is asked to settle that capability first, and its MODIFIED blocks are checked again

### Requirement: Branch and status

When the session is on the default branch, apply SHALL create a branch for the change. It SHALL set the brief to `building` and record the branch on the brief and in `blueprint.json`.

- **Scenario: On main**
  - **WHEN** apply starts on the default branch
  - **THEN** a branch is created for the change and recorded

### Requirement: Split into PRs

Before building a brief with no PR plan, apply SHALL judge its size. When it is big (more than about four build tasks, several capabilities whose code doesn't overlap, or more than about 400 changed lines), apply SHALL propose splitting its tasks into groups, each one branch, one PR and one session. A group SHALL be stacked on the group whose code it builds on, or whose files it edits, and parallel otherwise. Folding the delta SHALL be its own last group, run after every other group has merged; code groups SHALL leave `.blueprint/` alone apart from recording `building`. Apply SHALL show the proposed plan as a diagram as well as a table: a tree of branches in which a stacked group sits under its base, parallel groups are siblings, and the groups that can start now are marked. When blueprint-ui's `split` tool is in the session, apply SHALL show the plan through it instead of drawing the tree in chat, with the prompt each group's session starts with, and SHALL call it again once the plan is approved and as groups start, open PRs and merge. After the user approves, the plan SHALL be written into the brief, and apply SHALL offer a fresh session for each group that can start now: those based on the default branch, and those stacked on a group whose PR is open. `/blueprint apply <change> <group>` SHALL build only that group's tasks, on its own branch, and open its PR against its base.

- **Scenario: Small change**
  - **GIVEN** a brief with three build tasks in one capability
  - **WHEN** apply starts
  - **THEN** it builds them as one PR, with no split proposed
- **Scenario: Stacked and parallel**
  - **GIVEN** tasks 3 and 4 need the store that tasks 1 and 2 add, and task 5 touches only the admin UI
  - **WHEN** apply proposes the split
  - **THEN** group 2 (tasks 3, 4) is stacked on group 1 (tasks 1, 2), group 3 (task 5) runs in parallel from the default branch, and Specs comes last
  - **AND** the diagram shows group 2 under group 1, and groups 1 and 3 as starting now
- **Scenario: With the pane**
  - **GIVEN** blueprint-ui is installed
  - **WHEN** apply proposes the split
  - **THEN** the plan shows in the blueprint pane, each group with its session's prompt, and chat shows the table alone
- **Scenario: Build one group**
  - **GIVEN** the PR plan is on the brief and group 1's PR is open
  - **WHEN** the user runs `/blueprint apply add-sso-login 2`
  - **THEN** only tasks 3 and 4 are built, on a branch cut from group 1's, and the PR targets group 1's branch

### Requirement: One task at a time

Apply SHALL build the unticked tasks in order. After each one passes its checks, it SHALL close that task's ticket and tick it in the brief. When a session gets long, it MAY stop after a task and name the next one.

- **Scenario: Task done**
  - **WHEN** a task is built and its checks pass
  - **THEN** its ticket is closed with a note and its checkbox is ticked

### Requirement: Brief amended before code diverges

When a task can't be built as written, or the delta turns out wrong, apply SHALL stop and propose an amendment. After the user's yes, the brief is updated first (with a "Changed during build" decision), the review is rebuilt, and then building continues.

- **Scenario: Impossible requirement**
  - **WHEN** building shows a requirement can't hold
  - **THEN** nothing more is built until the user approves the amended brief

### Requirement: Verify against the delta

Before the last task, apply SHALL check every delta requirement and scenario against the code and record evidence for each as covered, missing or contradicts. It SHALL also propose anchors for changed files no capability covers.

- **Scenario: Missing evidence**
  - **WHEN** a scenario has no test or code path
  - **THEN** it is fixed, or the brief is amended with the user's yes, before the delta is folded

### Requirement: Fold the delta into specs

Apply SHALL merge the delta in the order RENAMED, REMOVED, MODIFIED (replacing whole blocks by name), then ADDED. A new capability's page SHALL be created inside its domain when its name has one, after checking the name against the naming rule. Apply SHALL show each merged spec as a diff and write it after approval, followed by the spec bookkeeping. When a folded capability belongs to a domain, apply SHALL refresh that domain overview's capability list. It SHALL then mark the brief `applied`, and end its report with the `drift.py hint` line when there is one.

- **Scenario: Not-yet-built marker**
  - **GIVEN** a requirement carries `Not yet built → <this blueprint>`
  - **WHEN** the delta is folded
  - **THEN** the marker line is dropped
- **Scenario: New capability in a domain**
  - **WHEN** a delta adds `board/pads` under domain `board`
  - **THEN** the `board` overview's Capabilities list gains `board/pads`, and the rest of the overview is untouched

### Requirement: Pending target repo

When `blueprint.json` has `targetRepo`, apply SHALL build the task that creates the repo first. It SHALL then move the pending setup into the new repo as `.blueprint/`, with `drift.py`, and remove `targetRepo`.

- **Scenario: Extraction into a new repo**
  - **GIVEN** a pending setup for a repo that doesn't exist yet
  - **WHEN** task 1 creates it
  - **THEN** the new repo gets `.blueprint/` committed with that task, and work continues there

### Requirement: Tickets per tracker

Ticket handling SHALL follow the configured tracker (`github`, `linear`, `jira`, `notion` or `none`). It SHALL use one ticket per task, created only after the brief is approved and the user agrees to the list. The brief's task line SHALL link its ticket, and a closed ticket SHALL mean the task is done.

- **Scenario: Tracker none**
  - **WHEN** `tickets.tracker` is `none`
  - **THEN** tasks stay as checkboxes in the brief and no tickets are created

### Requirement: Fold artifacts

When folding a brief, apply SHALL add each entry of its **Artifacts** section to `blueprint.json` with `drift.py artifacts add`, after the capabilities it names exist.

- **Scenario: Artifact for a new capability**
  - **GIVEN** a brief adds the capability `billing/refunds` and an artifact covering it
  - **WHEN** the brief is applied
  - **THEN** `blueprint.json` holds the artifact, stamped as checked against the built code
