import { Component, inject, input, signal, effect } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api, AutomationDetail, STATE_CLASS, STATE_WORDS, host, isoDate, modelName, parts, runDate } from '../api';

const ACTIONS: Record<string, string> = {
  click: 'Click', fill: 'Type in', select: 'Choose in', check: 'Tick', uncheck: 'Untick', press: 'Press',
  extract_table: 'Read the table', extract_text: 'Read', download: 'Download', upload: 'Upload', hover: 'Point at', wait: 'Wait for',
};

@Component({
  selector: 'app-automation',
  imports: [RouterLink],
  template: `
    <a routerLink="/automations" class="back muted">← All automations</a>
    @if (notFound()) {
      <h1 class="title">This automation <em>is not here</em></h1>
      <p class="muted">It may have been renamed or removed.</p>
    } @else if (a(); as a) {
      <p class="eyebrow">Automation</p>
      <h1 class="title">{{ a.name }}</h1>
      <blockquote class="request">@for (p of parts(a.request); track $index) {<span [class.param]="p.param">{{ p.text }}</span>}</blockquote>

      <dl class="facts">
        <div><dt>Site</dt><dd class="mono">{{ host(a.url) }}</dd></div>
        <div><dt>Model</dt><dd>{{ modelName(a.profile) }}</dd></div>
        <div><dt>Values you give</dt><dd>@for (p of a.parameters; track p) { <span class="param">{{ p }}</span> } @empty { None }</dd></div>
        <div><dt>Scheduling</dt><dd>{{ a.proven ? 'Can run with no one present' : 'Needs one clean run with you first' }}</dd></div>
      </dl>

      <section>
        <p class="eyebrow">The plan</p>
        @if (a.plan; as plan) {
          <p class="muted small">Learned {{ isoDate(plan.approved) }}. ANCHOR repeats these steps with no AI.</p>
          <ol class="steps card">
            @for (s of plan.steps; track $index) {
              <li><span class="n mono">{{ $index + 1 }}</span>
                <span class="what">{{ action(s.action) }}</span>
                <span class="step mono">{{ s.description }}@if (s.value !== null) { <span class="val">=</span> @for (p of parts(s.value); track $index) {<span [class.param]="p.param" [class.val]="!p.param">{{ p.param ? p.text : '"' + p.text + '"' }}</span>} }</span></li>
            }
          </ol>
        } @else {
          <div class="card pad muted">Not learned yet. The first run plans the steps with the AI and asks you to approve them.</div>
        }
      </section>

      <section>
        <p class="eyebrow">Last runs</p>
        @if (a.runs.length) {
          <table class="runs card">
            <thead><tr><th>When</th><th>How</th><th>Result</th><th class="num">Time</th><th>What happened</th></tr></thead>
            <tbody>
              @for (r of a.runs; track r.id) {
                <tr><td>{{ runDate(r.when) }}</td>
                  <td>{{ r.mode === 'learn' ? 'Learned the plan' : 'Repeated the plan' }}</td>
                  <td><span [class]="'badge ' + stateClass[r.state]">{{ stateWords[r.state] }}</span></td>
                  <td class="num mono">{{ r.seconds }} s</td>
                  <td class="msg muted">{{ r.message }}</td></tr>
              }
            </tbody>
          </table>
        } @else { <div class="card pad muted">Never run.</div> }
      </section>

      <section class="counts">
        <div class="card pad"><span class="big">{{ a.recoveries }}</span><span class="muted">fixes when the site changed</span></div>
        <div class="card pad"><span class="big">{{ a.notes }}</span><span class="muted">notes for the planner</span></div>
        <div class="card pad"><span class="big">{{ a.confirmations }}</span><span class="muted">decisions on sensitive actions</span></div>
      </section>
    } @else { <p class="muted">Loading…</p> }
  `,
  styles: [`
    .back { display: inline-block; margin-bottom: var(--space-6); text-decoration: none; font-size: 13px; }
    .back:hover { color: var(--ink); }
    .request { margin: var(--space-4) 0 var(--space-6); font: italic 400 24px/30px var(--font-serif); color: var(--ink); max-width: 760px; }
    .facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-4); margin: 0 0 var(--space-8); max-width: 1080px; }
    .facts div { border-top: 1px solid var(--border); padding-top: var(--space-3); }
    dt { font: 500 12px/16px var(--font-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--ink-muted); }
    dd { margin: 6px 0 0; }
    section { margin-bottom: var(--space-8); max-width: 1080px; }
    .small { font-size: 13px; margin: 0 0 var(--space-3); }
    .steps { list-style: none; margin: 0; padding: var(--space-2) 0; }
    .steps li { display: grid; grid-template-columns: 40px 132px 1fr; align-items: baseline; padding: 10px var(--space-6); }
    .steps li + li { border-top: 1px solid var(--border); }
    .n { color: var(--ink-muted); font-size: 12px; }
    .what { color: var(--ink-muted); font-size: 13px; }
    .step { font-size: 14px; } .val { color: var(--accent); margin-left: 6px; }
    .pad { padding: var(--space-4) var(--space-6); }
    .runs { width: 100%; border-collapse: separate; border-spacing: 0; overflow: hidden; }
    th { text-align: left; font: 500 12px/16px var(--font-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--ink-muted);
         padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border); }
    td { padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border); font-size: 14px; }
    tr:last-child td { border-bottom: 0; }
    .num { text-align: right; } .msg { max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .counts { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); }
    .counts .pad { display: grid; gap: 4px; }
    .big { font: 600 32px/36px var(--font-sans); letter-spacing: -0.03em; }
  `],
})
export class AutomationPage {
  private api = inject(Api);
  name = input.required<string>();
  a = signal<AutomationDetail | null>(null);
  notFound = signal(false);
  stateWords = STATE_WORDS; stateClass = STATE_CLASS; host = host; runDate = runDate; parts = parts; modelName = modelName; isoDate = isoDate;
  action = (a: string) => ACTIONS[a] ?? a;

  constructor() {
    effect(() => {
      const name = this.name();
      this.a.set(null); this.notFound.set(false);
      this.api.automation(name).subscribe({ next: d => this.a.set(d), error: () => this.notFound.set(true) });
    });
  }
}
