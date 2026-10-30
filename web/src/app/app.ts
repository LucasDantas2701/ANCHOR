import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ACTIVE, Api, RunListItem, Runs, takeCodeFromAddress } from './api';
import { Guide, guideOnStart } from './guide';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Guide],
  template: `
    <header class="top">
      <a routerLink="/automations" class="brand" aria-label="ANCHOR, home">
        <img [src]="theme() === 'dark' ? '/brand/anchor-wordmark-on-dark.svg' : '/brand/anchor-wordmark-on-light.svg'" alt="ANCHOR" height="18">
      </a>
      <div class="right">
        <button class="theme" type="button" (click)="toggleTheme()" [attr.aria-label]="'Switch to ' + (theme() === 'dark' ? 'light' : 'dark') + ' theme'">
          {{ theme() === 'dark' ? 'Light' : 'Dark' }} theme
        </button>
        <button class="theme" type="button" (click)="guide.set(true)">Guide</button>
        <a class="btn" [href]="docs()" target="_blank" rel="noopener noreferrer">Docs <span aria-hidden="true">↗</span></a>
      </div>
    </header>
    <div class="body">
      <nav class="side" aria-label="Main">
        <a routerLink="/automations" routerLinkActive="on">Automations</a>
        <a routerLink="/run" routerLinkActive="on">Run a request</a>
        <a routerLink="/runs" routerLinkActive="on" [routerLinkActiveOptions]="{ exact: true }">Runs@if (queued() + (current() ? 1 : 0) > 0) { <span class="pill">{{ queued() + (current() ? 1 : 0) }}</span> }</a>
        <a routerLink="/schedules" routerLinkActive="on">Schedules</a>
        <a routerLink="/settings" routerLinkActive="on">Settings</a>
        @if (current(); as c) {
          <a class="now" [routerLink]="['/runs', c.id]">
            <span class="eyebrow">{{ c.state === 'waiting' ? 'Waiting for you' : 'Running now' }}</span>
            <span class="what">{{ c.kind === 'automation' ? c.title : 'A request' }}</span>
            @if (queued() > 0) { <span class="muted">+ {{ queued() }} waiting their turn</span> }
          </a>
        }
        <span class="version mono">{{ version() }}</span>
      </nav>
      <main><router-outlet /></main>
    </div>
    @if (guide()) { <app-guide (close)="guide.set(false)" /> }
  `,
  styles: [`
    :host { display: grid; grid-template-rows: 64px 1fr; height: 100vh; }
    .top { display: flex; align-items: center; justify-content: space-between; padding: 0 var(--space-8);
           border-bottom: 1px solid var(--border); background: var(--surface-page); }
    .brand { display: flex; } .brand img { display: block; }
    .right { display: flex; align-items: center; gap: var(--space-4); }
    .theme { background: none; border: 0; color: var(--ink-muted); font: 500 13px var(--font-sans); cursor: pointer; padding: 8px; }
    .theme:hover { color: var(--ink); }
    .body { display: grid; grid-template-columns: 232px 1fr; min-height: 0; }
    .side { background: var(--surface-sunken); border-right: 1px solid var(--border); padding: var(--space-6) var(--space-3);
            display: flex; flex-direction: column; gap: 2px; }
    .side a { color: var(--ink-muted); text-decoration: none; padding: 10px var(--space-4); border-radius: var(--radius-full);
              font: 500 14px/20px var(--font-sans); }
    .side a:hover { color: var(--ink); background: var(--surface-raised); }
    .side .pill { margin-left: 8px; display: inline-block; min-width: 18px; padding: 0 6px; border-radius: 9px; background: var(--lime); color: #0C0A12; font: 600 11px/18px var(--font-mono); text-align: center; }
    .side a.on { color: var(--ink); background: var(--surface-raised); box-shadow: inset 0 0 0 1px var(--border); }
    .now { margin-top: auto; display: grid; gap: 2px; padding: var(--space-3) var(--space-4) !important; border-radius: var(--radius-md) !important;
           border: 1px solid var(--border); background: var(--surface-raised); }
    .now .eyebrow { margin: 0; color: var(--accent); } .now .eyebrow::before { display: none; }
    .now .what { color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .now .muted { font-size: 12px; }
    .now + .version { margin-top: var(--space-3); }
    .version { margin-top: auto; padding: 0 var(--space-4); font-size: 12px; color: var(--ink-muted); }
    main { overflow: auto; padding: var(--space-12) var(--space-12) var(--space-8); }
  `],
})
export class App implements OnInit {
  private api = inject(Api);
  theme = signal<'dark' | 'light'>((localStorage.getItem('anchor-theme') as 'dark' | 'light') || 'dark');
  docs = signal('https://github.com/LucasDantas2701/ANCHOR#readme');
  version = signal('');
  guide = signal(guideOnStart());
  private runs = inject(Runs);
  current = signal<RunListItem | null>(null);
  queued = signal(0);

  constructor() { takeCodeFromAddress(); }

  ngOnInit() {
    document.documentElement.dataset['theme'] = this.theme();
    this.api.info().subscribe({ next: i => { this.docs.set(i.docs); this.version.set(`version ${i.version}`); }, error: () => {} });
    this.watchRuns();
  }

  /** What is running now, every few seconds, for the sidebar. */
  private watchRuns() {
    this.runs.list().subscribe({
      next: list => {
        this.current.set(list.find(j => j.state === 'running' || j.state === 'waiting') ?? null);
        this.queued.set(list.filter(j => j.state === 'queued').length);
      },
      error: () => setTimeout(() => this.watchRuns(), 5000),
      complete: () => setTimeout(() => this.watchRuns(), 2000),
    });
  }

  toggleTheme() {
    this.theme.set(this.theme() === 'dark' ? 'light' : 'dark');
    document.documentElement.dataset['theme'] = this.theme();
    try { localStorage.setItem('anchor-theme', this.theme()); } catch { /* a preference only */ }
  }
}
