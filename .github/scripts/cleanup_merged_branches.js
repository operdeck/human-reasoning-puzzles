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
  const openBranches = new Set(
    openPullRequests
      .filter((pullRequest) => pullRequest.head.repo?.full_name === repositoryName)
      .map((pullRequest) => pullRequest.head.ref),
  );
  let deleted = 0;
  let skipped = 0;

  for (const [branch, pullRequest] of mergedByBranch) {
    if (openBranches.has(branch)) {
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
      await github.rest.git.deleteRef({ owner, repo, ref: `heads/${branch}` });
      core.info(`Deleted ${branch}.`);
      deleted += 1;
    }
  }

  core.info(
    `Branch cleanup finished: ${deleted} deleted, ${skipped} kept, ${mergedByBranch.size} merged-branch candidates.`,
  );
}

module.exports = { cleanupMergedBranches };
