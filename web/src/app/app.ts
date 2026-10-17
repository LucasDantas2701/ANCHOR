import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { Api, takeCodeFromAddress } from './api';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <header class="top">
      <a routerLink="/automations" class="brand" aria-label="ANCHOR, home">
        <img [src]="theme() === 'dark' ? '/brand/anchor-wordmark-on-dark.svg' : '/brand/anchor-wordmark-on-light.svg'" alt="ANCHOR" height="18">
      </a>
      <div class="right">
        <button class="theme" type="button" (click)="toggleTheme()" [attr.aria-label]="'Switch to ' + (theme() === 'dark' ? 'light' : 'dark') + ' theme'">
          {{ theme() === 'dark' ? 'Light' : 'Dark' }} theme
        </button>
        <a class="btn" [href]="docs()" target="_blank" rel="noopener noreferrer">Docs <span aria-hidden="true">↗</span></a>
      </div>
    </header>
    <div class="body">
      <nav class="side" aria-label="Main">
        <a routerLink="/automations" routerLinkActive="on">Automations</a>
        <a routerLink="/run" routerLinkActive="on">Run a request</a>
        <a routerLink="/schedules" routerLinkActive="on">Schedules</a>
        <a routerLink="/settings" routerLinkActive="on">Settings</a>
        <span class="version mono">{{ version() }}</span>
      </nav>
      <main><router-outlet /></main>
    </div>
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
    .side a.on { color: var(--ink); background: var(--surface-raised); box-shadow: inset 0 0 0 1px var(--border); }
    .version { margin-top: auto; padding: 0 var(--space-4); font-size: 12px; color: var(--ink-muted); }
    main { overflow: auto; padding: var(--space-12) var(--space-12) var(--space-8); }
  `],
})
export class App implements OnInit {
  private api = inject(Api);
  theme = signal<'dark' | 'light'>((localStorage.getItem('anchor-theme') as 'dark' | 'light') || 'dark');
  docs = signal('https://github.com/LucasDantas2701/ANCHOR#readme');
  version = signal('');

  constructor() { takeCodeFromAddress(); }

  ngOnInit() {
    document.documentElement.dataset['theme'] = this.theme();
    this.api.info().subscribe({ next: i => { this.docs.set(i.docs); this.version.set(`version ${i.version}`); }, error: () => {} });
  }

  toggleTheme() {
    this.theme.set(this.theme() === 'dark' ? 'light' : 'dark');
    document.documentElement.dataset['theme'] = this.theme();
    try { localStorage.setItem('anchor-theme', this.theme()); } catch { /* a preference only */ }
  }
}
