const { execFileSync } = require("node:child_process");

function isDryRun(context) {
  if (context.eventName !== "workflow_dispatch") return false;
  const input = context.payload.inputs?.["dry-run"];
  return input !== false && input !== "false";
}

function deleteBranch(branch, sha, remote = "origin") {
  const ref = `refs/heads/${branch}`;
  execFileSync("git", ["push", `--force-with-lease=${ref}:${sha}`, remote, `:${ref}`], {
    stdio: "inherit",
  });
}

function usedByOpenPullRequest(pullRequest, branch, repositoryName) {
  return (
    (pullRequest.head.repo?.full_name === repositoryName && pullRequest.head.ref === branch) ||
    (pullRequest.base.repo?.full_name === repositoryName && pullRequest.base.ref === branch)
  );
}

async function cleanupMergedBranches({ github, context, core, dryRun }) {
  const { owner, repo } = context.repo;
  const repositoryName = `${owner}/${repo}`;
  const { data: repository } = await github.rest.repos.get({ owner, repo });
  const closedPullRequests = await github.paginate(github.rest.pulls.list, {
    owner,
    repo,
    state: "closed",
    per_page: 100,
  });
  const mergedByBranch = new Map();
  const retentionPeriodMs = 30 * 24 * 60 * 60 * 1000;
  const now = Date.now();

  for (const pullRequest of closedPullRequests) {
    if (
      !pullRequest.merged_at ||
      pullRequest.head.repo?.full_name !== repositoryName ||
      pullRequest.head.ref === repository.default_branch
    ) {
      continue;
    }

    const previous = mergedByBranch.get(pullRequest.head.ref);
    if (!previous || pullRequest.merged_at > previous.merged_at) {
      mergedByBranch.set(pullRequest.head.ref, pullRequest);
    }
  }

  const openPullRequests = await github.paginate(github.rest.pulls.list, {
    owner,
    repo,
    state: "open",
    per_page: 100,
  });
  const eligibleBranches = new Map();
  let deleted = 0;
  let skipped = 0;

  for (const [branch, pullRequest] of mergedByBranch) {
    const mergedAt = Date.parse(pullRequest.merged_at);
    if (!Number.isFinite(mergedAt) || now - mergedAt < retentionPeriodMs) {
      core.info(`Keeping ${branch}: its latest merged pull request is less than 30 days old.`);
      skipped += 1;
      continue;
    }
    eligibleBranches.set(branch, pullRequest);
  }

  for (const [branch, pullRequest] of eligibleBranches) {
    if (openPullRequests.some((pr) => usedByOpenPullRequest(pr, branch, repositoryName))) {
      core.info(`Keeping ${branch}: an open pull request uses it.`);
      skipped += 1;
      continue;
    }

    let branchInfo;
    try {
      ({ data: branchInfo } = await github.rest.repos.getBranch({ owner, repo, branch }));
    } catch (error) {
      if (error.status === 404) {
        core.info(`Keeping ${branch}: the branch no longer exists.`);
        skipped += 1;
        continue;
      }
      throw error;
    }

    if (branchInfo.protected) {
      core.info(`Keeping ${branch}: it is protected.`);
      skipped += 1;
      continue;
    }
    if (branchInfo.commit.sha !== pullRequest.head.sha) {
      core.info(`Keeping ${branch}: it has changed since the pull request was merged.`);
      skipped += 1;
      continue;
    }

    if (dryRun) {
      core.info(`Dry run: would delete ${branch}.`);
    } else {
      const currentOpenPullRequests = await github.paginate(github.rest.pulls.list, {
        owner,
        repo,
        state: "open",
        per_page: 100,
      });
      if (currentOpenPullRequests.some((pr) => usedByOpenPullRequest(pr, branch, repositoryName))) {
        core.info(`Keeping ${branch}: an open pull request uses it.`);
        skipped += 1;
        continue;
      }
      deleteBranch(branch, branchInfo.commit.sha);
      core.info(`Deleted ${branch}.`);
      deleted += 1;
    }
  }

  core.info(
    `Branch cleanup finished: ${deleted} deleted, ${skipped} kept, ${mergedByBranch.size} merged-branch candidates.`,
  );
}

module.exports = { cleanupMergedBranches, deleteBranch, isDryRun };
