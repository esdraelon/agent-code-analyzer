# GitHub Actions Push/Merge Order Implementation Plan

> **For Hermes:** Use `subagent-driven-development` to execute this plan task-by-task.

**Goal:** Document the exact GitHub flow in order — push first, let Actions run, then merge only after checks are green.

**Architecture:**
Treat the local branch, GitHub Actions run, and merge step as three separate gates. The branch must be clean before push, the push must land on the remote before CI is trusted, and merge must only happen after the required checks pass. Keep post-merge cleanup as a final, explicit step so the branch lifecycle is complete.

**Tech Stack:**
- Git
- GitHub Actions
- GitHub CLI (`gh`) or GitHub API fallback
- Markdown documentation in `docs/plans/`

---

## Milestones

### Milestone 0: Capture the ordered workflow

**Status:** planned

**Objective:** Write the push → Actions → merge flow as a linear, copy-pasteable procedure.

**Planned shape:**
- Start from a clean local branch.
- Push the branch to `origin`.
- Verify the remote ref exists.
- Observe GitHub Actions until required checks complete.
- Merge the PR only when the branch is green.
- Delete the remote branch and clean up local refs after merge.

**Likely files:**
- Create: `docs/plans/2026-06-15-github-actions-push-merge-order.md`

**Success criteria:**
- The document reads as an ordered checklist, not a vague overview.
- The push step is clearly separated from the merge step.
- The merge step explicitly depends on CI success.

---

### Milestone 1: Define the pre-push gate

**Status:** planned

**Objective:** Make the branch state safe before anything is sent to GitHub.

**Steps:**
1. Confirm the working tree is clean.
2. Confirm the current branch name.
3. Confirm the branch is based on the intended target branch.
4. Commit any finished work before pushing.

**Command sequence:**
```bash
git status -sb
git branch --show-current
git log --oneline --decorate -n 3
```

**Success criteria:**
- No uncommitted changes remain before the first push.
- The branch name is known and intentional.
- The commit history is ready for review.

---

### Milestone 2: Push the branch to GitHub

**Status:** planned

**Objective:** Publish the branch so GitHub Actions can run on the remote ref.

**Steps:**
1. Push the current branch.
2. Verify the remote branch exists.
3. Record the branch name and commit SHA that Actions will build.

**Command sequence:**
```bash
git push -u origin HEAD
git status -sb
git ls-remote --heads origin "$(git branch --show-current)"
git rev-parse HEAD
```

**Success criteria:**
- The branch exists on `origin`.
- The local tree remains clean after push.
- The pushed SHA is known.

---

### Milestone 3: Wait for GitHub Actions to finish

**Status:** planned

**Objective:** Treat CI as the gate between push and merge.

**Steps:**
1. Check workflow status for the pushed commit.
2. Watch for required checks to pass.
3. If a check fails, inspect the logs before making any new merge decision.
4. Fix and re-push only after identifying the failing step.

**Command sequence:**
```bash
gh pr checks --watch
```

**Fallback sequence:**
```bash
SHA=$(git rev-parse HEAD)
curl -s \
  -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/commits/$SHA/status
```

**Success criteria:**
- Required checks reach success.
- Failures are explained by logs, not guessed.
- No merge attempt happens while checks are pending or red.

---

### Milestone 4: Merge only after checks are green

**Status:** planned

**Objective:** Merge the PR in the correct order after CI proves the branch is safe.

**Steps:**
1. Confirm all required checks are green.
2. Merge with the chosen strategy.
3. Delete the remote branch.
4. Sync local `main`.
5. Remove the local feature branch if it is no longer needed.

**Command sequence:**
```bash
gh pr merge --squash --delete-branch

git checkout main
git pull origin main
git branch -d <branch-name>
```

**Success criteria:**
- The PR is merged only after CI passes.
- The remote branch is removed.
- Local `main` is up to date.
- The feature branch is cleaned up locally.

---

### Milestone 5: Keep the post-merge record tidy

**Status:** planned

**Objective:** Leave the repository in a clear state after merge.

**Steps:**
1. Verify `main` matches the merged commit.
2. Confirm no stale local tracking refs remain.
3. Update any plan or roadmap document status if this workflow is part of a tracked milestone.

**Success criteria:**
- The repository reflects the merged state cleanly.
- No lingering branch confusion remains.
- The plan document itself can be updated or closed if the workflow becomes standard.

---

## Ordered workflow summary

1. Finish work on a feature branch.
2. Confirm the branch is clean and committed.
3. Push the branch to `origin`.
4. Verify GitHub Actions starts on the pushed ref.
5. Wait for required checks to pass.
6. Fix and re-push if a check fails.
7. Merge the PR once green.
8. Delete the remote branch.
9. Sync local `main` and clean up the local branch.

## Notes

- Push and merge are separate gates; do not collapse them into one step.
- CI failure is a debugging step, not a merge step.
- If the host dependency setup is still pending, treat that as a prerequisite outside this document.
