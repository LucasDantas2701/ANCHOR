import { Component, OnDestroy, inject, output, signal } from '@angular/core';

import { Api, SetupStatus } from './api';

/** The first opening, when something is missing: Ollama, the model, the browser ANCHOR drives. */
@Component({
  selector: 'app-setup',
  template: `
    <div class="backdrop"></div>
    <section class="panel" role="dialog" aria-modal="true" aria-labelledby="setup-title">
      <p class="eyebrow">Getting ready</p>
      <h2 id="setup-title" class="title">Three things, <em>once</em></h2>
      <p class="muted">ANCHOR runs everything on this computer. Before the first run, it needs these three things. You do this only once.</p>
      @if (s(); as st) {
        <ol class="items">
          <li [class.ok]="st.ollama">
            <div><b>Ollama</b>, which runs the AI on this computer.
              @if (st.ollama) { <span class="done">Running.</span> }
              @else { <span class="muted">Not found. Install it from <a [href]="st.ollama_download" target="_blank" rel="noopener noreferrer">ollama.com/download</a>,
                open it, and then check again.</span> }</div>
            @if (!st.ollama) { <button class="btn" type="button" (click)="load()">Check again</button> }
          </li>
          <li class="models" [class.ok]="st.model_ready">
            <div><b>An AI model</b>: at least one. The small one is enough to start; the medium one is more careful and slower.</div>
            @for (m of st.models ?? []; track m.profile) {
              <div class="model">
                <div><b>{{ m.label }}</b>&nbsp;<span class="muted">{{ m.size }}</span>
                  @if (m.ready) { <span class="done">Downloaded.</span> }
                  @else if (m.download.state === 'running') { <span class="bar"><i [style.width.%]="m.download.percent"></i></span>
                    <span class="muted small">{{ m.download.message }} {{ m.download.percent }}%</span> }
                  @else if (m.download.state === 'failed') { <span class="err">{{ m.download.message }}</span> }</div>
                @if (!m.ready && m.download.state !== 'running') {
                  <button class="btn" [class.primary]="!st.model_ready" type="button" [disabled]="!st.ollama" (click)="model(m.profile)">Download</button> }
              </div>
            }
          </li>
          <li [class.ok]="st.browser_ready">
            <div><b>The browser</b> ANCHOR drives (Chromium), about 150 MB.
              @if (st.browser_ready) { <span class="done">Downloaded.</span> }
              @else if (st.browser_download?.state === 'running') { <span class="bar"><i [style.width.%]="st.browser_download?.percent"></i></span>
                <span class="muted small">{{ st.browser_download?.percent }}%</span> }
              @else if (st.browser_download?.state === 'failed') { <span class="err">{{ st.browser_download?.message }}</span> }</div>
            @if (!st.browser_ready && st.browser_download?.state !== 'running') {
              <button class="btn primary" type="button" (click)="browser()">Download the browser</button> }
          </li>
        </ol>
        <footer>
          <button class="btn primary" type="button" [disabled]="!st.ready" (click)="done.emit()">{{ st.ready ? 'Start using ANCHOR' : 'Waiting for the three' }}</button>
        </footer>
      }
    </section>
  `,
  styles: [`
    :host { position: fixed; inset: 0; z-index: 70; display: grid; place-items: center; }
    .backdrop { position: absolute; inset: 0; background: rgba(4, 3, 8, .8); }
    .panel { position: relative; width: min(680px, 92vw); padding: var(--space-8); background: var(--surface-raised); border: 1px solid var(--border);
             border-radius: var(--radius-lg); display: grid; gap: var(--space-3); }
    .title { margin: 0; } p { margin: 0; }
    .items { list-style: none; margin: var(--space-3) 0 0; padding: 0; display: grid; gap: var(--space-3); }
    .items li { display: flex; justify-content: space-between; align-items: center; gap: var(--space-4); padding: var(--space-4);
                border: 1px solid var(--border); border-radius: var(--radius-md); }
    .items li.ok { border-color: var(--checked); }
    .items li.models { display: grid; gap: var(--space-3); }
    .model { display: flex; justify-content: space-between; align-items: center; gap: var(--space-4); padding-top: var(--space-3); border-top: 1px solid var(--border); }
    .items li > div { display: block; font-size: 14px; line-height: 1.5; }
    .done { display: block; margin-top: 4px; color: var(--checked); font-weight: 600; }
    .err { display: block; margin-top: 4px; color: var(--refused); font-size: 13px; }
    .small { display: block; margin-top: 4px; font-size: 12px; }
    .items li > div > .muted:not(.mono) { display: block; margin-top: 4px; }
    .bar { display: block; margin-top: 8px; height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; width: 280px; }
    .bar i { display: block; height: 100%; background: var(--lime); }
    footer { display: flex; justify-content: flex-end; margin-top: var(--space-3); }
    .btn:disabled { opacity: .5; }
  `],
})
export class Setup implements OnDestroy {
  private api = inject(Api);
  done = output<void>();
  s = signal<SetupStatus | null>(null);
  private timer = setInterval(() => this.load(), 1500);
  constructor() { this.load(); }
  ngOnDestroy() { clearInterval(this.timer); }
  load() { this.api.setup().subscribe({ next: s => this.s.set(s), error: () => {} }); }
  model(profile: string) { this.api.downloadModel(profile).subscribe({ next: () => this.load(), error: () => this.load() }); }
  browser() { this.api.downloadBrowser().subscribe({ next: () => this.load(), error: () => this.load() }); }
}
