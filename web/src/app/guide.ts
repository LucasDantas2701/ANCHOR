import { Component, HostListener, output, signal } from '@angular/core';

const KEY = 'anchor-guide';

/** Whether the guide opens by itself (the first time, and until the person turns it off). */
export function guideOnStart(): boolean {
  try { return localStorage.getItem(KEY) !== 'off'; } catch { return true; }
}

/** A short guide to ANCHOR: what it does, where things are, what happens during a run, which model. */
@Component({
  selector: 'app-guide',
  template: `
    <div class="backdrop" (click)="done()"></div>
    <section class="panel" role="dialog" aria-modal="true" aria-labelledby="guide-title">
      <div class="steps" aria-hidden="true">
        @for (s of pages; track $index) { <span [class.on]="$index === page()"></span> }
      </div>
      @switch (page()) {
        @case (0) {
          <p class="eyebrow">Welcome</p>
          <h2 id="guide-title" class="title">Web work, done <em>and checked</em></h2>
          <p>Write what you want done on a website, as you would ask a colleague: <span class="quote">“Register Ana Souza and save the record”</span>.</p>
          <ol class="flow">
            <li><strong>The AI plans</strong> the steps. It runs on this computer.</li>
            <li><strong>ANCHOR does them</strong> in a browser, one by one.</li>
            <li><strong>Every step is checked</strong>: if something did not happen, ANCHOR says so instead of pretending.</li>
          </ol>
          <p class="muted">Nothing leaves your computer: not your requests, not the pages, not your logins.</p>
        }
        @case (1) {
          <p class="eyebrow">Where things are</p>
          <h2 id="guide-title" class="title">Four places, <em>one idea each</em></h2>
          <dl class="places">
            <div><dt>Automations</dt><dd>Tasks you run often. ANCHOR learns them once, then repeats the steps with one click, without the AI. Create one with New automation, or save a request that worked.</dd></div>
            <div><dt>Run a request</dt><dd>Something you need done once. Write it, pick the page and the model, and run it. Not sure it will work? "See the plan first" shows the steps without doing any.</dd></div>
            <div><dt>Schedules</dt><dd>Automations that run by themselves at a set time, while ANCHOR is open. Coming soon.</dd></div>
            <div><dt>Settings</dt><dd>Your preferences. Coming soon.</dd></div>
            <div><dt>Docs</dt><dd>The full documentation, in your browser, from the top right of every screen.</dd></div>
          </dl>
        }
        @case (2) {
          <p class="eyebrow">While it runs</p>
          <h2 id="guide-title" class="title">You can always <em>see and stop</em></h2>
          <dl class="places">
            <div><dt>Watch it run</dt><dd>The browser, live, beside the steps as they happen.</dd></div>
            <div><dt>Waiting for you</dt><dd>Before anything sensitive (saving, sending, deleting, paying), ANCHOR asks. It also asks when two things look alike, and when a page needs you to log in: then the live view opens, and you click and type on it yourself.</dd></div>
            <div><dt>Stop</dt><dd>Stops at the next step. Nothing else is done after it.</dd></div>
            <div><dt>Try again</dt><dd>After a run that was not done, opens it again with what you wrote, to change and retry.</dd></div>
          </dl>
          <p class="note">Never write a password in a request. When a page needs a login, ANCHOR waits for you to do it.</p>
        }
        @case (3) {
          <p class="eyebrow">Which model</p>
          <h2 id="guide-title" class="title">Start small, <em>go medium when needed</em></h2>
          <div class="models">
            <div class="model card">
              <p class="name">Small <span class="mono muted">Qwen 3.5 4B</span></p>
              <p>Faster: about half the time of the medium one. Good for simple pages and short requests.</p>
              <p class="pick">Start here.</p>
            </div>
            <div class="model card">
              <p class="name">Medium <span class="mono muted">Qwen 3.5 9B</span></p>
              <p>More careful with big, busy pages and long requests, but slower: on a 4 GB graphics card, around a minute for each plan.</p>
              <p class="pick">Use it when the small one gets it wrong.</p>
            </div>
          </div>
          <p class="muted">Saved automations repeat their steps without the AI, so the model only matters when one is learned or fixed.</p>
        }
      }
      <footer>
        <label class="check"><input type="checkbox" [checked]="onStart()" (change)="toggle($event)"> Show this guide when ANCHOR opens</label>
        <div class="nav">
          @if (page() > 0) { <button class="btn" type="button" (click)="page.set(page() - 1)">Back</button> }
          @else { <button class="btn quiet" type="button" (click)="done()">Skip</button> }
          @if (page() < pages.length - 1) { <button class="btn primary" type="button" (click)="page.set(page() + 1)">Next</button> }
          @else { <button class="btn primary" type="button" (click)="done()">Got it</button> }
        </div>
      </footer>
    </section>
  `,
  styles: [`
    :host { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; }
    .backdrop { position: absolute; inset: 0; background: rgba(4, 3, 8, .72); backdrop-filter: blur(2px); }
    .panel { position: relative; width: min(680px, 92vw); max-height: 90vh; overflow: auto; padding: var(--space-8);
             background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-raised); }
    .steps { display: flex; gap: 6px; margin-bottom: var(--space-6); }
    .steps span { width: 24px; height: 4px; border-radius: 2px; background: var(--border); }
    .steps span.on { background: var(--lime); }
    .title { margin-bottom: var(--space-4); }
    p { margin: 0 0 var(--space-3); }
    .quote { font: italic 400 1.08em var(--font-serif); color: var(--accent); }
    .flow { margin: var(--space-4) 0; padding-left: 1.2em; display: grid; gap: var(--space-2); }
    .places { margin: var(--space-2) 0 var(--space-3); display: grid; gap: var(--space-3); }
    .places div { display: grid; grid-template-columns: 150px 1fr; gap: var(--space-4); padding-top: var(--space-3); border-top: 1px solid var(--border); }
    dt { font-weight: 600; } dd { margin: 0; color: var(--ink-muted); }
    .note { color: var(--waiting); }
    .models { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); margin: var(--space-2) 0 var(--space-4); }
    .model { padding: var(--space-4); background: var(--surface-page); }
    .model .name { font-weight: 600; } .model .name .mono { font-size: 12px; margin-left: 6px; }
    .model p:not(.name) { color: var(--ink-muted); font-size: 14px; }
    .model .pick { color: var(--checked) !important; margin: 0; }
    footer { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); margin-top: var(--space-6);
             padding-top: var(--space-4); border-top: 1px solid var(--border); flex-wrap: wrap; }
    .check { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--ink-muted); }
    .nav { display: flex; gap: var(--space-3); }
    .btn.quiet { border-color: transparent; color: var(--ink-muted); }
    @media (max-width: 560px) { .models { grid-template-columns: 1fr; } .places div { grid-template-columns: 1fr; gap: 2px; } }
  `],
})
export class Guide {
  close = output<void>();
  pages = [0, 1, 2, 3];
  page = signal(0);
  onStart = signal(guideOnStart());

  @HostListener('document:keydown.escape') onEscape() { this.done(); }

  toggle(e: Event) {
    const on = (e.target as HTMLInputElement).checked;
    this.onStart.set(on);
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch { /* a preference only */ }
  }

  done() { this.close.emit(); }
}
