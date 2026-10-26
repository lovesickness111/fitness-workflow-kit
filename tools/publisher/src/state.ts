import { copyFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomBytes } from "node:crypto";

import type { CliConfig, WorkflowStage, WorkflowState } from "./types.js";

function compactTimestamp(date = new Date()): string {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

export function createRunId(): string {
  return `${compactTimestamp()}-${randomBytes(3).toString("hex")}`;
}

export function sanitizeRunId(runId: string): string {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{2,80}$/.test(runId)) {
    throw new Error("Run id must be 3-81 characters using letters, numbers, dot, dash, or underscore.");
  }
  return runId;
}

export function runDir(config: CliConfig, runId: string): string {
  return path.join(config.workflowsDir, sanitizeRunId(runId));
}

export function statePath(config: CliConfig, runId: string): string {
  return path.join(runDir(config, runId), "state.json");
}

export async function writeJsonAtomic(filePath: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  const temporaryPath = `${filePath}.${process.pid}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporaryPath, filePath);
}

export async function readJson<T>(filePath: string): Promise<T> {
  return JSON.parse(await readFile(filePath, "utf8")) as T;
}

export async function loadWorkflow(config: CliConfig, runId: string): Promise<WorkflowState> {
  return readJson<WorkflowState>(statePath(config, runId));
}

export async function saveWorkflow(
  config: CliConfig,
  state: WorkflowState,
): Promise<WorkflowState> {
  state.updatedAt = new Date().toISOString();
  await writeJsonAtomic(statePath(config, state.runId), state);
  return state;
}

export async function transitionWorkflow(
  config: CliConfig,
  state: WorkflowState,
  stage: WorkflowStage,
  note?: string,
): Promise<WorkflowState> {
  const at = new Date().toISOString();
  state.stage = stage;
  state.updatedAt = at;
  state.history.push({ at, stage, note });
  await writeJsonAtomic(statePath(config, state.runId), state);
  return state;
}
