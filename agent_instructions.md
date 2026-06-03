# Agent Instructions

## 1. Purpose

This document tells an AI coding agent how to continue work on this repository without constant user prompting.

It is task agnostic. The agent should read `goal.md` for domain-specific direction and `techstack.md` for architecture choices.

## 2. Required Reading Order

Before making changes, read:

1. `goal.md`
2. `techstack.md`
3. `implementation_plan.md`
4. `pipeline_spec.md`
5. `README.md`

Then inspect the repository structure and current git status.

## 3. Operating Mode

Work as a careful implementation agent.

Default behavior:

- Prefer small, verifiable changes.
- Preserve user changes.
- Follow existing project docs.
- Use the simplest tool that satisfies the current milestone.
- Keep domain-specific assumptions configurable.
- Produce artifacts that can be inspected.

Do not:

- Rewrite the project direction without user instruction.
- Add heavy infrastructure before the local pipeline works.
- Skip access, safety, or provenance requirements.
- Hide errors behind vague summaries.
- Delete prior outputs unless explicitly instructed.

## 4. How To Choose The Next Task

If the user does not specify a task, choose the earliest incomplete milestone from `implementation_plan.md`.

Priority order:

1. Project skeleton.
2. Data models.
3. Source registry.
4. Access and politeness.
5. Discovery.
6. Fetching.
7. Extraction.
8. Cleaning.
9. Redaction.
10. Entity and claim extraction.
11. Trust scoring.
12. Storage.
13. Reporting.
14. Automation.
15. Productization.

Never jump to UI, RAG, orchestration, or distributed crawling before the core records and local run path exist.

## 5. Planning Rules

For each work session:

1. State the immediate goal.
2. Identify the milestone being advanced.
3. Inspect relevant files.
4. Make the smallest coherent change.
5. Run relevant checks.
6. Summarize what changed, how it was verified, and what remains.

Ask the user only when a decision is risky, irreversible, or cannot be inferred from project docs.

## 6. Coding Rules

Use Python-first implementation unless the user requests otherwise.

Follow these defaults:

- Keep modules single-purpose.
- Prefer typed records or Pydantic models for pipeline contracts.
- Keep network access isolated in fetch/discovery modules.
- Keep cleaning, redaction, extraction, scoring, and storage separate.
- Make functions testable without live network calls where practical.
- Use fixtures for tests.
- Use clear errors.
- Log operational decisions.

Do not create large all-in-one scripts.

## 7. Safety And Access Rules

Network code must:

- Use a timeout.
- Use a clear `User-Agent`.
- Respect configured rate limits.
- Check access rules before fetching when configured.
- Avoid bypassing access controls.
- Log skipped URLs and reasons.

The agent must not:

- Probe live systems for vulnerabilities.
- Collect credentials.
- Scrape private, paywalled, or access-controlled data.
- Circumvent CAPTCHA, logins, anti-bot systems, or technical restrictions.
- Store unnecessary sensitive personal data.

## 8. Documentation Rules

Update docs when behavior changes.

Use this split:

- `goal.md`: domain, customer, research framing, source priorities.
- `techstack.md`: technology choices and scale path.
- `implementation_plan.md`: build order and acceptance criteria.
- `pipeline_spec.md`: input/output contracts and stage behavior.
- `agent_instructions.md`: AI continuation rules.
- `README.md`: how to install, run, and verify the current project.

Keep task-specific notes out of generic docs unless they describe a reusable pattern.

## 9. Validation Rules

Every implementation change should include at least one relevant validation:

- Run tests.
- Run a small command.
- Validate a fixture.
- Show generated output.
- Confirm a file was written.
- Confirm a schema loads.

If validation cannot be run, state why and describe the residual risk.

## 10. Output Rules

When finishing a task, report:

- Files changed.
- What the change enables.
- Verification performed.
- Next recommended step.

Keep summaries concise and specific.

## 11. Autonomy Rules For Automatic Runs

An automatic agent run may proceed when:

- The next milestone is clear.
- The required inputs exist or can be scaffolded safely.
- The change is reversible or easy to inspect.
- The work stays within documented architecture.

An automatic agent run must stop when:

- Required source access is unclear.
- A change would delete or overwrite user data.
- A new paid service, credential, or account is required.
- The task would add a new domain-specific assumption not present in `goal.md`.
- The pipeline would fetch from a source not listed in the source registry.
- The agent has failed the same step repeatedly.

## 12. Runbook For A Self-Prompting Agent

Use this loop:

1. Read the docs in the required order.
2. Inspect repository status.
3. Find the earliest incomplete milestone.
4. Define one small task for that milestone.
5. Implement it.
6. Validate it.
7. Update docs if needed.
8. Write a short run summary.
9. Stop if the next task requires user judgment.
10. Otherwise continue with the next small task.

The agent should not invent a new product direction during this loop.

## 13. Done Criteria For Agent Sessions

An agent session is done when one of these is true:

- The requested task is complete and verified.
- One milestone is complete and documented.
- The agent reaches a documented stop condition.
- The user interrupts or redirects the work.

Do not continue indefinitely just because another milestone exists.

## 14. Change Control

Before editing existing files:

- Check git status.
- Read the file.
- Preserve unrelated user changes.
- Keep edits scoped.

After editing:

- Review the diff when possible.
- Run the smallest useful validation.
- Mention untracked or modified files in the final summary.

## 15. Quality Bar

The project should remain:

- Auditable.
- Safe.
- Modular.
- Reproducible.
- Domain-configurable.
- Evidence-preserving.
- Ready to scale without premature infrastructure.
