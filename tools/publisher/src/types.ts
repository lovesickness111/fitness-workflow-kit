export type SocialPlatform = "tiktok" | "youtube" | "facebook" | "linkedin";
export type WorkflowStage = "rendered" | "publish_review" | "publishing" | "published" | "partial" | "failed";
export interface PublishMetadata {
  content: string; title?: string; description?: string; tags?: string[];
  platforms: Partial<Record<SocialPlatform, boolean>>;
  youtubePrivacy?: "public" | "unlisted" | "private";
  youtubeMadeForKids?: boolean; youtubeContainsSyntheticMedia?: boolean;
  tiktokCaption?: string; tiktokPrivacyLevel?: string; tiktokVideoMadeWithAi?: boolean;
  facebookContentType?: "feed" | "reel"; facebookTitle?: string; scheduledAt?: string;
}
export interface ZernioAccountSelector { accountId?: string; username?: string }
export interface ZernioProfilesFile {
  version: 1;
  profiles: Record<string, { apiKeyEnv: string; platforms: Partial<Record<SocialPlatform, ZernioAccountSelector>> }>;
}
export interface ZernioPlatformResult {
  platform: SocialPlatform; status: string; platformPostUrl?: string; errorMessage?: string;
}
export interface ZernioPublishAttempt {
  profile: string; platforms: SocialPlatform[]; requestId: string; requestedAt: string;
  postId?: string;
  status: "pending" | "publishing" | "published" | "scheduled" | "partial" | "failed" | "uncertain";
  platformResults: ZernioPlatformResult[];
  errorCode?: string; errorMessage?: string; retryAfter?: string; scheduledFor?: string;
}
export interface PublishResult {
  status: "publishing" | "published" | "partial" | "failed";
  links: Record<string, string>; errors: string[]; retryAfter?: string; scheduledFor?: string;
}
export interface WorkflowState {
  version: 1; runId: string; stage: WorkflowStage; createdAt: string; updatedAt: string;
  videoFile: string;
  publish?: {
    mode: "api"; metadataFile: string; videoFile: string; planFile: string;
    planHash: string; preparedFingerprint: string; preparedAt: string;
    attempts?: ZernioPublishAttempt[]; result?: PublishResult;
  };
  history: Array<{ at: string; stage: WorkflowStage; note?: string }>;
}
export interface CliConfig {
  repoRoot: string; dataDir: string; workflowsDir: string;
  zernioApiBaseUrl: string; zernioProfilesFile: string; zernioEnvFile: string;
}
