import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { Api, Profile, Runs, apiError, nameFor, valuesIn } from '../api';

@Component({
  selector: 'app-new-automation',
  imports: [FormsModule, RouterLink],
  template: `
    <a routerLink="/automations" class="back muted">← All automations</a>
    <p class="eyebrow">New automation</p>
    <h1 class="title">A task you will <em>run again</em></h1>
    <p class="lead muted">The first run learns the steps with the AI and checks each one. After that, ANCHOR repeats them
      with one click, without the AI, and fixes them by itself if the site changes.</p>

    <form class="card form" (ngSubmit)="create()">
      <label for="request">What should it do?</label>
      <textarea id="request" name="request" rows="3" [(ngModel)]="request" (ngModelChange)="suggest()"
        placeholder="Register {name}, phone {phone}, and save the record"></textarea>
      <p class="hint muted">Put a word in braces for each value that changes from run to run, like <span class="param">name</span>
        in <span class="mono">{{ '{' }}name{{ '}' }}</span>: each run asks for it (or reads it from a spreadsheet).</p>
      @if (values().length) {
        <p class="found">Each run will ask for: @for (v of values(); track v) { <span class="param">{{ v }}</span> }</p>
      }
      <div class="row">
        <div>
          <label for="url">On which page does it start?</label>
          <input id="url" name="url" [(ngModel)]="url" placeholder="crm.example.com/customers/new">
        </div>
        <div>
          <label for="profile">Model</label>
          <select id="profile" name="profile" [(ngModel)]="profile">
            @for (p of profiles(); track p.name) { <option [value]="p.name">{{ p.label }}</option> }
          </select>
        </div>
      </div>
      <div>
        <label for="name">Name</label>
        <input id="name" name="name" [(ngModel)]="name" (ngModelChange)="named = true" class="mono">
        <p class="hint muted">Lowercase letters, numbers and hyphens, like <span class="mono">register-customer</span>.</p>
      </div>
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
      <div class="actions">
        <button class="btn primary" type="submit" [disabled]="busy()">{{ busy() ? 'Creating…' : 'Create automation' }}</button>
        <span class="muted small">Never write a password here: when a page needs a login, ANCHOR waits for you to do it.</span>
      </div>
    </form>
  `,
  styles: [`
    .back { display: inline-block; margin-bottom: var(--space-6); text-decoration: none; font-size: 13px; }
    .lead { max-width: 640px; margin: var(--space-3) 0 var(--space-8); }
    .form { padding: var(--space-6); max-width: 760px; display: grid; gap: var(--space-4); }
    label { font: 500 13px/18px var(--font-sans); color: var(--ink-muted); display: block; margin-bottom: 6px; }
    textarea, input, select { width: 100%; background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm); padding: 10px 12px; font: 400 15px/22px var(--font-sans); }
    input.mono { font-family: var(--font-mono); font-size: 14px; }
    textarea { resize: vertical; }
    .hint { font-size: 13px; margin: 6px 0 0; } .found { margin: 0; font-size: 14px; }
    .row { display: grid; grid-template-columns: 2fr 1fr; gap: var(--space-4); }
    .actions { display: flex; align-items: center; gap: var(--space-4); }
    .small { font-size: 13px; } .error { color: var(--refused); margin: 0; } .btn:disabled { opacity: .6; }
  `],
})
export class NewAutomationPage {
  private api = inject(Api);
  private runs = inject(Runs);
  private router = inject(Router);
  profiles = signal<Profile[]>([]);
  request = ''; url = ''; profile = 'ollama-small'; name = '';
  named = false;
  values = signal<string[]>([]);
  busy = signal(false);
  error = signal('');

  constructor() {
    this.runs.profiles().subscribe(p => { this.profiles.set(p); if (p.length && !p.some(x => x.name === this.profile)) this.profile = p[0].name; });
  }

  suggest() {
    this.values.set(valuesIn(this.request));
    if (!this.named) this.name = nameFor(this.request);
  }

  create() {
    this.error.set(''); this.busy.set(true);
    this.api.create(this.name.trim(), this.request, this.url, this.profile).subscribe({
      next: a => this.router.navigate(['/automations', a.name]),
      error: e => { this.busy.set(false); this.error.set(apiError(e, 'The automation could not be created.')); },
    });
  }
}
