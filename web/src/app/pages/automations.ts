import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api, AutomationSummary, STATE_CLASS, STATE_WORDS, host, parts, runDate } from '../api';

@Component({
  selector: 'app-automations',
  imports: [RouterLink],
  template: `
    <p class="eyebrow">Saved automations</p>
    <h1 class="title">Your <em>automations</em></h1>
    <p class="lead muted">Each one is a request that ANCHOR learned once and now repeats with no AI, checking every step.</p>

    @if (error()) {
      <div class="card notice" role="alert"><span class="badge refused">Not loaded</span>
        ANCHOR could not read your automations. Close this window and open ANCHOR again.</div>
    } @else if (items() === null) {
      <p class="muted">Loading your automations…</p>
    } @else if (items()!.length === 0) {
      <div class="card empty">
        <p class="heading">No automations yet</p>
        <p class="muted">An automation is a request you can run again, like "Register a customer and save". Creating
          them from here comes in the next version; for now, they are created with the command line.</p>
      </div>
    } @else {
      <ul class="list">
        @for (a of items(); track a.name) {
          <li>
            <a class="card row" [routerLink]="['/automations', a.name]">
              <div class="main">
                <span class="name">{{ a.name }}</span>
                <span class="request">@for (p of parts(a.request); track $index) {<span [class.param]="p.param">{{ p.text }}</span>}</span>
                <span class="site mono">{{ host(a.url) }}</span>
              </div>
              <div class="states">
                @if (!a.learned) { <span class="badge accent">Learns on first run</span> }
                @else if (a.proven) { <span class="badge">Ready · can run on a schedule</span> }
                @else { <span class="badge">Ready · {{ a.steps }} steps</span> }
                @if (a.last_run; as r) {
                  <span class="badge" [class]="'badge ' + stateClass[r.state]">{{ stateWords[r.state] }}</span>
                  <span class="when muted">{{ runDate(r.when) }}</span>
                } @else { <span class="when muted">Never run</span> }
              </div>
            </a>
          </li>
        }
      </ul>
    }
  `,
  styles: [`
    .lead { max-width: 560px; margin: var(--space-3) 0 var(--space-8); }
    .list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); max-width: 1080px; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-6); padding: var(--space-4) var(--space-6);
           color: inherit; text-decoration: none; transition: border-color .15s; }
    .row:hover { border-color: var(--border-strong); }
    .main { display: grid; gap: 2px; min-width: 0; }
    .name { font: 600 16px/22px var(--font-sans); letter-spacing: -0.01em; }
    .request { color: var(--ink-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .site { font-size: 12px; color: var(--ink-muted); }
    .states { display: flex; align-items: center; gap: var(--space-2); flex: none; }
    .when { font-size: 12px; min-width: 132px; text-align: right; }
    .empty, .notice { padding: var(--space-8); max-width: 640px; }
    .notice { display: flex; gap: var(--space-3); align-items: center; }
    .heading { font: 600 20px/26px var(--font-sans); letter-spacing: -0.02em; margin: 0 0 var(--space-2); }
  `],
})
export class AutomationsPage {
  private api = inject(Api);
  items = signal<AutomationSummary[] | null>(null);
  error = signal(false);
  stateWords = STATE_WORDS; stateClass = STATE_CLASS; host = host; runDate = runDate; parts = parts;

  constructor() {
    this.api.automations().subscribe({ next: a => this.items.set(a), error: () => this.error.set(true) });
  }
}
