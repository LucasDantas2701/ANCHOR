import { Component, OnDestroy, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { JOB_CLASS, JOB_WORDS, RunListItem, Runs, apiError, isoDate } from '../api';

/** The queue: what is running, what waits its turn, and what ended in this session. */
@Component({
  selector: 'app-runs',
  imports: [RouterLink],
  template: `
    <p class="eyebrow">This session</p>
    <h1 class="title">Runs</h1>
    <p class="muted lead">ANCHOR does one run at a time, in the order they came. The others wait their turn here.</p>

    <section>
      <p class="eyebrow">Now</p>
      @if (active().length) {
        <table class="card list">
          <thead><tr><th class="pos">#</th><th>What</th><th>State</th><th>Since</th><th></th></tr></thead>
          <tbody>
            @for (r of active(); track r.id) {
              <tr>
                <td class="pos mono">@if (r.position === 0) { <span class="live" aria-label="running"></span> } @else { {{ r.position }} }</td>
                <td class="what">{{ label(r) }}</td>
                <td><span [class]="'badge ' + jobClass[r.state]">{{ jobWords[r.state] }}</span></td>
                <td class="muted">{{ when(r.started || r.created) }}</td>
                <td class="acts">
                  <a class="btn small" [routerLink]="['/runs', r.id]">{{ r.state === 'queued' ? 'Open' : 'Watch' }}</a>
                  <button class="btn small" type="button" (click)="stop(r)">{{ r.state === 'queued' ? 'Remove from queue' : 'Stop' }}</button>
                </td>
              </tr>
            }
          </tbody>
        </table>
      } @else { <div class="card pad muted">Nothing is running. Runs you start appear here.</div> }
    </section>

    <section>
      <p class="eyebrow">Ended</p>
      @if (ended().length) {
        <table class="card list">
          <thead><tr><th>What</th><th>Result</th><th>Ended</th><th>What happened</th><th></th></tr></thead>
          <tbody>
            @for (r of ended(); track r.id) {
              <tr>
                <td class="what">{{ label(r) }}</td>
                <td><span [class]="'badge ' + jobClass[r.state]">{{ jobWords[r.state] }}</span></td>
                <td class="muted">{{ when(r.finished) }}</td>
                <td class="msg muted" [title]="r.message || ''">{{ r.message }}</td>
                <td class="acts"><a class="btn small" [routerLink]="['/runs', r.id]">Open</a></td>
              </tr>
            }
          </tbody>
        </table>
      } @else { <div class="card pad muted">No run has ended yet in this session.</div> }
    </section>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
  `,
  styles: [`
    .lead { margin: var(--space-2) 0 var(--space-8); max-width: 720px; }
    section { margin-bottom: var(--space-8); max-width: 1080px; }
    .list { width: 100%; border-collapse: separate; border-spacing: 0; overflow: hidden; }
    th { text-align: left; font: 500 12px/16px var(--font-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--ink-muted);
         padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border); }
    td { padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border); font-size: 14px; vertical-align: middle; }
    tr:last-child td { border-bottom: 0; }
    .pos { width: 36px; text-align: center; color: var(--ink-muted); }
    .live { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: var(--lime); box-shadow: 0 0 0 4px rgba(210,245,122,.18); }
    .what { max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .msg { max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .acts { text-align: right; white-space: nowrap; }
    .acts .btn + .btn { margin-left: 6px; }
    .btn.small { padding: 4px 10px; font-size: 12.5px; text-decoration: none; }
    .pad { padding: var(--space-4) var(--space-6); }
    .error { color: var(--refused); }
  `],
})
export class RunsPage implements OnDestroy {
  private runs = inject(Runs);
  active = signal<RunListItem[]>([]);
  ended = signal<RunListItem[]>([]);
  error = signal('');
  jobWords = JOB_WORDS; jobClass = JOB_CLASS;
  private timer = setInterval(() => this.load(), 2000);

  constructor() { this.load(); }
  ngOnDestroy() { clearInterval(this.timer); }

  load() {
    this.runs.list().subscribe({
      next: list => {
        const live = list.filter(r => r.state === 'queued' || r.state === 'running' || r.state === 'waiting');
        this.active.set(live.sort((a, b) => a.position - b.position));
        this.ended.set(list.filter(r => !live.includes(r)));
      },
      error: e => this.error.set(apiError(e, 'The runs could not be loaded.')),
    });
  }
  label(r: RunListItem) { return r.kind === 'automation' ? r.title : r.kind === 'login' ? `Log in for ${r.title}` : r.title; }
  when(iso?: string) { return iso ? isoDate(iso) : ''; }
  stop(r: RunListItem) {
    const what = r.state === 'queued' ? 'Take this run out of the queue?' : 'Stop this run? What it already did on the site stays done.';
    if (!confirm(what)) return;
    this.runs.stop(r.id).subscribe({ next: () => this.load(), error: e => this.error.set(apiError(e, 'The run could not be stopped.')) });
  }
}
