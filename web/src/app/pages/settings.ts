import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api, Choice, apiError, isoDate } from '../api';

/** Settings: for now, the choices remembered from requests (each automation keeps its own). */
@Component({
  selector: 'app-settings',
  imports: [RouterLink],
  template: `
    <p class="eyebrow">ANCHOR</p>
    <h1 class="title">Settings</h1>

    <section>
      <p class="eyebrow">Remembered choices</p>
      <p class="muted lead">When ANCHOR was not sure which element a step of a request meant, you chose one, and it was remembered for
        that page. Forget a choice if it is wrong: the next time, ANCHOR asks again. The choices of each automation are on its own page,
        in the Choices tab (<a routerLink="/automations">Automations</a>).</p>
      @for (s of sites(); track s.site) {
        <article class="card site">
          <header><span class="mono">{{ s.site }}</span><span class="muted small">{{ s.choices.length }} choice{{ s.choices.length === 1 ? '' : 's' }}</span>
            <span class="grow"></span>
            <button class="btn small" type="button" (click)="forgetSite(s.site)">Forget all for this site</button></header>
          <ul>
            @for (c of s.choices; track c.key) {
              <li>
                <div><span class="mono">{{ c.description }}</span>&nbsp;<span class="muted">is</span>&nbsp;<span class="mono">“{{ c.element || 'an element without text' }}”</span>
                  <span class="muted small"> · used {{ c.uses }} time{{ c.uses === 1 ? '' : 's' }}@if (c.last_used) {, last {{ isoDate(c.last_used) }}}</span></div>
                <button class="btn small" type="button" (click)="forget(c)">Forget</button>
              </li>
            }
          </ul>
        </article>
      } @empty { <div class="card pad muted">No remembered choices from requests.</div> }
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    </section>
  `,
  styles: [`
    .lead { max-width: 760px; margin: var(--space-2) 0 var(--space-6); }
    section { margin-top: var(--space-8); max-width: 1080px; }
    .site { padding: var(--space-4) var(--space-6); margin-bottom: var(--space-4); }
    .site header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); }
    .grow { flex: 1; }
    ul { list-style: none; margin: 0; padding: 0; }
    li { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: 10px 0; border-top: 1px solid var(--border); font-size: 14px; }
    .small { font-size: 12.5px; }
    .btn.small { padding: 4px 10px; font-size: 12.5px; }
    .pad { padding: var(--space-4) var(--space-6); }
    .error { color: var(--refused); }
  `],
})
export class SettingsPage {
  private api = inject(Api);
  sites = signal<{ site: string; choices: Choice[] }[]>([]);
  error = signal('');
  isoDate = isoDate;

  constructor() { this.load(); }
  load() { this.api.requestChoices().subscribe({ next: s => this.sites.set(s), error: e => this.error.set(apiError(e, 'The choices could not be loaded.')) }); }
  forget(c: Choice) {
    if (!confirm(`Forget this choice? Next time, ANCHOR asks you again which element “${c.description}” means.`)) return;
    this.api.forgetRequestChoice(c.key).subscribe({ next: () => this.load(), error: e => this.error.set(apiError(e, 'This could not be done.')) });
  }
  forgetSite(site: string) {
    if (!confirm(`Forget every choice remembered for ${site}?`)) return;
    this.api.forgetRequestSite(site).subscribe({ next: () => this.load(), error: e => this.error.set(apiError(e, 'This could not be done.')) });
  }
}
