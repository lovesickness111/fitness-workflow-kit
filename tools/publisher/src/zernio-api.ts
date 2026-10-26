import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { access, readFile, stat } from "node:fs/promises";
import path from "node:path";

import { readJson, runDir, saveWorkflow, transitionWorkflow, writeJsonAtomic } from "./state.js";
import type {
  CliConfig,
  PublishMetadata,
  PublishResult,
  SocialPlatform,
  WorkflowState,
  ZernioAccountSelector,
  ZernioPlatformResult,
  ZernioProfilesFile,
  ZernioPublishAttempt,
} from "./types.js";
import {
  validateMp4,
  validatePublishMetadata,
} from "./validation.js";

type JsonObject = Record<string, unknown>;

interface ZernioAccount {
  _id: string;
  platform: SocialPlatform;
  username?: string;
  displayName?: string;
  isActive?: boolean;
}

interface ZernioAccountHealth {
  accountId: string;
  status?: string;
  canPost?: boolean;
  tokenValid?: boolean;
  needsReconnect?: boolean;
  issues?: string[];
}

interface ZernioTarget {
  platform: SocialPlatform;
  accountId: string;
  platformSpecificData?: JsonObject;
  customContent?: string;
}

interface ZernioPostBody extends JsonObject {
  title?: string;
  content: string;
  mediaItems: Array<{ type: "video"; url: string }>;
  platforms: ZernioTarget[];
  tags?: string[];
  tiktokSettings?: JsonObject;
  // Đăng ngay: publishNow=true. Hẹn giờ: isDraft=false + scheduledFor (ISO).
  // Lưu ý field Zernio là "scheduledFor" — gửi "scheduledAt" bị lặng lẽ bỏ qua, post kẹt ở draft.
  publishNow?: boolean;
  isDraft?: boolean;
  scheduledFor?: string;
}

/** metadata.scheduledAt → ISO chuẩn hoá; throw nếu sai định dạng hoặc không ở tương lai. */
function normalizedScheduledAt(metadata: PublishMetadata): string | undefined {
  const raw = metadata.scheduledAt?.trim();
  if (!raw) return undefined;
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    throw new Error(`scheduledAt không hợp lệ: "${raw}" (cần ISO 8601, vd 2026-09-07T08:00:00+07:00).`);
  }
  if (date.getTime() < Date.now() + 2 * 60_000) {
    throw new Error(`scheduledAt phải ở tương lai (tối thiểu 2 phút nữa): ${raw}`);
  }
  return date.toISOString();
}

interface PreparedProfile {
  alias: string;
  platforms: SocialPlatform[];
  body: ZernioPostBody;
}

interface ZernioPublishPlan {
  version: 1;
  runId: string;
  kind: "selected-platforms";
  createdAt: string;
  fingerprint: string;
  profiles: PreparedProfile[];
}

export interface ZernioAccountSummary {
  profile: string;
  platforms: Array<{
    platform: SocialPlatform;
    username?: string;
    displayName?: string;
    active: boolean;
    canPost: boolean;
  }>;
}

export class ZernioApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
    readonly retryAfter?: string,
  ) {
    super(message);
    this.name = "ZernioApiError";
  }
}

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringField(value: JsonObject, key: string): string | undefined {
  const field = value[key];
  return typeof field === "string" && field ? field : undefined;
}

function normalizeUsername(value?: string): string {
  return (value ?? "").trim().replace(/^@/, "").toLocaleLowerCase();
}

function parseEnvValue(raw: string): string {
  const trimmed = raw.trim();
  if (
    trimmed.length >= 2 &&
    ((trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'")))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export async function loadZernioEnvironment(config: CliConfig): Promise<void> {
  let contents: string;
  try {
    contents = await readFile(config.zernioEnvFile, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw error;
  }
  for (const line of contents.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const separator = trimmed.indexOf("=");
    if (separator < 1) throw new Error(`Invalid line in ${config.zernioEnvFile}.`);
    const name = trimmed.slice(0, separator).trim();
    if (!/^[A-Z_][A-Z0-9_]*$/.test(name)) {
      throw new Error(`Invalid environment variable name in ${config.zernioEnvFile}.`);
    }
    if (process.env[name] === undefined) {
      process.env[name] = parseEnvValue(trimmed.slice(separator + 1));
    }
  }
}

export async function loadProfiles(config: CliConfig): Promise<ZernioProfilesFile> {
  await loadZernioEnvironment(config);
  const profiles = await readJson<ZernioProfilesFile>(config.zernioProfilesFile);
  if (profiles.version !== 1 || !isObject(profiles.profiles)) {
    throw new Error(`Invalid Zernio profiles file: ${config.zernioProfilesFile}`);
  }
  for (const [alias, definition] of Object.entries(profiles.profiles)) {
    if (!alias.trim() || !definition.apiKeyEnv || !isObject(definition.platforms)) {
      throw new Error(`Invalid Zernio profile '${alias}'.`);
    }
    if (!/^[A-Z_][A-Z0-9_]*$/.test(definition.apiKeyEnv) || Object.keys(definition.platforms).some(p => !["tiktok", "youtube", "facebook", "linkedin"].includes(p))) {
      throw new Error(`Invalid environment name or unsupported platform in '${alias}'.`);
    }
    const apiKey = process.env[definition.apiKeyEnv];
    if (!apiKey) {
      throw new Error(
        `Missing ${definition.apiKeyEnv}. Set it in the process environment or ${config.zernioEnvFile}.`,
      );
    }
  }
  return profiles;
}

export function apiKeyFor(profiles: ZernioProfilesFile, alias: string): string {
  const definition = profiles.profiles[alias];
  if (!definition) throw new Error(`Unknown Zernio profile '${alias}'.`);
  const apiKey = process.env[definition.apiKeyEnv];
  if (!apiKey) throw new Error(`Missing ${definition.apiKeyEnv}.`);
  return apiKey;
}

function apiUrl(config: CliConfig, resource: string): string {
  return `${config.zernioApiBaseUrl.replace(/\/$/, "")}/${resource.replace(/^\//, "")}`;
}

export async function requestJson<T>(
  config: CliConfig,
  apiKey: string,
  resource: string,
  options: { method?: string; body?: unknown; requestId?: string } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(config, resource), {
      method: options.method ?? "GET",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: "application/json",
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(options.requestId ? { "x-request-id": options.requestId } : {}),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(60_000),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new ZernioApiError(`Zernio request did not return a response: ${message}`, 0);
  }

  const raw = await response.text();
  let data: unknown = {};
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch {
      data = { error: raw.slice(0, 500) };
    }
  }
  if (!response.ok) {
    const object = isObject(data) ? data : {};
    const message = stringField(object, "error") ?? `Zernio returned HTTP ${response.status}.`;
    throw new ZernioApiError(
      message,
      response.status,
      stringField(object, "code"),
      response.headers.get("retry-after") ?? undefined,
    );
  }
  return data as T;
}

export async function listAccountsForProfile(
  config: CliConfig,
  apiKey: string,
): Promise<ZernioAccount[]> {
  const response = await requestJson<{ accounts?: ZernioAccount[] }>(
    config,
    apiKey,
    "accounts?status=connected",
  );
  return (response.accounts ?? []).filter((account) => account.isActive !== false);
}

export async function accountHealthForProfile(
  config: CliConfig,
  apiKey: string,
): Promise<Map<string, ZernioAccountHealth>> {
  const response = await requestJson<{ accounts?: ZernioAccountHealth[] }>(
    config,
    apiKey,
    "accounts/health",
  );
  return new Map((response.accounts ?? []).map((account) => [account.accountId, account]));
}

export function assertCanPost(account: ZernioAccount, health: Map<string, ZernioAccountHealth>): void {
  const status = health.get(account._id);
  if (!status) throw new Error(`Zernio health data is missing for ${account.platform}.`);
  if (status.canPost !== true || status.needsReconnect || status.tokenValid === false) {
    throw new Error(
      `The selected ${account.platform} account cannot post: ${(status.issues ?? []).join("; ") || status.status || "unhealthy connection"}.`,
    );
  }
}

export function resolveAccount(
  accounts: ZernioAccount[],
  platform: SocialPlatform,
  selector: ZernioAccountSelector,
): ZernioAccount {
  let candidates = accounts.filter((account) => account.platform === platform);
  if (selector.accountId) {
    candidates = candidates.filter((account) => account._id === selector.accountId);
  }
  if (selector.username) {
    const expected = normalizeUsername(selector.username);
    candidates = candidates.filter((account) =>
      [account.username, account.displayName].some(
        (value) => normalizeUsername(value) === expected,
      ),
    );
  }
  if (candidates.length !== 1) {
    const hint = selector.username ?? selector.accountId ?? "a unique connected account";
    throw new Error(
      `Expected ${hint} for ${platform}, but found ${candidates.length}. Update the account selector in the Zernio profiles file.`,
    );
  }
  return candidates[0];
}

export async function checkZernioAccounts(config: CliConfig): Promise<ZernioAccountSummary[]> {
  const profiles = await loadProfiles(config);
  const summaries: ZernioAccountSummary[] = [];
  for (const [alias, definition] of Object.entries(profiles.profiles)) {
    const apiKey = apiKeyFor(profiles, alias);
    const accounts = await listAccountsForProfile(config, apiKey);
    const health = await accountHealthForProfile(config, apiKey);
    const selected = Object.entries(definition.platforms).map(([platform, selector]) => {
      const account = resolveAccount(accounts, platform as SocialPlatform, selector ?? {});
      assertCanPost(account, health);
      return {
        platform: platform as SocialPlatform,
        username: account.username,
        displayName: account.displayName,
        active: account.isActive !== false,
        canPost: true,
      };
    });
    summaries.push({ profile: alias, platforms: selected });
  }
  return summaries;
}

async function uploadVideo(
  config: CliConfig,
  apiKey: string,
  videoFile: string,
  uploadName: string,
): Promise<string> {
  const info = await stat(videoFile);
  const presign = await requestJson<JsonObject>(config, apiKey, "media/presign", {
    method: "POST",
    body: { filename: uploadName, contentType: "video/mp4", size: info.size },
  });
  const uploadUrl = stringField(presign, "uploadUrl");
  const publicUrl = stringField(presign, "publicUrl");
  if (!uploadUrl || !publicUrl) throw new Error("Zernio media presign response is incomplete.");

  const uploadResponse = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": "video/mp4", "Content-Length": String(info.size) },
    body: createReadStream(videoFile) as unknown as BodyInit,
    duplex: "half",
    signal: AbortSignal.timeout(30 * 60_000),
  } as RequestInit & { duplex: "half" });
  if (!uploadResponse.ok) {
    throw new Error(`Zernio media upload failed with HTTP ${uploadResponse.status}.`);
  }
  return publicUrl;
}

function extractPrivacyOptions(value: unknown): string[] {
  if (!isObject(value)) return [];
  for (const key of [
    "privacyLevelOptions",
    "privacy_level_options",
    "privacyLevels",
    "privacy_levels",
  ]) {
    const options = value[key];
    if (Array.isArray(options)) {
      return options
        .map((option) => typeof option === "string" ? option : isObject(option)
          ? stringField(option, "value") ?? stringField(option, "privacy_level")
          : undefined)
        .filter((option): option is string => Boolean(option));
    }
  }
  for (const nested of Object.values(value)) {
    const options = extractPrivacyOptions(nested);
    if (options.length) return options;
  }
  return [];
}

export async function resolveTikTokPrivacy(
  config: CliConfig,
  apiKey: string,
  accountId: string,
  requested?: string,
  mediaType: "video" | "photo" = "video",
): Promise<string> {
  const info = await requestJson<unknown>(
    config,
    apiKey,
    `accounts/${encodeURIComponent(accountId)}/tiktok/creator-info?mediaType=${mediaType}`,
  );
  const options = extractPrivacyOptions(info);
  if (!options.length) {
    throw new Error("TikTok creator info did not return any allowed privacy levels.");
  }
  if (requested) {
    if (!options.includes(requested)) {
      throw new Error(`TikTok privacy '${requested}' is not currently allowed for the selected creator.`);
    }
    return requested;
  }
  if (options.includes("PUBLIC_TO_EVERYONE")) return "PUBLIC_TO_EVERYONE";
  throw new Error(
    "TikTok public visibility is unavailable. Set tiktokPrivacyLevel explicitly after reviewing creator info.",
  );
}

function buildTarget(
  platform: SocialPlatform,
  account: ZernioAccount,
  metadata: PublishMetadata,
): ZernioTarget {
  if (platform === "youtube") {
    return {
      platform,
      accountId: account._id,
      customContent: metadata.description ?? metadata.content,
      platformSpecificData: {
        title: metadata.title,
        visibility: metadata.youtubePrivacy ?? "public",
        madeForKids: metadata.youtubeMadeForKids ?? false,
        containsSyntheticMedia: metadata.youtubeContainsSyntheticMedia,
      },
    };
  }
  if (platform === "tiktok") {
    return {
      platform,
      accountId: account._id,
      customContent: metadata.tiktokCaption ?? metadata.content,
    };
  }
  if (platform === "facebook" && metadata.facebookContentType === "reel") {
    return {
      platform,
      accountId: account._id,
      platformSpecificData: {
        contentType: "reel",
        ...(metadata.facebookTitle ? { title: metadata.facebookTitle } : {}),
      },
    };
  }
  return { platform, accountId: account._id };
}

async function fileFingerprint(
  metadata: PublishMetadata,
  videoFile: string,
  kind: ZernioPublishPlan["kind"],
): Promise<string> {
  const hash = createHash("sha256").update(kind).update("\0").update(JSON.stringify(metadata)).update("\0");
  for await (const chunk of createReadStream(videoFile)) hash.update(chunk);
  return hash.digest("hex");
}

function requireVideoFile(state: WorkflowState, requested?: string): string {
  const file = requested ? path.resolve(requested) : state.videoFile;
  if (!file) throw new Error("No rendered video is recorded. Import a video first.");
  return file;
}

async function loadMetadata(filePath: string): Promise<PublishMetadata> {
  const metadata = JSON.parse(await readFile(path.resolve(filePath), "utf8")) as PublishMetadata;
  validatePublishMetadata(metadata);
  return metadata;
}

function assertProfileCoverage(profiles: ZernioProfilesFile, metadata: PublishMetadata): void {
  for (const platform of Object.keys(metadata.platforms) as SocialPlatform[]) {
    if (!metadata.platforms[platform]) continue;
    const owners = Object.values(profiles.profiles).filter(p => platform in p.platforms);
    if (owners.length !== 1) throw new Error(`Selected platform '${platform}' must belong to exactly one API profile.`);
  }
}

function assertPlanCoverage(plan: ZernioPublishPlan, runId: string): void {
  if (plan.version !== 1 || plan.runId !== runId || plan.kind !== "selected-platforms" || !plan.profiles?.length)
    throw new Error("Invalid prepared plan or run ID.");
  const platforms = plan.profiles.flatMap(p => p.platforms);
  if (!platforms.length || new Set(platforms).size !== platforms.length) throw new Error("Duplicate or empty targets.");
  const age = Date.now() - Date.parse(plan.createdAt);
  if (!Number.isFinite(age) || age < 0 || age > 24 * 60 * 60_000) throw new Error("Prepared media is over 24 hours old; prepare again before the first publish.");
}

function validationErrors(value: unknown): string[] {
  if (!isObject(value)) return [];
  const errors = value.errors;
  if (!Array.isArray(errors)) return [];
  return errors.map((error) => isObject(error)
    ? stringField(error, "error") ?? stringField(error, "message") ?? JSON.stringify(error)
    : String(error));
}

async function validatePlanBody(
  config: CliConfig,
  apiKey: string,
  body: ZernioPostBody,
): Promise<void> {
  const result = await requestJson<JsonObject>(config, apiKey, "tools/validate/post", {
    method: "POST",
    body,
  });
  const errors = validationErrors(result);
  if (result.valid === false || errors.length) {
    throw new Error(`Zernio validation failed: ${errors.join("; ") || "unknown validation error"}`);
  }
}

export async function prepareApiPosts(
  config: CliConfig, state: WorkflowState,
  options: { metadataFile: string; videoFile?: string },
): Promise<unknown> {
  if (!["rendered", "publish_review"].includes(state.stage) || state.publish?.attempts?.length)
    throw new Error("Cannot replace a plan after publishing has begun. Inspect the existing run.");
  const kind = "selected-platforms" as const;
  const metadata = await loadMetadata(options.metadataFile);
  const videoFile = requireVideoFile(state, options.videoFile);
  await validateMp4(videoFile);
  const profiles = await loadProfiles(config);
  assertProfileCoverage(profiles, metadata);
  const fingerprint = await fileFingerprint(metadata, videoFile, kind);
  const preparedProfiles: PreparedProfile[] = [];
  const review: JsonObject[] = [];
  for (const [alias, definition] of Object.entries(profiles.profiles)) {
    const platforms = (Object.keys(definition.platforms) as SocialPlatform[]).filter(p => metadata.platforms[p]);
    if (!platforms.length) continue;
    const apiKey = apiKeyFor(profiles, alias);
    const accounts = await listAccountsForProfile(config, apiKey);
    const health = await accountHealthForProfile(config, apiKey);
    const selected = platforms.map(p => {
      const account = resolveAccount(accounts, p, definition.platforms[p] ?? {});
      assertCanPost(account, health);
      return account;
    });
    const body: ZernioPostBody = {
      title: metadata.title, content: metadata.content,
      mediaItems: [{ type: "video", url: await uploadVideo(config, apiKey, videoFile, `${state.runId}-${alias}-${Date.now()}.mp4`) }],
      platforms: selected.map(a => buildTarget(a.platform, a, metadata)),
      ...(metadata.tags?.length ? { tags: metadata.tags } : {}),
      ...(normalizedScheduledAt(metadata) ? { isDraft: false, scheduledFor: normalizedScheduledAt(metadata), timezone: "UTC" } : { publishNow: true }),
    };
    const tt = selected.find(a => a.platform === "tiktok");
    if (tt) body.tiktokSettings = {
      draft: false,
      privacyLevel: await resolveTikTokPrivacy(config, apiKey, tt._id, metadata.tiktokPrivacyLevel),
      allowComment: true, allowDuet: false, allowStitch: false,
      contentPreviewConfirmed: true, expressConsentGiven: true,
      videoMadeWithAi: metadata.tiktokVideoMadeWithAi,
    };
    await validatePlanBody(config, apiKey, body);
    preparedProfiles.push({ alias, platforms, body });
    review.push({ profile: alias, accounts: selected.map(a => ({ platform: a.platform, accountId: a._id, username: a.username, displayName: a.displayName })), metadata, mode: body.scheduledFor ? "scheduled" : "immediate", scheduledFor: body.scheduledFor });
  }
  const plan: ZernioPublishPlan = { version: 1, runId: state.runId, kind, createdAt: new Date().toISOString(), fingerprint, profiles: preparedProfiles };
  const planFile = path.join(runDir(config, state.runId), "plan.json");
  await writeJsonAtomic(planFile, plan);
  await writeJsonAtomic(path.join(runDir(config, state.runId), "review.json"), { runId: state.runId, videoFile, profiles: review });
  state.publish = { mode: "api", metadataFile: path.resolve(options.metadataFile), videoFile, preparedFingerprint: fingerprint, planFile, preparedAt: plan.createdAt, planHash: createHash("sha256").update(await readFile(planFile)).digest("hex") };
  await transitionWorkflow(config, state, "publish_review", "Media uploaded and plan validated; no post created.");
  return { runId: state.runId, reviewFile: path.join(runDir(config, state.runId), "review.json"), targets: review };
}

function normalizePostStatus(value: unknown): ZernioPublishAttempt["status"] {
  const v = typeof value === "string" ? value.toLowerCase() : "";
  if (v === "published" || v === "partial" || v === "failed" || v === "publishing" || v === "scheduled") {
    return v as ZernioPublishAttempt["status"];
  }
  return "publishing";
}

function platformResults(post: JsonObject): ZernioPlatformResult[] {
  const platforms = Array.isArray(post.platforms) ? post.platforms : [];
  return platforms.filter(isObject).map((item) => ({
    platform: String(item.platform) as SocialPlatform,
    status: stringField(item, "status") ?? "unknown",
    platformPostUrl: stringField(item, "platformPostUrl"),
    errorMessage: stringField(item, "errorMessage") ?? stringField(item, "error"),
  }));
}

function unwrapPost(response: unknown): JsonObject {
  if (!isObject(response)) throw new Error("Zernio post response is invalid.");
  const candidate = response.post ?? response.existingPost ?? response;
  if (!isObject(candidate)) throw new Error("Zernio post response has no post object.");
  return candidate;
}

function updateAttemptFromPost(attempt: ZernioPublishAttempt, post: JsonObject): void {
  attempt.postId = stringField(post, "_id") ?? stringField(post, "id") ?? attempt.postId;
  attempt.status = normalizePostStatus(post.status);
  attempt.platformResults = platformResults(post);
  const errors = attempt.platformResults
    .map((result) => result.errorMessage)
    .filter((message): message is string => Boolean(message));
  attempt.errorMessage = errors.length ? errors.join("; ") : undefined;
}

function aggregateResult(attempts: ZernioPublishAttempt[]): PublishResult {
  const active = attempts.filter((attempt) => attempt.status !== "pending");
  const links: Record<string, string> = {};
  const errors: string[] = [];
  for (const attempt of active) {
    for (const platform of attempt.platformResults) {
      if (platform.platformPostUrl) links[platform.platform] = platform.platformPostUrl;
      if (platform.errorMessage) errors.push(`${attempt.profile}/${platform.platform}: ${platform.errorMessage}`);
    }
    if (attempt.errorMessage && !attempt.platformResults.some((item) => item.errorMessage)) {
      errors.push(`${attempt.profile}: ${attempt.errorMessage}`);
    }
  }
  // "scheduled" là trạng thái thành công của post hẹn giờ — tính như published cho workflow.
  const succeeded = (attempt: ZernioPublishAttempt) =>
    attempt.status === "published" || attempt.status === "scheduled";
  let status: PublishResult["status"];
  if (active.length === attempts.length && active.length > 0 && active.every(succeeded)) {
    status = "published";
  } else if (active.some((attempt) => succeeded(attempt) || attempt.status === "partial")) {
    status = "partial";
  } else if (active.length > 0 && active.every((attempt) => attempt.status === "failed")) {
    status = "failed";
  } else {
    status = "publishing";
  }
  return {
    status,
    links,
    errors,
    retryAfter: active.map((attempt) => attempt.retryAfter).find(Boolean),
    scheduledFor: active.map((attempt) => attempt.scheduledFor).find(Boolean),
  };
}

async function loadPlan(state: WorkflowState): Promise<ZernioPublishPlan> {
  if (state.publish?.mode !== "api" || !state.publish.planFile) {
    throw new Error("Workflow has no prepared Zernio API plan.");
  }
  const raw = await readFile(state.publish.planFile);
  if (createHash("sha256").update(raw).digest("hex") !== state.publish.planHash) throw new Error("Plan changed after preparation.");
  return JSON.parse(raw.toString("utf8")) as ZernioPublishPlan;
}

async function refreshAttempts(
  config: CliConfig,
  profiles: ZernioProfilesFile,
  attempts: ZernioPublishAttempt[],
): Promise<void> {
  for (const attempt of attempts) {
    if (!attempt.postId) continue;
    try {
      const response = await requestJson<unknown>(
        config,
        apiKeyFor(profiles, attempt.profile),
        `posts/${encodeURIComponent(attempt.postId)}`,
      );
      updateAttemptFromPost(attempt, unwrapPost(response));
    } catch (error) {
      attempt.errorMessage = error instanceof Error ? error.message : String(error);
    }
  }
}

async function pollKnownPosts(
  config: CliConfig,
  profiles: ZernioProfilesFile,
  attempts: ZernioPublishAttempt[],
  timeoutMs: number,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  await refreshAttempts(config, profiles, attempts);
  while (
    attempts.some((attempt) => ["pending", "publishing"].includes(attempt.status)) &&
    Date.now() < deadline
  ) {
    await new Promise((resolve) => setTimeout(resolve, Math.min(8_000, deadline - Date.now())));
    await refreshAttempts(config, profiles, attempts);
  }
}

export async function publishPreparedApiPosts(
  config: CliConfig,
  state: WorkflowState,
  options: { confirmed: boolean; timeoutMs: number },
): Promise<PublishResult> {
  if (!options.confirmed) {
    throw new Error("Publishing is an external side effect. Obtain immediate user approval first.");
  }
  if (state.stage !== "publish_review") {
    throw new Error(`Zernio API publish requires publish_review, not '${state.stage}'.`);
  }
  const plan = await loadPlan(state);
  assertPlanCoverage(plan, state.runId);
  const metadata = await loadMetadata(state.publish!.metadataFile);
  const videoFile = requireVideoFile(state, state.publish!.videoFile);
  await validateMp4(videoFile);
  const fingerprint = await fileFingerprint(metadata, videoFile, plan.kind);
  if (fingerprint !== plan.fingerprint || fingerprint !== state.publish?.preparedFingerprint) {
    throw new Error("Publish metadata or video changed after API preflight. Run prepare again.");
  }
  const profiles = await loadProfiles(config);
  assertProfileCoverage(profiles, metadata);
  const currentAttempts = state.publish?.attempts ?? [];
  const attempts: ZernioPublishAttempt[] = plan.profiles.map((prepared) => ({
    profile: prepared.alias,
    platforms: prepared.platforms,
    requestId: randomUUID(),
    requestedAt: new Date().toISOString(),
    status: "pending",
    platformResults: [],
    ...(typeof prepared.body.scheduledFor === "string" ? { scheduledFor: prepared.body.scheduledFor } : {}),
  }));
  state.publish!.attempts = [...currentAttempts, ...attempts];
  await transitionWorkflow(config, state, "publishing", "User authorized prepared Zernio publish.");

  for (let index = 0; index < plan.profiles.length; index += 1) {
    const prepared = plan.profiles[index];
    const attempt = attempts[index];
    attempt.status = "uncertain";
    await saveWorkflow(config, state);
    try {
      const response = await requestJson<unknown>(
        config,
        apiKeyFor(profiles, prepared.alias),
        "posts",
        { method: "POST", body: prepared.body, requestId: attempt.requestId },
      );
      updateAttemptFromPost(attempt, unwrapPost(response));
    } catch (error) {
      if (error instanceof ZernioApiError) {
        attempt.status = error.status === 0 || error.status >= 500 ? "uncertain" : "failed";
        attempt.errorCode = error.code;
        attempt.errorMessage = error.message;
        attempt.retryAfter = error.retryAfter;
      } else {
        attempt.status = "uncertain";
        attempt.errorMessage = error instanceof Error ? error.message : String(error);
      }
    }
    await saveWorkflow(config, state);
  }

  await pollKnownPosts(config, profiles, attempts, options.timeoutMs);
  const result = aggregateResult(attempts);
  state.publish!.result = result;
  await transitionWorkflow(config, state, result.status, "Zernio API publish result recorded per profile.");
  return result;
}

export async function inspectApiPosts(
  config: CliConfig,
  state: WorkflowState,
): Promise<PublishResult> {
  const attempts = state.publish?.attempts;
  if (!attempts?.length) throw new Error("Workflow has no Zernio API attempts to inspect.");
  const plan = await loadPlan(state);
  const profiles = await loadProfiles(config);
  const currentAttempts = attempts.slice(-plan.profiles.length);
  await refreshAttempts(config, profiles, currentAttempts);
  const result = aggregateResult(currentAttempts);
  state.publish!.result = result;
  await transitionWorkflow(config, state, result.status, "Zernio API posts inspected without publishing.");
  return result;
}

export async function retryApiPosts(config: CliConfig, state: WorkflowState, options: { confirmed: boolean; timeoutMs: number }): Promise<PublishResult> {
  if (!options.confirmed) throw new Error("Publishing authorization is required.");
  const plan = await loadPlan(state);
  const profiles = await loadProfiles(config);
  const attempts = state.publish?.attempts;
  if (!attempts?.length) throw new Error("No recorded attempt; use publish.");
  await refreshAttempts(config, profiles, attempts);
  await saveWorkflow(config, state);
  if (attempts.some(a => ["uncertain", "publishing"].includes(a.status) && !a.postId))
    throw new Error("An attempt has no post ID and its outcome is uncertain. Reconcile in Zernio, then adopt the verified post ID. Do not create another run.");
  for (const attempt of attempts) {
    if (!["pending", "failed", "partial"].includes(attempt.status)) continue;
    if (attempt.retryAfter) throw new Error(`Recorded retry limit: ${attempt.retryAfter}. Inspect and reconcile before retrying.`);
    const unsent = attempt.status === "pending";
    if (!unsent && !attempt.postId) throw new Error("Failed attempt has no ID. Reconcile manually; no automatic new post.");
    if (unsent) assertPlanCoverage(plan, state.runId);
    const prepared = plan.profiles.find(p => p.alias === attempt.profile);
    if (!prepared) throw new Error("Missing prepared profile.");
    attempt.status = "uncertain";
    await saveWorkflow(config, state);
    try {
      const response = await requestJson<unknown>(config, apiKeyFor(profiles, attempt.profile),
        unsent ? "posts" : `posts/${encodeURIComponent(attempt.postId!)}/retry`,
        { method: "POST", body: unsent ? prepared.body : {}, requestId: unsent ? attempt.requestId : randomUUID() });
      updateAttemptFromPost(attempt, unwrapPost(response));
    } catch (error) {
      attempt.status = "uncertain";
      attempt.errorMessage = error instanceof Error ? error.message : String(error);
    }
    await saveWorkflow(config, state);
  }
  await pollKnownPosts(config, profiles, attempts, options.timeoutMs);
  const result = aggregateResult(attempts);
  state.publish!.result = result;
  await transitionWorkflow(config, state, result.status, "Recorded attempts refreshed or retried.");
  return result;
}

export async function ensureZernioFiles(config: CliConfig): Promise<void> {
  await access(config.zernioProfilesFile);
  await access(config.zernioEnvFile);
}
