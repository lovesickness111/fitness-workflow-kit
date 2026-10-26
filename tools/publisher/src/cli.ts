import path from "node:path";
import { fileURLToPath } from "node:url";
import { mkdir, open, readFile, unlink } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { loadWorkflow, runDir, saveWorkflow, sanitizeRunId, writeJsonAtomic } from "./state.js";
import { validateMp4 } from "./validation.js";
import { apiKeyFor, checkZernioAccounts, inspectApiPosts, listAccountsForProfile, loadProfiles, prepareApiPosts, publishPreparedApiPosts, requestJson, retryApiPosts } from "./zernio-api.js";
import type { CliConfig, WorkflowState } from "./types.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const config: CliConfig = {
  repoRoot: root, dataDir: path.join(root, "local"), workflowsDir: path.join(root, "local/runs"),
  zernioApiBaseUrl: "https://zernio.com/api/v1", zernioProfilesFile: path.join(root, "local/accounts.json"),
  zernioEnvFile: path.join(root, "local/secrets.env"),
};
const args = process.argv.slice(2);
const command = args.shift() ?? "help";
const options = new Map<string,string>();
while (args.length) {
  const key = args.shift()!;
  if (!key.startsWith("--")) throw new Error(`Unexpected argument ${key}`);
  const value = args[0]?.startsWith("--") || !args.length ? "true" : args.shift()!;
  if (options.has(key.slice(2))) throw new Error(`Duplicate option ${key}`);
  options.set(key.slice(2), value);
}
function need(key: string): string {
  const v = options.get(key);
  if (!v || v === "true") throw new Error(`Missing --${key}`);
  return v;
}
function output(v: unknown): void { console.log(JSON.stringify(v,null,2)); }
const help = `Video Workflow Publisher
  accounts                              List connected account IDs (GET only)
  check                                 Check configured account selectors and health
  import --run ID --video FILE.mp4       Record an existing MP4
  prepare --run ID --metadata FILE.json  Upload and validate, no post creation
  publish --run ID --confirm-publish     Publish the reviewed plan
  status --run ID                        Read local checkpoint
  inspect --run ID                       Read remote post status
  retry --run ID --confirm-publish       Resume eligible recorded attempts
  adopt --run ID --profile ALIAS --post-id ID  Bind a manually verified existing post
  All credentials come from local/secrets.env or process environment.
  A locked run requires manual reconciliation after a crash; do not bypass a running process.`;

async function main(): Promise<void> {
  if (["help", "--help", "-h"].includes(command)) { console.log(help); return; }
  if (command === "accounts") {
    const profiles = await loadProfiles(config);
    const result = [];
    for (const alias of Object.keys(profiles.profiles)) {
      const accounts = await listAccountsForProfile(config, apiKeyFor(profiles,alias));
      result.push({ profile: alias, accounts: accounts.map(a => ({ accountId: a._id, platform: a.platform, username: a.username, displayName: a.displayName })) });
    }
    output(result); return;
  }
  if (command === "check") { output(await checkZernioAccounts(config)); return; }
  if (!["import","prepare","publish","status","inspect","retry","adopt"].includes(command)) throw new Error("Unknown command. Run help.");
  const id = sanitizeRunId(need("run"));
  const dir = runDir(config,id);
  if (command === "status") { output(await loadWorkflow(config,id)); return; }
  await mkdir(config.workflowsDir,{recursive:true});
  // The parent-level lock also serializes the first import. Lock survives abrupt process death.
  const lockPath = path.join(config.workflowsDir,`${id}.lock`);
  const lock = await open(lockPath,"wx").catch(() => { throw new Error(`Run locked: ${lockPath}. Check for an active process and reconcile its outcome before removing a stale lock.`); });
  try {
    await lock.writeFile(JSON.stringify({pid:process.pid,at:new Date().toISOString()}));
    if (command === "import") {
      const file = path.resolve(need("video"));
      await validateMp4(file);
      await mkdir(dir,{recursive:false});
      const now=new Date().toISOString();
      const state: WorkflowState = {version:1,runId:id,stage:"rendered",videoFile:file,createdAt:now,updatedAt:now,history:[{at:now,stage:"rendered",note:"Imported existing MP4; no Studio generation."}]};
      await writeJsonAtomic(path.join(dir,"state.json"),state);
      output({runId:id,stage:state.stage,videoFile:file}); return;
    }
    const state = await loadWorkflow(config,id);
    if (state.version !== 1) throw new Error("Unsupported checkpoint version.");
    if (command === "prepare") output(await prepareApiPosts(config,state,{metadataFile:path.resolve(need("metadata"))}));
    if (command === "publish") output(await publishPreparedApiPosts(config,state,{confirmed:options.get("confirm-publish")==="true",timeoutMs:0}));
    if (command === "inspect") output(await inspectApiPosts(config,state));
    if (command === "retry") output(await retryApiPosts(config,state,{confirmed:options.get("confirm-publish")==="true",timeoutMs:0}));
    if (command === "adopt") {
      const alias=need("profile");
      const postId=need("post-id");
      const attempt=state.publish?.attempts?.find(a=>a.profile===alias && !a.postId && a.status==="uncertain");
      if (!attempt) throw new Error("No uncertain attempt without an ID for this profile.");
      const profiles=await loadProfiles(config);
      const response=await requestJson<{post?:Record<string,unknown>}>(config,apiKeyFor(profiles,alias),`posts/${encodeURIComponent(postId)}`);
      const post=response.post;
      const plan=JSON.parse(await readFile(state.publish!.planFile,"utf8"));
      const body=plan.profiles.find((p:{alias:string})=>p.alias===alias)?.body;
      const targets=Array.isArray(post?.platforms) ? post.platforms as Array<Record<string,unknown>> : [];
      const accountId=(v:unknown):unknown=>typeof v==="object" && v!==null ? (v as Record<string,unknown>)._id : v;
      if (!post || !body || post.content!==body.content || JSON.stringify(targets.map(t=>`${t.platform}:${accountId(t.accountId)}`).sort())!==JSON.stringify(body.platforms.map((t:{platform:string;accountId:string})=>`${t.platform}:${t.accountId}`).sort()))
        throw new Error("Post content or account IDs do not match this prepared attempt.");
      attempt.postId=postId;
      await saveWorkflow(config,state);
      output(await inspectApiPosts(config,state));
    }
  } finally { await lock.close(); await unlink(lockPath); }
}
main().catch(error=>{
  // Replace every loaded credential value in errors, including provider error strings.
  let message=error instanceof Error ? error.message : String(error);
  for (const [name,value] of Object.entries(process.env)) if (/(?:API_KEY|TOKEN|SECRET)/.test(name) && value) message=message.split(value).join("[REDACTED]");
  console.error(message); process.exitCode=1;
});
