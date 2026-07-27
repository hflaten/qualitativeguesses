# Agent Execution Policy

## Purpose

Use small, cheap agents for bounded execution and reserve senior agents for
decisions that require context, judgment, or coordination.

## Decompose Linear tickets

- A ticket must have one observable outcome, clear acceptance criteria, and a
  named owner.
- Split work into small tasks that can be completed independently in one short
  session. Good tasks include one component, one endpoint, one migration, one
  test group, or one documentation change.
- Put required context, constraints, affected paths, test commands, and known
  risks in the ticket before assigning execution.
- Separate discovery, implementation, and verification when they need
  different skills or write scopes.
- Do not split work that requires shared mutable state, a single design
  decision, or tightly coupled edits. Keep that work with one senior agent.
- Make dependencies explicit in Linear. A dependent task must wait for its
  prerequisite rather than guessing at an unfinished interface.

## Senior agent ownership

Senior agents own ticket decomposition, architecture and API decisions,
security and data-risk review, cross-cutting refactors, conflict resolution,
integration of parallel work, and final acceptance. They also decide when a
small agent should stop and escalate rather than expand scope.

Small agents may implement and test a clearly specified slice. They must not
change public contracts, take ownership of adjacent tickets, modify shared
configuration, or broaden scope without senior approval.

## Branch and write-scope rules

- One Linear issue per branch. Name the branch with the issue identifier and a
  short slug.
- Never use another issue's branch for convenience, and never combine
  unrelated issues in one branch or pull request.
- Every parallel agent receives a disjoint write scope, stated in the ticket
  before work begins. Paths, generated files, and ownership of shared
  interfaces must be explicit.
- Agents must not edit files outside their assigned scope. If the change needs
  overlap, pause and ask the senior agent to re-slice or serialize the work.
- Keep commits and pull requests focused on the issue. Do not rewrite or revert
  unrelated work from another agent.

## Reporting and completion

When finished, the agent reports in the Linear issue:

- what changed and why;
- files or modules touched;
- tests, checks, and commands run, including failures;
- remaining risks, follow-up work, or deviations from the ticket;
- the branch and GitHub pull request link, if one exists.

The senior agent updates Linear with the final status, links the GitHub pull
request and relevant commits, records review decisions, and confirms acceptance
criteria. GitHub pull requests must link the Linear issue, describe behavior
changes, list verification, and identify any known limitations. A ticket is
complete only after review, required checks, and the Linear status update are
done.
