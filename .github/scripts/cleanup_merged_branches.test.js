const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");
const { cleanupMergedBranches, deleteBranch, isDryRun } = require("./cleanup_merged_branches.js");

test("manual runs default to dry-run and only explicit false enables deletion", () => {
  const context = (input) => ({ eventName: "workflow_dispatch", payload: { inputs: input } });
  assert.equal(isDryRun(context(undefined)), true);
  assert.equal(isDryRun(context({ "dry-run": "true" })), true);
  assert.equal(isDryRun(context({ "dry-run": true })), true);
  assert.equal(isDryRun(context({ "dry-run": "false" })), false);
  assert.equal(isDryRun(context({ "dry-run": false })), false);
  assert.equal(isDryRun({ eventName: "schedule", payload: {} }), false);
});

function pullRequest(branch, options = {}) {
  return {
    merged_at: "2020-01-01T00:00:00Z",
    head: { ref: branch, sha: "original", repo: { full_name: "owner/repo" } },
    base: { ref: "main", repo: { full_name: "owner/repo" } },
    ...options,
  };
}

function mockGithub(closed, openPages, branchInfo) {
  let openCalls = 0;
  return {
    rest: {
      repos: {
        get: async () => ({ data: { default_branch: "main" } }),
        getBranch: async () => ({ data: branchInfo }),
      },
      pulls: { list: () => {} },
    },
    paginate: async (_method, options) => {
      if (options.state === "closed") return closed;
      return openPages[Math.min(openCalls++, openPages.length - 1)];
    },
  };
}

test("keeps branches used as the head or base of an open PR", async () => {
  for (const role of ["head", "base"]) {
    const open = pullRequest("other");
    open[role] = { ref: "feature", repo: { full_name: "owner/repo" } };
    const messages = [];
    const github = mockGithub([pullRequest("feature")], [[open]], null);
    await cleanupMergedBranches({
      github,
      context: { repo: { owner: "owner", repo: "repo" } },
      core: { info: (message) => messages.push(message) },
      dryRun: false,
    });
    assert(messages.some((message) => message.includes("an open pull request uses it")));
  }
});

test("rechecks open PRs before deleting", async () => {
  const messages = [];
  const open = pullRequest("other", {
    base: { ref: "feature", repo: { full_name: "owner/repo" } },
  });
  const github = mockGithub([pullRequest("feature")], [[], [open]], {
    protected: false,
    commit: { sha: "original" },
  });
  await cleanupMergedBranches({
    github,
    context: { repo: { owner: "owner", repo: "repo" } },
    core: { info: (message) => messages.push(message) },
    dryRun: false,
  });
  assert(messages.some((message) => message.includes("an open pull request uses it")));
});

test("dry-run previews only branches whose latest merge is at least 30 days old", async () => {
  const now = Date.parse("2026-11-23T09:00:00Z");
  const day = 24 * 60 * 60 * 1000;
  const originalNow = Date.now;
  const messages = [];
  Date.now = () => now;
  try {
    const closed = [
      pullRequest("old", { merged_at: new Date(now - 30 * day).toISOString() }),
      pullRequest("reused", { merged_at: new Date(now - 60 * day).toISOString() }),
      pullRequest("reused", { merged_at: new Date(now - 29 * day).toISOString() }),
    ];
    const github = mockGithub(closed, [[]], {
      protected: false,
      commit: { sha: "original" },
    });
    await cleanupMergedBranches({
      github,
      context: { repo: { owner: "owner", repo: "repo" } },
      core: { info: (message) => messages.push(message) },
      dryRun: true,
    });
    assert(messages.includes("Dry run: would delete old."));
    assert(messages.some((message) => message.includes("Keeping reused:")));
  } finally {
    Date.now = originalNow;
  }
});

test("a lease rejects deletion when the remote branch changed after inspection", () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "branch-cleaner-test-"));
  const remote = path.join(directory, "remote.git");
  const work = path.join(directory, "work");
  const git = (...args) => execFileSync("git", args, { cwd: work, stdio: "pipe" }).toString().trim();
  try {
    fs.mkdirSync(work);
    execFileSync("git", ["init", "--bare", "--quiet", remote]);
    git("init", "--quiet");
    git("config", "user.name", "Test");
    git("config", "user.email", "test@example.invalid");
    git("commit", "--quiet", "--allow-empty", "-m", "first");
    const first = git("rev-parse", "HEAD");
    git("push", "--quiet", remote, "HEAD:refs/heads/feature");
    git("commit", "--quiet", "--allow-empty", "-m", "second");
    const second = git("rev-parse", "HEAD");
    git("push", "--quiet", remote, "HEAD:refs/heads/feature");

    assert.throws(() => deleteBranch("feature", first, remote));
    assert.equal(git("ls-remote", remote, "refs/heads/feature").split(/\s+/)[0], second);
    deleteBranch("feature", second, remote);
    assert.equal(git("ls-remote", remote, "refs/heads/feature"), "");
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
