## Purpose

Intent drift: judges the code against its capability specs, including spec edits people made outside the code, and fixes the code where it no longer does what the spec says. The spec is right; the code moves.

## Requirements

### Requirement: Scope

`/blueprint-drift` SHALL cover the named capabilities, or by default every capability whose spec or code moved. With `--deep` it SHALL check every requirement in scope even where nothing moved. It SHALL skip `no-spec` capabilities.

- **Scenario: Nothing moved**
  - **WHEN** nothing moved and `--deep` is not given
  - **THEN** it says so and stops

### Requirement: Every requirement judged

For each capability in scope, drift SHALL check every requirement and scenario of the current spec against the code, tests first, and give each one a verdict: holds, broken, not built or unclear, with evidence. Requirements changed in the spec SHALL be listed first.

- **Scenario: Broken requirement**
  - **WHEN** the code does something other than the spec says
  - **THEN** the row quotes both, and when the code changed according to git

### Requirement: Code changes, never requirements

Drift SHALL change code, never a requirement's meaning. An unclear requirement gets a proposed sharper wording that the user approves. If the user decides the code is right, the capability goes to `blueprint-sync`.

- **Scenario: User sides with the code**
  - **WHEN** the user says the code is right
  - **THEN** the row is left for `blueprint-sync` and not recorded

### Requirement: One decision per gap

Each broken or not-built row SHALL get one decision with the user. A small gap is fixed now with a test that pins the requirement. A larger one becomes a blueprint or tickets.

- **Scenario: Larger gap deferred**
  - **WHEN** a gap becomes a blueprint or tickets
  - **THEN** with the user's yes, `Not yet built → <link>` is added under the requirement

### Requirement: Recorded when satisfied

Drift SHALL do the spec bookkeeping only for capabilities whose code now satisfies the spec, or whose remaining gaps are all marked `Not yet built`.

- **Scenario: Partial fix**
  - **WHEN** one broken requirement is left unresolved and unmarked
  - **THEN** the capability is not stamped
