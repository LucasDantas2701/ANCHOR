import { Component, ElementRef, OnDestroy, effect, inject, input, signal, viewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { LiveView } from './live';

import { ACTIVE, JOB_CLASS, JOB_WORDS, JobState, Question, RunEvent, RunView, Runs, apiError, nameFor } from '../api';

const WHAT: Record<string, string> = {
  delete: 'delete something', submit: 'save or submit a form', send: 'send a message', pay: 'make a payment',
  download: 'download a file', upload: 'upload a file',
};

@Component({
  selector: 'app-run',
  imports: [RouterLink, LiveView],
  template: `
    @if (run(); as r) {
      <div class="layout" [class.theater]="watching()">
      <div class="top">
      @if (r.kind === 'automation' || r.kind === 'login') { <a [routerLink]="['/automations', r.title]" class="back muted">← {{ r.title }}</a> }
      @else { <a routerLink="/run" class="back muted">← Run a request</a> }
      <p class="eyebrow">{{ r.kind === 'automation' ? 'Running an automation' : r.kind === 'login' ? 'Logging in' : r.kind === 'plan' ? 'Planning only: nothing is done' : 'Running a request' }}</p>
      <div class="head">
        <h1 class="title">{{ r.kind === 'request' ? 'Your request' : r.kind === 'plan' ? 'The plan for your request' : r.title }}</h1>
        <span [class]="'badge ' + jobClass[r.state]">{{ jobWords[r.state] }}@if (r.state === 'queued' && r.position > 1) { · {{ r.position - 1 }} ahead }</span>
        <div class="head-actions">
          @if (watching()) { <button class="btn" type="button" (click)="watching.set(false)">Close the live view</button> }
          @else if (r.state !== 'queued' && r.kind !== 'plan') { <button class="btn" type="button" (click)="watching.set(true)">{{ active(r) ? 'Watch it run' : 'See the last view' }}</button> }
          @if (active(r)) { <button class="btn" type="button" (click)="stop()" [disabled]="stopping()">{{ stopping() ? 'Stopping…' : 'Stop' }}</button> }
        </div>
      </div>
      @if (r.kind === 'request' || r.kind === 'plan') { <blockquote class="request">{{ r.title }}</blockquote> }
      </div>
      @if ((r.state === 'running' || r.state === 'waiting') && r.spec['show_browser']) {
        <p class="muted note">The browser is also open in its own window.</p>
      }
      @if (watching()) { <app-live class="live" [run]="r.id" [state]="r.state" [ended]="!active(r)" [interactive]="takesInput(r)" (close)="watching.set(false)" /> }

      @if (r.question; as q) {
        <section class="ask card" role="alertdialog" aria-labelledby="ask-title">
          <p class="eyebrow">Waiting for you</p>
          @switch (q.kind) {
            @case ('confirm') {
              <h2 id="ask-title" class="heading">ANCHOR wants to {{ what(q.category) }}: <em>“{{ q.element }}”</em></h2>
              <p class="muted">Step: {{ q.description }}</p>
              <p class="muted small">{{ q.remembers ? 'Your answer is kept: this automation will not ask again for this step.' : 'Your answer is only for this run.' }}</p>
              <div class="actions">
                <button class="btn primary" type="button" (click)="answer(q, { choice: 'allow' })">Allow</button>
                <button class="btn" type="button" (click)="answer(q, { choice: 'deny' })">Don't allow</button>
                @if (q.remembers) { <button class="btn quiet" type="button" (click)="answer(q, { choice: 'not_now' })">Not now, ask me next time</button> }
              </div>
            }
            @case ('choose') {
              <h2 id="ask-title" class="heading">@if (q.reason === 'ambiguous') { Which one is <em>“{{ q.description }}”</em>? } @else { ANCHOR could not find <em>“{{ q.description }}”</em> }</h2>
              @if (q.screenshot) { <img class="shot" [src]="'data:image/png;base64,' + q.screenshot" alt="The page, with each option numbered"> }
              @if (q.candidates?.length) {
                <p class="muted small">{{ q.reason === 'ambiguous' ? 'These look alike. Choose the right one:' : 'Is it one of these?' }}</p>
                <div class="options">
                  @for (c of q.candidates; track c.number) {
                    <button class="option" type="button" (click)="answer(q, { choice: 'candidate', number: c.number })">
                      <span class="num mono">{{ c.number }}</span><span>{{ c.kind }} <strong>“{{ c.name }}”</strong>@if (c.near) { <span class="muted"> near {{ c.near }}</span> }</span>
                    </button>
                  }
                </div>
              }
              <div class="actions">
                @if (q.can_point) { <button class="btn" type="button" (click)="answer(q, { choice: 'point' })">I'll point at it on the live view</button> }
                <button class="btn quiet" type="button" (click)="answer(q, { choice: 'skip' })">Skip this step</button>
              </div>
            }
            @case ('point') {
              <h2 id="ask-title" class="heading">Click the element <em>on the live view</em></h2>
              <p class="muted">ANCHOR will use what you click for this step, and remember it for next time.</p>
              <div class="actions">
                <button class="btn" type="button" (click)="answer(q, { choice: 'cancel' })">Cancel</button>
              </div>
            }
            @case ('login') {
              <h2 id="ask-title" class="heading">This page needs you to <em>{{ q.signup ? 'sign up' : 'log in' }}</em></h2>
              <p class="muted">@if (q.window) { A browser window opened: log in there, or on the live view. } @else { Log in on the live view: click and type on the page (paste with Ctrl+V). }
                ANCHOR never types, keeps or sees your password.</p>
              <div class="actions">
                <button class="btn primary" type="button" (click)="answer(q, { choice: 'done' })">I've logged in, continue</button>
                <button class="btn" type="button" (click)="answer(q, { choice: 'cancel' })">Cancel the run</button>
              </div>
            }
          }
        </section>
      }

      @if (r.result; as res) {
        <section [class]="'outcome card ' + jobClass[res.state]">
          <span [class]="'badge ' + jobClass[res.state]">{{ jobWords[res.state] }}</span>
          <p class="summary">{{ res.summary || res.message }}</p>
          @if (res.hint) { <p class="hint">{{ res.hint }}</p> }
          @if (res.plan; as plan) {
            <ol class="plan">
              @for (s of plan.steps; track $index) {
                <li><span class="n mono">{{ $index + 1 }}</span><span class="step mono">{{ s.action }} {{ s.description }}@if (s.value !== null && s.value !== undefined) { <span class="val">= "{{ s.value }}"</span> }</span></li>
              }
            </ol>
            @if (plan.goals.length) {
              <p class="muted small goals-head">What it would check at the end:</p>
              <ul class="goals">@for (g of plan.goals; track g.id) { <li>{{ g.description }}</li> }</ul>
            }
          }
          @if (r.can_save) {
            <form class="save" (submit)="$event.preventDefault(); save(r)">
              <label for="save-name">Save it as an automation, to run it again with one click and no AI:</label>
              <div class="save-row">
                <input id="save-name" name="save-name" class="mono" [value]="saveName() || nameFor(r.title)" (input)="saveName.set($any($event.target).value)">
                <button class="btn primary" type="submit">Save as an automation</button>
              </div>
              <p class="save-note muted">It will do exactly what this run did, with the same values. For an automation that asks for a value each time, use New automation with the value in braces.</p>
              @if (saveError()) { <p class="err">{{ saveError() }}</p> }
            </form>
          }
          @if (res.summary && res.message && res.state !== 'checked' && res.state !== 'planned') { <p class="detail mono muted">{{ res.message }}</p> }
          @if (res.steps !== undefined) {
            <p class="muted small mono">{{ res.steps }} steps done · {{ res.seconds }} s · {{ res.model_calls ? res.model_calls + ' AI calls' : 'no AI calls' }}</p>
          }
          <div class="actions">
            @if (res.state === 'planned') { <button class="btn primary" type="button" (click)="runIt(r)">Run it</button>
              <button class="btn" type="button" (click)="retry(r)">Change the request</button> }
            @else if (res.state !== 'checked') { <button class="btn primary" type="button" (click)="retry(r)">Try again</button> }
            <button class="btn" type="button" (click)="saveDetails(r)">Save the details of this run</button>
          </div>
        </section>
      }

      <section class="logsec">
        <p class="eyebrow">What happened</p>
        <ol class="log card" #log>
          @for (e of events(); track e.seq) {
            @if (e.type === 'line') { <li [class]="'row ' + kindOf(e.text)"><time>{{ e.at }}</time><span class="mark" aria-hidden="true"></span><span class="text">{{ shown(e.text) }}</span></li> }
            @if (e.type === 'used') { <li class="row used"><time></time><span></span><span class="text">↳ on the {{ lower(e.text) }}</span></li> }
            @if (e.type === 'question') { <li class="row ask-row"><time>{{ e.at }}</time><span class="mark" aria-hidden="true"></span><span class="text">ANCHOR asked you a question</span></li> }
            @if (e.type === 'answered') { <li class="row you"><time>{{ e.at }}</time><span class="mark" aria-hidden="true"></span><span class="text">You answered: {{ said(e) }}</span></li> }
            @if (e.type === 'result') { <li [class]="'row end ' + jobClass[stateOf(e)]"><time>{{ e.at }}</time><span class="mark" aria-hidden="true"></span><span class="text">{{ jobWords[stateOf(e)] }}</span></li> }
          } @empty { @if (!r.activity) { <li class="row muted"><time></time><span class="mark"></span><span class="text">{{ r.state === 'queued' ? 'Waiting for the run before it to finish…' : 'Starting…' }}</span></li> } }
          @if (r.activity; as a) {
            <li class="row live"><time>now</time><span class="mark pulse" aria-hidden="true"></span>
              <span class="text">{{ a.phase === 'writing' ? 'The AI is writing the plan' : 'The AI is thinking' }}@if (a.attempt > 1) { (attempt {{ a.attempt }}) }… {{ a.seconds }} s</span></li>
          }
        </ol>
      </section>
      </div>
    } @else if (missing()) {
      <h1 class="title">This run <em>is not here</em></h1>
      <p class="muted">Runs are kept only while ANCHOR is open.</p>
    } @else { <p class="muted">Loading…</p> }
  `,
  styles: [`
    .back { display: inline-block; margin-bottom: var(--space-6); text-decoration: none; font-size: 13px; }
    /* Watching: the same content, filling the window: the browser left, the rest in a column on the right. */
    .theater { position: fixed; inset: 0; z-index: 40; background: var(--surface-page); padding: var(--space-4) var(--space-6) var(--space-6);
               display: grid; gap: var(--space-4) var(--space-6); grid-template-columns: minmax(0, 1fr) minmax(340px, 400px);
               grid-template-rows: auto auto auto minmax(0, 1fr); grid-template-areas: "top top" "live ask" "live outcome" "live log"; }
    .theater .top { grid-area: top; } .theater .live { grid-area: live; }
    .theater .ask { grid-area: ask; margin: 0; } .theater .outcome { grid-area: outcome; margin: 0; }
    .theater .logsec { grid-area: log; margin: 0; display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; }
    .theater .logsec .log { max-height: none; height: 100%; }
    .theater .back, .theater .top > .eyebrow, .theater .request, .theater .note { display: none; }
    .theater .head .title { font-size: 22px; line-height: 28px; }
    .theater .ask, .theater .outcome { padding: var(--space-4); }
    .theater .ask .heading { font-size: 17px; line-height: 23px; }
    .theater .row { grid-template-columns: 64px 16px 1fr; padding: 5px var(--space-4); }
    .head { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
    .head-actions { margin-left: auto; display: flex; gap: var(--space-3); }
    .request { margin: var(--space-4) 0 0; font: italic 400 22px/28px var(--font-serif); max-width: 760px; }
    .note { font-size: 13px; margin: var(--space-3) 0 0; }
    section { margin-top: var(--space-8); max-width: 1080px; }
    .ask { padding: var(--space-6); border-color: var(--waiting); background: var(--surface-raised); }
    .ask .eyebrow { color: var(--waiting); }
    .heading { font: 600 22px/28px var(--font-sans); letter-spacing: -0.02em; margin: 0 0 var(--space-2); }
    .heading em { font: italic 400 1.1em/1 var(--font-serif); color: var(--accent); }
    .small { font-size: 13px; }
    .actions { display: flex; gap: var(--space-3); flex-wrap: wrap; margin-top: var(--space-4); }
    .btn.quiet { border-color: transparent; color: var(--ink-muted); }
    .btn:disabled { opacity: .6; cursor: default; }
    .options { display: grid; gap: var(--space-2); margin-top: var(--space-2); }
    .option { display: flex; gap: var(--space-3); align-items: center; text-align: left; padding: var(--space-3) var(--space-4);
              background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
              font: 400 14px/20px var(--font-sans); cursor: pointer; }
    .option:hover { border-color: var(--accent); }
    .num { display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; background: var(--lime); color: #0C0A12;
           font-size: 12px; flex: none; }
    .shot { max-width: 100%; border-radius: var(--radius-sm); border: 1px solid var(--border); margin: var(--space-3) 0; }
    .outcome { padding: var(--space-4) var(--space-6); display: grid; gap: var(--space-2); justify-items: start; }
    .outcome.checked { border-color: var(--checked); } .outcome.refused { border-color: var(--refused); } .outcome.waiting { border-color: var(--waiting); }
    .plan { list-style: none; margin: var(--space-2) 0 0; padding: 0; display: grid; gap: 4px; width: 100%; }
    .plan li { display: grid; grid-template-columns: 28px 1fr; } .plan .n { color: var(--ink-muted); font-size: 12px; }
    .plan .step { font-size: 14px; } .plan .val { color: var(--accent); margin-left: 6px; }
    .goals-head { margin: var(--space-2) 0 0; } .goals { margin: 0; padding-left: 1.2em; font-size: 14px; }
    .save-note { margin: 0; font-size: 13px; }
    .save { display: grid; gap: 8px; width: 100%; margin-top: var(--space-2); padding-top: var(--space-3); border-top: 1px solid var(--border); }
    .save label { font-size: 14px; } .save-row { display: flex; gap: var(--space-3); }
    .save input { flex: 1; max-width: 360px; background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong);
                  border-radius: var(--radius-sm); padding: 8px 12px; font: 400 14px var(--font-mono); }
    .err { color: var(--refused); margin: 0; font-size: 13px; }
    .summary { margin: 0; font: 600 18px/24px var(--font-sans); letter-spacing: -0.01em; }
    .hint { margin: 0; color: var(--ink); max-width: 760px; }
    .detail { margin: 0; font-size: 12px; }
    .log { list-style: none; margin: 0; padding: var(--space-3) 0; max-height: 56vh; overflow: auto; }
    .row { display: grid; grid-template-columns: 72px 20px 1fr; align-items: baseline; padding: 6px var(--space-6); }
    .row time { font: 400 12px/20px var(--font-mono); color: var(--ink-muted); }
    .row .text { font: 400 14px/20px var(--font-sans); white-space: pre-wrap; }
    .mark { width: 8px; height: 8px; border-radius: 50%; background: var(--border-strong); justify-self: center; align-self: center; }
    .row.step .text { font: 400 13px/20px var(--font-mono); } .row.step .mark { background: var(--ink-muted); }
    .row.good .mark, .row.end.checked .mark { background: var(--checked); } .row.good .text, .row.end.checked .text { color: var(--checked); }
    .row.bad .mark, .row.end.refused .mark { background: var(--refused); } .row.bad .text, .row.end.refused .text { color: var(--refused); }
    .row.end .text { font-weight: 600; }
    .row.used { padding-top: 0; } .row.used .text { color: var(--ink-muted); font-size: 13px; }
    .row.you .mark, .row.ask-row .mark { background: var(--accent); } .row.you .text { color: var(--accent); }
    .row.ask-row .text { color: var(--waiting); } .row.ask-row .mark { background: var(--waiting); }
    .row.live .text { color: var(--ink-muted); } .pulse { background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
    @keyframes pulse { 50% { opacity: .3; transform: scale(.7); } }
    @media (prefers-reduced-motion: reduce) { .pulse { animation: none; } }
  `],
})
export class RunPage implements OnDestroy {
  private runs = inject(Runs);
  private router = inject(Router);
  watching = signal(false);
  id = input.required<string>();
  run = signal<RunView | null>(null);
  events = signal<RunEvent[]>([]);
  missing = signal(false);
  stopping = signal(false);
  log = viewChild<ElementRef<HTMLElement>>('log');
  jobWords = JOB_WORDS; jobClass = JOB_CLASS;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private opened = 0;
  private last = 0;

  constructor() {
    effect(() => { const id = +this.id(); this.reset(); this.poll(id); });
    // A login or a pointing needs the live view: it opens by itself, once for each question.
    effect(() => {
      const q = this.run()?.question;
      if (q && (q.kind === 'login' || q.kind === 'point') && q.number !== this.opened) { this.opened = q.number; this.watching.set(true); }
    });
  }

  ngOnDestroy() { clearTimeout(this.timer); }

  private reset() { clearTimeout(this.timer); this.run.set(null); this.events.set([]); this.last = 0; this.missing.set(false); this.stopping.set(false); }

  private poll(id: number) {
    this.runs.view(id, this.last).subscribe({
      next: v => {
        if (v.events.length) {
          this.last = v.events[v.events.length - 1].seq;
          this.events.update(list => [...list, ...v.events]);
          setTimeout(() => { const el = this.log()?.nativeElement; if (el) el.scrollTop = el.scrollHeight; });
        }
        this.run.set(v);
        if (this.active(v)) this.timer = setTimeout(() => this.poll(id), v.activity ? 1000 : 500);
      },
      error: () => this.missing.set(true),
    });
  }

  active(r: RunView) { return ACTIVE.includes(r.state); }
  takesInput(r: RunView) { return !!r.question && (r.question.kind === 'login' || r.question.kind === 'point'); }
  what(category?: string) { return WHAT[category ?? ''] ?? 'do something sensitive'; }

  answer(q: Question, answer: Record<string, unknown>) {
    const r = this.run(); if (!r) return;
    this.run.set({ ...r, question: null });                 // the panel closes at once; the poll confirms
    this.runs.answer(r.id, q.number, answer).subscribe({ error: () => {} });
  }

  stop() {
    const r = this.run(); if (!r) return;
    this.stopping.set(true);
    this.runs.stop(r.id).subscribe({ error: () => this.stopping.set(false) });
  }

  stateOf(e: RunEvent): JobState { return e['state'] as JobState; }
  lower(text?: string): string { const t = text ?? ''; return t.charAt(0).toLowerCase() + t.slice(1); }

  /** The same run again: the request's form filled in, or the automation's page with the same values. */
  saveName = signal('');
  saveError = signal('');
  nameFor = nameFor;

  save(r: RunView) {
    this.saveError.set('');
    this.runs.save(r.id, (this.saveName() || nameFor(r.title)).trim()).subscribe({
      next: a => this.router.navigate(['/automations', a.name]),
      error: e => this.saveError.set(apiError(e, 'It could not be saved.')),
    });
  }

  /** The plan looked right: run the same request for real. */
  runIt(r: RunView) {
    const s = r.spec as Record<string, unknown>;
    this.runs.startRequest(String(s['request']), String(s['url']), String(s['profile']), !!s['show_browser'])
      .subscribe(x => this.router.navigate(['/runs', x.id]));
  }

  retry(r: RunView) {
    const s = r.spec as Record<string, unknown>;
    if (r.kind === 'request' || r.kind === 'plan') {
      this.router.navigate(['/run'], { queryParams: { request: s['request'], url: s['url'], profile: s['profile'], window: s['show_browser'] ? 1 : null } });
    } else {
      this.router.navigate(['/automations', r.title], { state: { values: s['values'], relearn: s['relearn'], fresh: s['fresh_browser'], window: s['show_browser'] } });
    }
  }

  /** A file on this computer with what the model read and answered: for working out what went wrong. */
  saveDetails(r: RunView) {
    this.runs.details(r.id).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement('a'), { href: url, download: `anchor-run-${r.id}.json` });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }

  /** What a line is, to show it as a step, a success or a refusal. */
  kindOf(text?: string): string {
    const t = (text ?? '').toLowerCase();
    if (t.startsWith('→') || t.startsWith('->')) return 'step';
    if (t.startsWith('stopped') || t.includes('was not usable') || t.includes('refused') || t.includes('failed') || t.includes('not found')) return 'bad';
    if (t.startsWith('done') || t.includes('checked') || t.startsWith('allowed')) return 'good';
    return 'plain';
  }

  shown(text?: string): string { return (text ?? '').replace(/^(→|->)\s*/, ''); }

  said(e: RunEvent): string {
    const a = (e['answer'] ?? {}) as Record<string, unknown>;
    switch (a['choice']) {
      case 'allow': return 'Allow'; case 'deny': return "Don't allow"; case 'not_now': return 'Not now';
      case 'candidate': return `option ${a['number']}`; case 'point': return "I'll point at it on the live view";
      case 'skip': return 'Skip this step'; case 'done': return "I've logged in"; case 'cancel': return 'Cancel';
      case undefined: return (e['answer'] === null) ? 'the element, by clicking it' : 'no answer';
      default: return 'no answer (the run was stopped)';
    }
  }
}
