import { TrPipe, tr } from '../i18n';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api, AutomationSummary, STATE_CLASS, STATE_WORDS, host, parts, runDate } from '../api';

/** Lower case and without accents, so "relatorio" finds "relatório". */
const plain = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

@Component({
  selector: 'app-automations',
  imports: [RouterLink, TrPipe],
  template: `
    <div class="top">
      <div>
        <p class="eyebrow">{{ 'Saved automations' | tr }}</p>
        <h1 class="title">{{ 'Your' | tr }} <em>{{ 'automations' | tr }}</em></h1>
      </div>
      <a class="btn primary" routerLink="/automations/new">{{ 'New automation' | tr }}</a>
    </div>
    <p class="lead muted">{{ 'Each one is a request that ANCHOR learned once and now repeats with no AI, checking every step.' | tr }}</p>

    @if (error()) {
      <div class="card notice" role="alert"><span class="badge refused">{{ 'Not loaded' | tr }}</span>
        {{ 'ANCHOR could not read your automations. Close this window and open ANCHOR again.' | tr }}</div>
    } @else if (items() === null) {
      <p class="muted">{{ 'Loading your automations…' | tr }}</p>
    } @else if (items()!.length === 0) {
      <div class="card empty">
        <p class="heading">{{ 'No automations yet' | tr }}</p>
        <p class="muted">{{ 'An automation is a request you can run again, like "Register a customer and save". Create one with' | tr }} <a routerLink="/automations/new">{{ 'New automation' | tr }}</a>{{ ', or run a request and save it when it is done.' | tr }}</p>
      </div>
    } @else {
      <div class="tools" role="search">
        <input class="search" type="search" [value]="query()" (input)="query.set($any($event.target).value)"
               [placeholder]="'Search by name, request or site' | tr" [attr.aria-label]="'Search the automations' | tr">
        <div class="filters" role="group" [attr.aria-label]="'Show' | tr">
          @for (f of filters; track f.id) {
            <button type="button" class="chip" [class.on]="filter() === f.id" [attr.aria-pressed]="filter() === f.id" (click)="filter.set(f.id)">
              {{ f.label | tr }} <span class="n">{{ count(f.id) }}</span></button>
          }
        </div>
        <label class="sort">{{ 'Order' | tr }}
          <select [value]="sort()" (change)="sort.set($any($event.target).value)">
            <option value="recent">{{ 'Last run first' | tr }}</option>
            <option value="name">{{ 'Name' | tr }}</option>
          </select></label>
      </div>
      @if (!shown().length) {
        <div class="card empty"><p class="muted">{{ 'No automation matches.' | tr }}</p>
          <button class="btn" type="button" (click)="query.set(''); filter.set('all')">{{ 'Show all' | tr }}</button></div>
      }
      <ul class="list">
        @for (a of shown(); track a.name) {
          <li>
            <a class="card row" [routerLink]="['/automations', a.name]">
              <div class="main">
                <span class="name">{{ a.name }}</span>
                <span class="request">@for (p of parts(a.request); track $index) {<span [class.param]="p.param">{{ p.text }}</span>}</span>
                <span class="site mono">{{ host(a.url) }}</span>
              </div>
              <div class="states">
                @if (!a.learned) { <span class="badge accent">{{ 'Learns on first run' | tr }}</span> }
                @else if (a.proven) { <span class="badge">{{ 'Ready · can run on a schedule' | tr }}</span> }
                @else { <span class="badge">{{ (a.steps === 1 ? 'Ready · 1 step' : 'Ready · {n} steps') | tr: { n: a.steps } }}</span> }
                @if (a.last_run; as r) {
                  <span class="badge" [class]="'badge ' + stateClass[r.state]">{{ stateWords[r.state] | tr }}</span>
                  <span class="when muted">{{ runDate(r.when) }}</span>
                } @else { <span class="when muted">{{ 'Never run' | tr }}</span> }
              </div>
            </a>
          </li>
        }
      </ul>
    }
  `,
  styles: [`
    .tools { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; margin: 0 0 var(--space-4); max-width: 1080px; }
    .search { flex: 1; min-width: 260px; background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong);
              border-radius: var(--radius-full); padding: 9px 16px; font: 400 14px/20px var(--font-sans); }
    .filters { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip { border: 1px solid var(--border-strong); border-radius: var(--radius-full); padding: 6px 12px; font: 500 13px var(--font-sans);
            background: none; color: var(--ink-muted); cursor: pointer; white-space: nowrap; }
    .chip.on { border-color: var(--lime); color: var(--ink); }
    .chip .n { font: 500 12px var(--font-mono); opacity: .7; margin-left: 4px; }
    .sort { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--ink-muted); }
    .sort select { background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); padding: 6px 10px; }
    .top { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-4); max-width: 1080px; }
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
  query = signal('');
  filter = signal<'all' | 'alone' | 'ready' | 'new' | 'failed'>('all');
  sort = signal<'recent' | 'name'>('recent');
  filters = [{ id: 'all', label: 'All' }, { id: 'alone', label: 'Can run alone' }, { id: 'ready', label: 'Ready' },
             { id: 'new', label: 'Not learned yet' }, { id: 'failed', label: 'Last run not done' }] as const;

  private matches(a: AutomationSummary, id: string): boolean {
    switch (id) {
      case 'alone': return a.learned && a.proven;
      case 'ready': return a.learned;
      case 'new': return !a.learned;
      case 'failed': return !!a.last_run && a.last_run.state !== 'checked';
      default: return true;
    }
  }
  private searched = computed(() => {
    const words = plain(this.query()).split(/\s+/).filter(Boolean);
    return (this.items() ?? []).filter(a => {
      const text = plain(`${a.name} ${a.request} ${a.url}`);
      return words.every(w => text.includes(w));
    });
  });
  /** The automations shown: the search's words in the name, the request or the site, the filter, the order. */
  shown = computed(() => {
    const list = this.searched().filter(a => this.matches(a, this.filter()));
    return this.sort() === 'name' ? [...list].sort((x, y) => x.name.localeCompare(y.name))
                                  : [...list].sort((x, y) => (y.last_run?.when ?? '').localeCompare(x.last_run?.when ?? '') || x.name.localeCompare(y.name));
  });
  count(id: string) { return this.searched().filter(a => this.matches(a, id)).length; }
  error = signal(false);
  stateWords = STATE_WORDS; stateClass = STATE_CLASS; host = host; runDate = runDate; parts = parts;

  constructor() {
    this.api.automations().subscribe({ next: a => this.items.set(a), error: () => this.error.set(true) });
  }
}
