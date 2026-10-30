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
  runs: Run[]; recoveries: number; notes: number; confirmations: number; choices: number;
}

export interface PlanStep { action: string; description: string; value: string | null; }
export interface Fix {
  number: number; date: string; undone: boolean; method: 'replan' | 'user';
  failed?: PlanStep | null; reason?: string; replaced_by?: PlanStep[]; effect_confirmed?: boolean;   // replan
  step?: PlanStep | null;                                                                         // user
}
export interface Note { number: number; date: string; text: string; run: string; sent: boolean; edited?: string; }
export interface Decision { number: number; date: string; action: string; element: string; category: string; decision: 'allowed' | 'denied'; }
export interface RowOutcome { number: number; state: JobState; message: string; values: Record<string, string>; }
export interface SheetCheck {
  rows: number; columns: string[]; missing: string[]; extra: string[]; blank_rows: number[]; too_many: boolean;
  preview: Record<string, string>[]; all: Record<string, string>[]; parameters: string[];
}
export interface Choice { key: string; action: string; description: string; url: string; element: string; uses: number; last_used: string; }

@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  info() { return this.http.get<{ version: string; docs: string }>('/api/info'); }
  automations() { return this.http.get<AutomationSummary[]>('/api/automations'); }
  automation(name: string) { return this.http.get<AutomationDetail>(`/api/automations/${encodeURIComponent(name)}`); }
  create(name: string, request: string, url: string, profile: string) {
    return this.http.post<AutomationSummary>('/api/automations', { name, request, url, profile });
  }
  private at(name: string, rest = '') { return `/api/automations/${encodeURIComponent(name)}${rest}`; }
  fixes(name: string) { return this.http.get<Fix[]>(this.at(name, '/fixes')); }
  undoFix(name: string, n: number) { return this.http.post<Fix>(this.at(name, `/fixes/${n}/undo`), {}); }
  notes(name: string) { return this.http.get<Note[]>(this.at(name, '/notes')); }
  addNote(name: string, text: string, run = '') { return this.http.post<Note>(this.at(name, '/notes'), { text, run }); }
  editNote(name: string, n: number, text: string) { return this.http.put(this.at(name, `/notes/${n}`), { text }); }
  removeNote(name: string, n: number) { return this.http.delete(this.at(name, `/notes/${n}`)); }
  decisions(name: string) { return this.http.get<Decision[]>(this.at(name, '/decisions')); }
  forgetDecision(name: string, n: number) { return this.http.delete(this.at(name, `/decisions/${n}`)); }
  choices(name: string) { return this.http.get<Choice[]>(this.at(name, '/choices')); }
  forgetChoice(name: string, key: string) { return this.http.delete(this.at(name, '/choices'), { params: { key } }); }
  edit(name: string, request: string, url: string, profile: string) {
    return this.http.put<{ relearn: boolean; parameters: string[] }>(this.at(name), { request, url, profile });
  }
  remove(name: string, confirm: string) { return this.http.delete(this.at(name), { params: { confirm } }); }
  checkSheet(name: string, filename: string, content: string) { return this.http.post<SheetCheck>(this.at(name, '/sheet'), { filename, content }); }
}

/** "20261017-101500" → "17 Oct 2026, 10:15" */
export function runDate(id: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(id);
  if (!m) return id;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${+m[3]} ${months[+m[2] - 1]} ${m[1]}, ${m[4]}:${m[5]}`;
}

/** The values a request names ({name} → "name"), as the automation store finds them. */
export function valuesIn(request: string): string[] {
  return [...new Set([...request.matchAll(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g)].map(m => m[1]))];
}

/** A name for an automation from its request: lowercase letters, digits and hyphens. */
const SMALL_WORDS = new Set(['a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with', 'from', 'at', 'it', 'its', 'my', 'your',
  'o', 'os', 'as', 'um', 'uma', 'e', 'ou', 'de', 'do', 'da', 'dos', 'das', 'no', 'na', 'nos', 'nas', 'em', 'para', 'com', 'por', 'meu', 'minha']);

/** A name for an automation from its request: its first meaningful words, lowercase, with hyphens. */
export function nameFor(request: string): string {
  const words = request.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    .replace(/[{}]/g, ' ').split(/[^a-z0-9]+/).filter(w => w && !SMALL_WORDS.has(w));
  return [...new Set(words)].slice(0, 4).join('-').slice(0, 64) || 'my-automation';
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

export type JobState = 'queued' | 'running' | 'waiting' | 'checked' | 'planned' | 'not_done' | 'stopped' | 'error';

export interface Question {
  number: number; kind: 'confirm' | 'choose' | 'login' | 'point';
  // confirm
  category?: string; element?: string; shown?: string; near?: string; description?: string; remembers?: boolean;
  // choose
  action?: string; reason?: 'ambiguous' | 'not_found'; can_point?: boolean; screenshot?: string | null;
  candidates?: { number: number; kind: string; name: string; near: string }[];
  // login
  url?: string; signup?: boolean; window?: boolean; keeps_notes?: boolean;
}

export interface RunEvent { seq: number; at: string; type: 'line' | 'used' | 'tried' | 'page' | 'ended_on' | 'row' | 'state' | 'question' | 'answered' | 'result'; text?: string; [k: string]: unknown; }

export interface RunResult { state: JobState; message: string; summary?: string; hint?: string; rows?: RowOutcome[];
  plan?: { steps: Step[]; goals: { id: string; description: string; conclusive: boolean }[] }; steps?: number; seconds?: number; model_calls?: number; mode?: string; }

export interface RunView {
  suggest_note?: { text: string; reason: string } | null;
  id: number; kind: 'automation' | 'request' | 'login' | 'plan'; title: string; can_save: boolean; state: JobState; position: number;
  question: Question | null; result: RunResult | null; events: RunEvent[]; spec: Record<string, unknown>;
  activity: { phase: string; seconds: number; tokens: number; attempt: number } | null;
  tabs?: Tab[]; viewing?: number | null;
}

export interface Tab { index: number; title: string; url: string; anchor: boolean; }

export interface RunListItem {
  id: number; kind: string; title: string; state: JobState; position: number;
  name?: string | null; created?: string; started?: string; finished?: string; message?: string;
}

export interface Profile { name: string; label: string; }

@Injectable({ providedIn: 'root' })
export class Runs {
  private http = inject(HttpClient);
  startAutomation(name: string, values: Record<string, string>, relearn: boolean, freshBrowser: boolean, showBrowser: boolean,
                  rows?: Record<string, string>[]) {
    return this.http.post<{ id: number }>('/api/runs', { kind: 'automation', name, values, relearn, fresh_browser: freshBrowser, show_browser: showBrowser, rows });
  }
  startRequest(request: string, url: string, profile: string, showBrowser: boolean) {
    return this.http.post<{ id: number }>('/api/runs', { kind: 'request', request, url, profile, show_browser: showBrowser });
  }
  view(id: number, after: number) { return this.http.get<RunView>(`/api/runs/${id}?after=${after}`); }
  list() { return this.http.get<RunListItem[]>('/api/runs'); }
  answer(id: number, number: number, answer: Record<string, unknown>) { return this.http.post(`/api/runs/${id}/answer`, { number, answer }); }
  stop(id: number) { return this.http.post(`/api/runs/${id}/stop`, {}); }
  frame(id: number, after: number) {
    return this.http.get(`/api/runs/${id}/frame?after=${after}`, { observe: 'response', responseType: 'blob' });
  }
  details(id: number) { return this.http.get(`/api/runs/${id}/details`, { responseType: 'blob' }); }
  plan(request: string, url: string, profile: string) {
    return this.http.post<{ id: number }>('/api/runs', { kind: 'plan', request, url, profile });
  }
  save(id: number, name: string) { return this.http.post<AutomationSummary>(`/api/runs/${id}/save`, { name }); }
  input(id: number, event: Record<string, unknown>) { return this.http.post(`/api/runs/${id}/input`, event); }
  tab(id: number, index: number | null) { return this.http.post<{ viewing: number | null }>(`/api/runs/${id}/tab`, { index }); }
  logIn(name: string) { return this.http.post<{ id: number }>(`/api/automations/${encodeURIComponent(name)}/login`, {}); }
  profiles() { return this.http.get<Profile[]>('/api/profiles'); }
}

export const JOB_WORDS: Record<JobState, string> = {
  queued: 'Waiting its turn', running: 'Running', waiting: 'Waiting for you', checked: 'Checked', planned: 'Planned',
  not_done: 'Not done', stopped: 'Stopped', error: 'Could not run',
};
export const JOB_CLASS: Record<JobState, string> = {
  queued: '', running: 'accent', waiting: 'waiting', checked: 'checked', planned: 'accent', not_done: 'refused', stopped: 'waiting', error: 'refused',
};
export const ACTIVE: JobState[] = ['queued', 'running', 'waiting'];

/** An error from the API, in the words the server wrote for the person. */
export function apiError(err: unknown, fallback: string): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  return typeof detail === 'string' ? detail : fallback;
}
