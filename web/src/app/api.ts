import { HttpClient, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

/** The code made at each start: it arrives in the address's fragment, and stays only in this tab. */
const KEY = 'anchor-code';

export function takeCodeFromAddress(): void {
  const match = /(?:^#|&)token=([^&]+)/.exec(location.hash);
  if (match) {
    sessionStorage.setItem(KEY, decodeURIComponent(match[1]));
    history.replaceState(null, '', location.pathname + location.search);   // off the address bar
  }
}

export const withCode: HttpInterceptorFn = (req, next) => {
  const code = sessionStorage.getItem(KEY);
  return next(code && req.url.startsWith('/api/') ? req.clone({ setHeaders: { 'X-Anchor-Token': code } }) : req);
};

export type RunState = 'checked' | 'stopped' | 'not_done';

export interface Run { id: string; mode: string; state: RunState; status: string; message: string; seconds: number; when: string; }

export interface AutomationSummary {
  name: string; request: string; url: string; profile: string; parameters: string[];
  learned: boolean; steps: number; proven: boolean; last_run: Run | null;
}

export interface Step { action: string; description: string; value: string | null; }

export interface AutomationDetail extends AutomationSummary {
  plan: { approved: string; steps: Step[] } | null;
  runs: Run[]; recoveries: number; notes: number; confirmations: number;
}

@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  info() { return this.http.get<{ version: string; docs: string }>('/api/info'); }
  automations() { return this.http.get<AutomationSummary[]>('/api/automations'); }
  automation(name: string) { return this.http.get<AutomationDetail>(`/api/automations/${encodeURIComponent(name)}`); }
}

/** "20261017-101500" → "17 Oct 2026, 10:15" */
export function runDate(id: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(id);
  if (!m) return id;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${+m[3]} ${months[+m[2] - 1]} ${m[1]}, ${m[4]}:${m[5]}`;
}

export function host(url: string): string {
  try { const u = new URL(url); return u.protocol === 'file:' ? 'A file on this computer' : u.host; } catch { return url; }
}

export const STATE_WORDS: Record<RunState, string> = { checked: 'Checked', stopped: 'Stopped by you', not_done: 'Not done' };
export const STATE_CLASS: Record<RunState, string> = { checked: 'checked', stopped: 'waiting', not_done: 'refused' };

/** A request or value cut into text and the values the person gives ({name} → a "name" chip). */
export function parts(text: string | null): { text: string; param: boolean }[] {
  if (text === null) return [];
  return text.split(/(\{[^{}]+\})/).filter(Boolean)
    .map(p => /^\{[^{}]+\}$/.test(p) ? { text: p.slice(1, -1), param: true } : { text: p, param: false });
}

const MODELS: Record<string, string> = { 'ollama-small': 'Small · Qwen 3.5 4B', 'ollama-medium': 'Medium · Qwen 3.5 9B' };
export function modelName(profile: string): string { return MODELS[profile] ?? profile; }

/** "2026-10-17T16:00:12" → "17 Oct 2026, 16:00" */
export function isoDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  return m ? runDate(`${m[1]}${m[2]}${m[3]}-${m[4]}${m[5]}`) : iso;
}

// --- Runs ---------------------------------------------------------------------------------------

export type JobState = 'queued' | 'running' | 'waiting' | 'checked' | 'not_done' | 'stopped' | 'error';

export interface Question {
  number: number; kind: 'confirm' | 'choose' | 'login';
  // confirm
  category?: string; element?: string; description?: string; remembers?: boolean;
  // choose
  action?: string; reason?: 'ambiguous' | 'not_found'; can_point?: boolean; screenshot?: string | null;
  candidates?: { number: number; kind: string; name: string; near: string }[];
  // login
  url?: string; signup?: boolean;
}

export interface RunEvent { seq: number; at: string; type: 'line' | 'state' | 'question' | 'answered' | 'result'; text?: string; [k: string]: unknown; }

export interface RunResult { state: JobState; message: string; summary?: string; hint?: string; steps?: number; seconds?: number; model_calls?: number; mode?: string; }

export interface RunView {
  id: number; kind: 'automation' | 'request'; title: string; state: JobState; position: number;
  question: Question | null; result: RunResult | null; events: RunEvent[]; spec: Record<string, unknown>;
  activity: { phase: string; seconds: number; tokens: number; attempt: number } | null;
}

export interface RunListItem { id: number; kind: string; title: string; state: JobState; position: number; }

export interface Profile { name: string; label: string; }

@Injectable({ providedIn: 'root' })
export class Runs {
  private http = inject(HttpClient);
  startAutomation(name: string, values: Record<string, string>, relearn: boolean, freshBrowser: boolean, showBrowser: boolean) {
    return this.http.post<{ id: number }>('/api/runs', { kind: 'automation', name, values, relearn, fresh_browser: freshBrowser, show_browser: showBrowser });
  }
  startRequest(request: string, url: string, profile: string, showBrowser: boolean) {
    return this.http.post<{ id: number }>('/api/runs', { kind: 'request', request, url, profile, show_browser: showBrowser });
  }
  view(id: number, after: number) { return this.http.get<RunView>(`/api/runs/${id}?after=${after}`); }
  list() { return this.http.get<RunListItem[]>('/api/runs'); }
  answer(id: number, number: number, answer: Record<string, unknown>) { return this.http.post(`/api/runs/${id}/answer`, { number, answer }); }
  stop(id: number) { return this.http.post(`/api/runs/${id}/stop`, {}); }
  profiles() { return this.http.get<Profile[]>('/api/profiles'); }
}

export const JOB_WORDS: Record<JobState, string> = {
  queued: 'Waiting its turn', running: 'Running', waiting: 'Waiting for you', checked: 'Checked',
  not_done: 'Not done', stopped: 'Stopped', error: 'Could not run',
};
export const JOB_CLASS: Record<JobState, string> = {
  queued: '', running: 'accent', waiting: 'waiting', checked: 'checked', not_done: 'refused', stopped: 'waiting', error: 'refused',
};
export const ACTIVE: JobState[] = ['queued', 'running', 'waiting'];

/** An error from the API, in the words the server wrote for the person. */
export function apiError(err: unknown, fallback: string): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' ? detail : fallback;
}
