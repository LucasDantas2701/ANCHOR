import { Component, ElementRef, OnDestroy, effect, inject, input, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ACTIVE, JOB_CLASS, JOB_WORDS, Question, RunEvent, RunView, Runs } from '../api';

const WHAT: Record<string, string> = {
  delete: 'delete something', submit: 'save or submit a form', send: 'send a message', pay: 'make a payment',
  download: 'download a file', upload: 'upload a file',
};

@Component({
  selector: 'app-run',
  imports: [RouterLink],
  template: `
    @if (run(); as r) {
      @if (r.kind === 'automation') { <a [routerLink]="['/automations', r.title]" class="back muted">← {{ r.title }}</a> }
      @else { <a routerLink="/run" class="back muted">← Run a request</a> }
      <p class="eyebrow">{{ r.kind === 'automation' ? 'Running an automation' : 'Running a request' }}</p>
      <div class="head">
        <h1 class="title">{{ r.kind === 'automation' ? r.title : 'Your request' }}</h1>
        <span [class]="'badge ' + jobClass[r.state]">{{ jobWords[r.state] }}@if (r.state === 'queued' && r.position > 1) { · {{ r.position - 1 }} ahead }</span>
        @if (active(r)) { <button class="btn stop" type="button" (click)="stop()" [disabled]="stopping()">{{ stopping() ? 'Stopping…' : 'Stop' }}</button> }
      </div>
      @if (r.kind === 'request') { <blockquote class="request">{{ r.title }}</blockquote> }
      @if (r.state === 'running' || r.state === 'waiting') {
        <p class="muted note">The browser is open in its own window, so you can watch every step.</p>
      }

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
                @if (q.can_point) { <button class="btn" type="button" (click)="answer(q, { choice: 'point' })">I'll click it in the browser</button> }
                <button class="btn quiet" type="button" (click)="answer(q, { choice: 'skip' })">Skip this step</button>
              </div>
            }
            @case ('login') {
              <h2 id="ask-title" class="heading">This page needs you to <em>{{ q.signup ? 'sign up' : 'log in' }}</em></h2>
              <p class="muted">Log in in the browser window, then come back here. ANCHOR never types or sees your password.</p>
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
          <p class="message">{{ res.message }}</p>
          @if (res.steps !== undefined) {
            <p class="muted small mono">{{ res.steps }} steps · {{ res.seconds }} s · {{ res.model_calls ? res.model_calls + ' AI calls' : 'no AI calls' }}</p>
          }
        </section>
      }

      <section>
        <p class="eyebrow">What happened</p>
        <ol class="log card" #log>
          @for (e of events(); track e.seq) {
            @if (e.type === 'line') { <li class="line">{{ e.text }}</li> }
            @if (e.type === 'answered') { <li class="you">You answered: {{ said(e) }}</li> }
          } @empty { <li class="line muted">{{ r.state === 'queued' ? 'Waiting for the run before it to finish…' : 'Starting…' }}</li> }
        </ol>
      </section>
    } @else if (missing()) {
      <h1 class="title">This run <em>is not here</em></h1>
      <p class="muted">Runs are kept only while ANCHOR is open.</p>
    } @else { <p class="muted">Loading…</p> }
  `,
  styles: [`
    .back { display: inline-block; margin-bottom: var(--space-6); text-decoration: none; font-size: 13px; }
    .head { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
    .stop { margin-left: auto; }
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
    .message { margin: 0; font-size: 16px; }
    .log { list-style: none; margin: 0; padding: var(--space-3) 0; max-height: 52vh; overflow: auto; }
    .log li { padding: 6px var(--space-6); font: 400 13px/20px var(--font-mono); white-space: pre-wrap; }
    .log .you { color: var(--accent); }
  `],
})
export class RunPage implements OnDestroy {
  private runs = inject(Runs);
  id = input.required<string>();
  run = signal<RunView | null>(null);
  events = signal<RunEvent[]>([]);
  missing = signal(false);
  stopping = signal(false);
  log = viewChild<ElementRef<HTMLElement>>('log');
  jobWords = JOB_WORDS; jobClass = JOB_CLASS;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private last = 0;

  constructor() {
    effect(() => { const id = +this.id(); this.reset(); this.poll(id); });
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
        if (this.active(v)) this.timer = setTimeout(() => this.poll(id), 500);
      },
      error: () => this.missing.set(true),
    });
  }

  active(r: RunView) { return ACTIVE.includes(r.state); }
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

  said(e: RunEvent): string {
    const a = (e['answer'] ?? {}) as Record<string, unknown>;
    switch (a['choice']) {
      case 'allow': return 'Allow'; case 'deny': return "Don't allow"; case 'not_now': return 'Not now';
      case 'candidate': return `option ${a['number']}`; case 'point': return "I'll click it in the browser";
      case 'skip': return 'Skip this step'; case 'done': return "I've logged in"; case 'cancel': return 'Cancel';
      default: return 'no answer (the run was stopped)';
    }
  }
}
