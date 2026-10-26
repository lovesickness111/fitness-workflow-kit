import { open, stat } from "node:fs/promises";
import type { PublishMetadata } from "./types.js";

export function validatePublishMetadata(m: PublishMetadata): void {
  if (!m || typeof m.content !== "string" || !m.content.trim()) throw new Error("Nonempty content is required.");
  const allowed = ["tiktok", "youtube", "facebook", "linkedin"];
  if (!m.platforms || Object.entries(m.platforms).some(([p,v]) => !allowed.includes(p) || typeof v !== "boolean") || !Object.values(m.platforms).some(Boolean))
    throw new Error("Select at least one supported platform with boolean values.");
  if ("tiktokDraft" in m) throw new Error("TikTok Inbox mode is not automated by this kit.");
  if (m.platforms.youtube) {
    if (!m.title?.trim() || m.title.length > 100) throw new Error("YouTube title must contain 1 to 100 characters.");
    if (!["public", "unlisted", "private"].includes(m.youtubePrivacy ?? "")) throw new Error("Set youtubePrivacy explicitly.");
    if (typeof m.youtubeMadeForKids !== "boolean" || typeof m.youtubeContainsSyntheticMedia !== "boolean") throw new Error("Set YouTube audience and synthetic media flags explicitly.");
  }
  if (m.platforms.tiktok && (!m.tiktokPrivacyLevel || typeof m.tiktokVideoMadeWithAi !== "boolean")) throw new Error("Set TikTok privacy and AI label explicitly.");
  if (m.platforms.facebook && !["feed", "reel"].includes(m.facebookContentType ?? "")) throw new Error("Set Facebook feed or reel explicitly.");
  if (m.tags && (!Array.isArray(m.tags) || m.tags.some(t => typeof t !== "string"))) throw new Error("tags must be a string array.");
  if (m.scheduledAt && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(m.scheduledAt)) throw new Error("scheduledAt must include a timezone offset or Z.");
}

export async function validateMp4(file: string): Promise<void> {
  const info = await stat(file);
  if (!info.isFile() || info.size < 1024) throw new Error("Video must be a nonempty MP4 file.");
  const handle = await open(file, "r");
  try {
    const bytes = Buffer.alloc(12);
    await handle.read(bytes, 0, bytes.length, 0);
    if (bytes.toString("ascii", 4, 8) !== "ftyp") throw new Error("MP4 ftyp signature missing.");
  } finally { await handle.close(); }
}
