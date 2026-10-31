import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { Profile, Runs, apiError } from '../api';
import { fromCommand } from '../command';

@Component({
  selector: 'app-request',
  imports: [FormsModule],
  template: `
    <p class="eyebrow">Run a request</p>
    <h1 class="title">Tell ANCHOR <em>what to do</em></h1>
    <p class="lead muted">Write it as you would ask a colleague. ANCHOR plans the steps with the AI on your computer,
      does them in the browser and checks each one. Nothing is saved for next time; for that, create an automation.</p>

    <form class="card form" (ngSubmit)="start()">
      <label for="request">What should ANCHOR do?</label>
      <textarea id="request" name="request" rows="3" [(ngModel)]="request"
        placeholder="Search for wireless headphones and add the cheapest one to the cart"></textarea>
      @if (pasted(); as c) {
        <div class="warn" role="status">This looks like a terminal command, not a request: ANCHOR would read the command itself.
          @if (c.request) { <button class="btn quiet" type="button" (click)="useCommand()">Use “{{ c.request }}”@if (c.url) { on {{ c.url }} }</button> }
          @else { Write only what ANCHOR should do, and put the page in “On which page?”. }
        </div>
      }
      <div class="row">
        <div>
          <label for="url">On which page?</label>
          <input id="url" name="url" [(ngModel)]="url" placeholder="shop.example.com">
        </div>
        <div>
          <label for="profile">Model</label>
          <select id="profile" name="profile" [(ngModel)]="profile">
            @for (p of profiles(); track p.name) { <option [value]="p.name" [disabled]="p.downloaded === false">{{ p.label }}{{ p.downloaded === false ? ' (not downloaded)' : '' }}</option> }
          </select>
        </div>
      </div>
      <label class="check"><input type="checkbox" name="show" [(ngModel)]="show"> Also open the browser in its own window</label>
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
      <div class="actions">
        <button class="btn primary" type="submit" [disabled]="busy()">{{ busy() ? 'Starting…' : 'Run' }}</button>
        <button class="btn" type="button" (click)="seePlan()" [disabled]="busy()" title="The AI plans the steps on the page; nothing is done">See the plan first</button>
        <span class="muted small">Never write a password here: when a page needs a login, ANCHOR waits for you to do it.</span>
      </div>
    </form>
  `,
  styles: [`
    .lead { max-width: 620px; margin: var(--space-3) 0 var(--space-8); }
    .form { padding: var(--space-6); max-width: 760px; display: grid; gap: var(--space-3); }
    label { font: 500 13px/18px var(--font-sans); color: var(--ink-muted); display: block; margin-bottom: 6px; }
    textarea, input, select { width: 100%; background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm); padding: 10px 12px; font: 400 15px/22px var(--font-sans); }
    textarea { resize: vertical; }
    .row { display: grid; grid-template-columns: 2fr 1fr; gap: var(--space-4); }
    .actions { display: flex; align-items: center; gap: var(--space-4); margin-top: var(--space-2); }
    .small { font-size: 13px; }
    .error { color: var(--refused); margin: 0; }
    .warn { border: 1px solid var(--waiting); border-radius: var(--radius-sm); padding: 10px 12px; font-size: 14px; color: var(--ink);
            display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; }
    .check { display: flex; gap: 8px; align-items: center; font-size: 14px; color: var(--ink); margin: 0; }
    .check input { width: auto; }
    .btn:disabled { opacity: .6; }
  `],
})
export class RequestPage {
  pasted() { return fromCommand(this.request); }
  useCommand() {
    const c = fromCommand(this.request);
    if (!c) return;
    this.request = c.request;
    if (c.url) this.url = c.url;
  }
  private runs = inject(Runs);
  private router = inject(Router);
  profiles = signal<Profile[]>([]);
  request = ''; url = ''; profile = 'ollama-small'; show = false;
  busy = signal(false);
  error = signal('');

  constructor() {
    const q = inject(ActivatedRoute).snapshot.queryParamMap;          // "Try again": the last try, filled in
    this.request = q.get('request') ?? ''; this.url = q.get('url') ?? '';
    this.profile = q.get('profile') ?? this.profile; this.show = q.get('window') === '1';
    this.runs.profiles().subscribe(p => { this.profiles.set(p); const usable = p.filter(x => x.downloaded !== false);
      if (usable.length && !usable.some(x => x.name === this.profile)) this.profile = usable[0].name; });
  }

  seePlan() {
    this.error.set(''); this.busy.set(true);
    this.runs.plan(this.request, this.url, this.profile).subscribe({
      next: r => this.router.navigate(['/runs', r.id]),
      error: e => { this.busy.set(false); this.error.set(apiError(e, 'The plan could not start.')); },
    });
  }

  start() {
    this.error.set(''); this.busy.set(true);
    this.runs.startRequest(this.request, this.url, this.profile, this.show).subscribe({
      next: r => this.router.navigate(['/runs', r.id]),
      error: e => { this.busy.set(false); this.error.set(apiError(e, 'The run could not start.')); },
    });
  }
}
