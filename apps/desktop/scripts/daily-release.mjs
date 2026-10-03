import { appendFile } from "node:fs/promises";
import { createReleaseGit } from "./daily-release-git.mjs";
import { createReleaseGitHub } from "./daily-release-github.mjs";
import { planDailyRelease } from "./daily-release-policy.mjs";
import { readDailyState, publishDailyRelease } from "./daily-release-publish.mjs";
import { readDailyAssets } from "./daily-release-assets.mjs";

const git = createReleaseGit();
const github = createReleaseGitHub({ token: process.env.GITHUB_TOKEN, repository: process.env.GITHUB_REPOSITORY });
const command = process.argv[2];
let summary;
if (command === "plan") {
  const { shouldRelease, plan } = planDailyRelease(await readDailyState(git, github, git.resolve("HEAD")));
  summary = `${shouldRelease ? "Build" : "Skip"} ${plan.tag}: ${plan.commitCount} commits since ${plan.baselineTag}; minimum 5. Source: ${plan.sha}.`;
  const outputs = { should_release: shouldRelease, sha: plan.sha, version: plan.version, plan: JSON.stringify(plan) };
  if (process.env.GITHUB_OUTPUT) {
    await appendFile(process.env.GITHUB_OUTPUT, Object.entries(outputs).map(([key, value]) => `${key}=${value}\n`).join(""), "utf8");
  }
} else if (command === "publish") {
  const plan = JSON.parse(process.env.SHIORI_DAILY_RELEASE_PLAN);
  const files = await readDailyAssets(process.argv[3], plan.version);
  const result = await publishDailyRelease({ plan, files, git, github });
  summary = `${result}: ${plan.tag} at ${plan.sha} (${plan.commitCount} commits since ${plan.baselineTag}).`;
} else {
  throw new Error("Usage: daily-release.mjs plan | publish <artifact-directory>");
}
console.log(summary);
if (process.env.GITHUB_STEP_SUMMARY) await appendFile(process.env.GITHUB_STEP_SUMMARY, `${summary}\n`, "utf8");
