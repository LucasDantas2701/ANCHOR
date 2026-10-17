import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { Profile, Runs, apiError } from '../api';

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
      <div class="row">
        <div>
          <label for="url">On which page?</label>
          <input id="url" name="url" [(ngModel)]="url" placeholder="shop.example.com">
        </div>
        <div>
          <label for="profile">Model</label>
          <select id="profile" name="profile" [(ngModel)]="profile">
            @for (p of profiles(); track p.name) { <option [value]="p.name">{{ p.label }}</option> }
          </select>
        </div>
      </div>
      <label class="check"><input type="checkbox" name="show" [(ngModel)]="show"> Show the browser window (needed when the page asks you to log in)</label>
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
      <div class="actions">
        <button class="btn primary" type="submit" [disabled]="busy()">{{ busy() ? 'Starting…' : 'Run' }}</button>
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
    .check { display: flex; gap: 8px; align-items: center; font-size: 14px; color: var(--ink); margin: 0; }
    .check input { width: auto; }
    .btn:disabled { opacity: .6; }
  `],
})
export class RequestPage {
  private runs = inject(Runs);
  private router = inject(Router);
  profiles = signal<Profile[]>([]);
  request = ''; url = ''; profile = 'ollama-small'; show = true;
  busy = signal(false);
  error = signal('');

  constructor() {
    this.runs.profiles().subscribe(p => { this.profiles.set(p); if (p.length && !p.some(x => x.name === this.profile)) this.profile = p[0].name; });
  }

  start() {
    this.error.set(''); this.busy.set(true);
    this.runs.startRequest(this.request, this.url, this.profile, this.show).subscribe({
      next: r => this.router.navigate(['/runs', r.id]),
      error: e => { this.busy.set(false); this.error.set(apiError(e, 'The run could not start.')); },
    });
  }
}
