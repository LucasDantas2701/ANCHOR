import { TrPipe, tr } from '../i18n';
import { Component, inject, input, signal, effect } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { Api, AutomationDetail, Choice, Decision, Fix, Note, PlanStep, Profile, Runs, SheetCheck, STATE_CLASS, STATE_WORDS, apiError, host, isoDate, modelName, parts, runDate } from '../api';

const ACTIONS: Record<string, string> = {
  click: 'Click', fill: 'Type in', select: 'Choose in', check: 'Tick', uncheck: 'Untick', press: 'Press',
  extract_table: 'Read the table', extract_text: 'Read', download: 'Download', upload: 'Upload', hover: 'Point at', wait: 'Wait for',
};

@Component({
  selector: 'app-automation',
  imports: [RouterLink, FormsModule, TrPipe],
  template: `
    <a routerLink="/automations" class="back muted">{{ '← All automations' | tr }}</a>
    @if (notFound()) {
      <h1 class="title">{{ 'This automation' | tr }} <em>{{ 'is not here' | tr }}</em></h1>
      <p class="muted">{{ 'It may have been renamed or removed.' | tr }}</p>
    } @else if (a(); as a) {
      <p class="eyebrow">{{ 'Automation' | tr }}</p>
      <h1 class="title">{{ a.name }}</h1>
      <blockquote class="request">@for (p of parts(a.request); track $index) {<span [class.param]="p.param">{{ p.text }}</span>}</blockquote>

      <form class="card runbox" (ngSubmit)="run(a)">
        @for (p of a.parameters; track p) {
          <div class="field"><label [for]="'v-' + p">{{ p }}</label>
            <input [id]="'v-' + p" [name]="'v-' + p" [(ngModel)]="values[p]" autocomplete="off"></div>
        }
        <div class="go">
          <button class="btn primary" type="submit" [disabled]="busy()">{{ (busy() ? 'Starting…' : (a.learned ? 'Run' : 'Run and learn')) | tr }}</button>
          <label class="check window"><input type="checkbox" name="show" [(ngModel)]="show"> {{ 'Also open the browser in its own window' | tr }}</label>
          <button class="btn" type="button" (click)="logIn(a)" [title]="'Opens this automation’s browser so you can log in once; its runs keep the session' | tr">{{ 'Log in to this site' | tr }}</button>
          <details class="more"><summary class="muted">{{ 'More options' | tr }}</summary>
            <label class="check"><input type="checkbox" name="relearn" [(ngModel)]="relearn"> {{ 'Learn the plan again with the AI' | tr }}</label>
            <label class="check"><input type="checkbox" name="fresh" [(ngModel)]="fresh"> {{ 'Use a clean browser (no saved logins)' | tr }}</label>
            <label class="check"><input type="checkbox" name="shot" [(ngModel)]="shot"> {{ 'Include a screenshot of the page at the end' | tr }}</label>
          </details>
        </div>
        @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
      </form>

      @if (a.parameters.length) {
        <div class="card sheet">
          <div class="sheet-head">
            <div><p class="eyebrow">{{ 'Run for each row of a spreadsheet' | tr }}</p>
              <p class="muted small">{{ 'A CSV or Excel (.xlsx) file whose first row names the columns: {cols}. One run per row, one after the other.' | tr: { cols: a.parameters.join(', ') } }}</p></div>
            <label class="btn">{{ 'Choose a file' | tr }}<input type="file" accept=".csv,.xlsx" hidden (change)="pickSheet(a, $event)"></label>
          </div>
          @if (sheetError()) { <p class="error" role="alert">{{ sheetError() }}</p> }
          @if (sheet(); as s) {
            <p class="small"><b>{{ sheetName() }}</b> · {{ (s.rows === 1 ? '1 row' : '{n} rows') | tr: { n: s.rows } }}
              @if (s.extra.length) { <span class="muted">{{ ' · not used: {cols}' | tr: { cols: s.extra.join(', ') } }}</span> }</p>
            @if (s.missing.length) { <p class="warn">{{ 'The spreadsheet has no column for: {cols}. Name a column exactly like that.' | tr: { cols: s.missing.join(', ') } }}</p> }
            @if (s.blank_rows.length) { <p class="warn">{{ 'These rows have an empty value: {rows}. Fill them in, or remove them.' | tr: { rows: s.blank_rows.slice(0, 10).join(', ') + (s.blank_rows.length > 10 ? '…' : '') } }}</p> }
            @if (s.too_many) { <p class="warn">{{ 'A spreadsheet run has at most 500 rows: split it in parts.' | tr }}</p> }
            <div class="scroll"><table class="preview">
              <thead><tr><th>#</th>@for (p of s.parameters; track p) { <th>{{ p }}</th> }</tr></thead>
              <tbody>@for (row of s.preview; track $index) { <tr><td class="muted">{{ $index + 1 }}</td>@for (p of s.parameters; track p) { <td class="mono">{{ row[p] }}</td> }</tr> }</tbody>
            </table></div>
            @if (s.rows > s.preview.length) { <p class="muted small">{{ 'and {n} more.' | tr: { n: s.rows - s.preview.length } }}</p> }
            <button class="btn primary" type="button" [disabled]="!sheetOk(s) || busy()" (click)="runSheet(a, s)">{{ (s.rows === 1 ? 'Run 1 row' : 'Run {n} rows') | tr: { n: s.rows } }}</button>
          }
        </div>
      }

      <dl class="facts">
        <div><dt>{{ 'Site' | tr }}</dt><dd class="mono">{{ host(a.url) }}</dd></div>
        <div><dt>{{ 'Model' | tr }}</dt><dd>{{ modelName(a.profile) | tr }}</dd></div>
        <div><dt>{{ 'Values you give' | tr }}</dt><dd>@for (p of a.parameters; track p) { <span class="param">{{ p }}</span> } @empty { None }</dd></div>
        <div><dt>{{ 'Scheduling' | tr }}</dt><dd>@if (a.proven) { {{ 'Can run with no one present' | tr }} ·
          <a [routerLink]="['/schedules']" [queryParams]="{ automation: a.name }">{{ 'Schedule this' | tr }}</a> } @else { {{ 'Needs one clean run with you first' | tr }} }</dd></div>
        <div><dt>{{ 'Last run' | tr }}</dt><dd>@if (a.has_log) { <button class="linkish" type="button" (click)="downloadLog(a)">{{ 'Download its log' | tr }}</button> }
          @else { {{ 'No run kept yet' | tr }} }</dd></div>
      </dl>

      <nav class="tabs" role="tablist" [attr.aria-label]="'This automation' | tr">
        @for (t of tabs; track t.id) {
          <button type="button" role="tab" class="tab" [class.on]="tab() === t.id" [attr.aria-selected]="tab() === t.id" (click)="open(t.id, a)">
            {{ t.label | tr }}@if (count(a, t.id) !== null) { <span class="count">{{ count(a, t.id) }}</span> }
          </button>
        }
      </nav>

      @if (tab() === 'overview') {
      <section>
        <p class="eyebrow">{{ 'The plan' | tr }}</p>
        @if (a.plan; as plan) {
          <p class="muted small">{{ 'Learned {date}. ANCHOR repeats these steps with no AI.' | tr: { date: isoDate(plan.approved) } }}</p>
          <ol class="steps card">
            @for (s of plan.steps; track $index) {
              <li><span class="n mono">{{ $index + 1 }}</span>
                <span class="what">{{ action(s.action) }}</span>
                <span class="step mono">{{ s.description }}@if (s.value !== null) { <span class="val">=</span> @for (p of parts(s.value); track $index) {<span [class.param]="p.param" [class.val]="!p.param">{{ p.param ? p.text : '"' + p.text + '"' }}</span>} }</span></li>
            }
          </ol>
        } @else {
          <div class="card pad muted">{{ 'Not learned yet. The first run plans the steps with the AI and asks you to approve them.' | tr }}</div>
        }
      </section>

      <section>
        <p class="eyebrow">{{ 'Last runs' | tr }}</p>
        @if (a.runs.length) {
          <table class="runs card">
            <thead><tr><th>{{ 'When' | tr }}</th><th>{{ 'How' | tr }}</th><th>{{ 'Result' | tr }}</th><th class="num">{{ 'Time' | tr }}</th><th>{{ 'What happened' | tr }}</th></tr></thead>
            <tbody>
              @for (r of a.runs; track r.id) {
                <tr><td>{{ runDate(r.when) }}</td>
                  <td>{{ (r.mode === 'learn' ? 'Learned the plan' : 'Repeated the plan') | tr }}</td>
                  <td><span [class]="'badge ' + stateClass[r.state]">{{ stateWords[r.state] | tr }}</span></td>
                  <td class="num mono">{{ r.seconds }} s</td>
                  <td class="msg muted">{{ r.message }}</td></tr>
              }
            </tbody>
          </table>
        } @else { <div class="card pad muted">{{ 'Never run.' | tr }}</div> }
      </section>

      }

      @if (tab() === 'fixes') {
        <section>
          <p class="muted small">{{ 'When the site changed and a step stopped working, ANCHOR fixed the plan, or asked you which element was right. Undoing a fix brings the step back as it was.' | tr }}</p>
          @for (f of fixes(); track f.number) {
            <article class="card pad item" [class.dim]="f.undone">
              <header><span class="mono muted">#{{ f.number }} · {{ isoDate(f.date) }}</span>
                <span class="grow"></span>
                @if (f.undone) { <span class="badge">{{ 'Undone' | tr }}</span> }
                @else { <button class="btn small" type="button" (click)="undo(a, f)">{{ 'Undo' | tr }}</button> }</header>
              @if (f.method === 'replan') {
                <p><span class="lab">{{ 'Step that stopped working' | tr }}</span> <span class="mono">{{ stepText(f.failed) }}</span></p>
                @if (f.reason) { <p><span class="lab">{{ 'Why' | tr }}</span> {{ f.reason }}</p> }
                <p><span class="lab">{{ 'Replaced by' | tr }}</span> @for (r of f.replaced_by ?? []; track $index) { <span class="mono">{{ stepText(r) }}</span>@if (!$last) {; } } @empty { {{ 'nothing' | tr }} }</p>
                <p class="muted small">{{ (f.effect_confirmed ? 'The new step had its effect.' : 'The effect of the new step was not confirmed.') | tr }}</p>
              } @else {
                <p>{{ 'You chose the element for' | tr }} <span class="mono">{{ f.step?.description }}</span>.</p>
              }
            </article>
          } @empty { <div class="card pad muted">{{ 'No fixes: the site has not changed under this automation.' | tr }}</div> }
        </section>
      }

      @if (tab() === 'notes') {
        <section>
          <p class="muted small">{{ 'Notes tell the AI something about this site when it plans (for example, "The reports are inside the Portal menu"). The {n} most recent go to the AI; they count from the next time it plans.' | tr: { n: notesSent } }}</p>
          <form class="card pad noteform" (ngSubmit)="addNote(a)">
            <textarea name="newNote" rows="2" maxlength="500" [(ngModel)]="newNote" [placeholder]="'Write a note about this site' | tr"></textarea>
            <button class="btn primary" type="submit" [disabled]="!newNote.trim()">{{ 'Add note' | tr }}</button>
          </form>
          @for (n of notes(); track n.number) {
            <article class="card pad item">
              <header><span class="mono muted">#{{ n.number }} · {{ isoDate(n.edited || n.date) }}</span>
                @if (n.sent) { <span class="badge ok">{{ 'Sent to the AI' | tr }}</span> }
                <span class="grow"></span>
                @if (editing() !== n.number) {
                  <button class="btn small" type="button" (click)="startEdit(n)">{{ 'Edit' | tr }}</button>
                  <button class="btn small" type="button" (click)="removeNote(a, n)">{{ 'Remove' | tr }}</button>
                }</header>
              @if (editing() === n.number) {
                <form class="noteform" (ngSubmit)="saveEdit(a, n)">
                  <textarea name="editNote" rows="2" maxlength="500" [(ngModel)]="editText"></textarea>
                  <button class="btn primary small" type="submit" [disabled]="!editText.trim()">{{ 'Save' | tr }}</button>
                  <button class="btn small" type="button" (click)="editing.set(null)">{{ 'Cancel' | tr }}</button>
                </form>
              } @else { <p>{{ n.text }}</p> }
            </article>
          } @empty { <div class="card pad muted">{{ 'No notes yet.' | tr }}</div> }
        </section>
      }

      @if (tab() === 'decisions') {
        <section>
          <p class="muted small">{{ 'What you allowed or denied when this automation reached a sensitive action. ANCHOR does it again without asking; forget one to be asked again next time.' | tr }}</p>
          @if (decisions().length) {
            <table class="runs card">
              <thead><tr><th>{{ 'Decision' | tr }}</th><th>{{ 'Action' | tr }}</th><th>{{ 'On' | tr }}</th><th>{{ 'When' | tr }}</th><th></th></tr></thead>
              <tbody>
                @for (d of decisions(); track d.number) {
                  <tr><td><span [class]="'badge ' + (d.decision === 'allowed' ? 'ok' : 'no')">{{ (d.decision === 'allowed' ? 'Allowed' : 'Denied') | tr }}</span></td>
                    <td>{{ category(d.category) }}</td><td class="mono msg">{{ d.element }}</td><td class="muted">{{ isoDate(d.date) }}</td>
                    <td class="num"><button class="btn small" type="button" (click)="forgetDecision(a, d)">{{ 'Forget' | tr }}</button></td></tr>
                }
              </tbody>
            </table>
          } @else { <div class="card pad muted">{{ 'No decisions: this automation has not reached a sensitive action, or asks every time.' | tr }}</div> }
        </section>
      }

      @if (tab() === 'choices') {
        <section>
          <p class="muted small">{{ 'When ANCHOR was not sure which element a step meant, you chose one, and it was remembered. Forget a choice if it is wrong: the next run asks again.' | tr }}</p>
          @for (c of choices(); track c.key) {
            <article class="card pad item">
              <header><span class="mono">{{ c.description }}</span><span class="grow"></span>
                <button class="btn small" type="button" (click)="forgetChoice(a, c)">{{ 'Forget' | tr }}</button></header>
              <p>{{ 'is the element' | tr }} <span class="mono">“{{ c.element || ('without text' | tr) }}”</span> <span class="muted">{{ (c.uses === 1 ? ' · used once' : ' · used {n} times') | tr: { n: c.uses } }}@if (c.last_used) {{{ ', last {date}' | tr: { date: isoDate(c.last_used) } }}}</span></p>
            </article>
          } @empty { <div class="card pad muted">{{ 'No remembered choices.' | tr }}</div> }
        </section>
      }

      @if (tab() === 'settings') {
        <section>
          <form class="card pad settings" (ngSubmit)="save(a)">
            <div class="field wide"><label for="s-request">{{ 'Request' | tr }}</label>
              <textarea id="s-request" name="sRequest" rows="3" [(ngModel)]="sRequest"></textarea></div>
            <div class="field wide"><label for="s-url">{{ 'Page' | tr }}</label><input id="s-url" name="sUrl" [(ngModel)]="sUrl"></div>
            <div class="field"><label for="s-profile">{{ 'Model' | tr }}</label>
              <select id="s-profile" name="sProfile" [(ngModel)]="sProfile">
                @for (p of profiles(); track p.name) { <option [value]="p.name">{{ p.label }}</option> }
              </select></div>
            @if (relearns(a)) { <p class="warn">{{ 'Changing the request or the page makes ANCHOR learn the plan again on the next run: the plan it has was checked for the old one.' | tr }}</p> }
            <div class="go"><button class="btn primary" type="submit" [disabled]="!changed(a)">{{ 'Save changes' | tr }}</button>
              @if (saved()) { <span class="muted small">{{ saved() }}</span> }</div>
          </form>

          <div class="card pad danger">
            <p class="eyebrow">{{ 'Delete this automation' | tr }}</p>
            <p class="muted small">{{ 'This deletes it for good: its plan, its history, its notes, decisions and choices, and its browser with the saved logins. It cannot be undone.' | tr }}</p>
            <div class="go">
              <input name="confirmName" [(ngModel)]="confirmName" [placeholder]="'Type ' + a.name + ' to confirm'" autocomplete="off">
              <button class="btn dangerbtn" type="button" [disabled]="confirmName !== a.name" (click)="remove(a)">{{ 'Delete for good' | tr }}</button>
            </div>
          </div>
        </section>
      }
      @if (actionError()) { <p class="error" role="alert">{{ actionError() }}</p> }
    } @else { <p class="muted">{{ 'Loading…' | tr }}</p> }
  `,
  styles: [`
    .back { display: inline-block; margin-bottom: var(--space-6); text-decoration: none; font-size: 13px; }
    .back:hover { color: var(--ink); }
    .request { margin: var(--space-4) 0 var(--space-6); font: italic 400 24px/30px var(--font-serif); color: var(--ink); max-width: 760px; }
    .runbox { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--space-4); padding: var(--space-4) var(--space-6);
              margin: 0 0 var(--space-8); max-width: 1080px; }
    .field { display: grid; gap: 6px; min-width: 200px; }
    .field label { font: 500 12px/16px var(--font-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--accent); }
    .field input { background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
                   padding: 9px 12px; font: 400 15px/20px var(--font-sans); }
    .go { display: flex; align-items: center; gap: var(--space-4); }
    .more summary { cursor: pointer; font-size: 13px; }
    .more[open] { display: grid; gap: 6px; }
    .check { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--ink-muted); }
    .error { flex-basis: 100%; color: var(--refused); margin: 0; }
    .sheet { padding: var(--space-4) var(--space-6); margin: 0 0 var(--space-8); max-width: 1080px; display: grid; gap: var(--space-3); }
    .sheet-head { display: flex; justify-content: space-between; align-items: center; gap: var(--space-4); }
    .sheet-head p { margin: 0; }
    .sheet .btn { cursor: pointer; }
    .sheet .scroll { overflow-x: auto; }
    .preview { border-collapse: collapse; font-size: 13px; }
    .preview th, .preview td { padding: 6px 12px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
    .sheet button.primary { justify-self: start; }
    .sheet button:disabled { opacity: .4; cursor: not-allowed; }
    .linkish { background: none; border: 0; padding: 0; color: var(--accent); font: inherit; cursor: pointer; text-decoration: underline; }
    .facts { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: var(--space-4); margin: 0 0 var(--space-8); max-width: 1080px; }
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
    .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); margin: 0 0 var(--space-6); max-width: 1080px; overflow-x: auto; }
    .tab { background: none; border: 0; border-bottom: 2px solid transparent; color: var(--ink-muted); padding: 10px 14px; font: 500 14px/20px var(--font-sans);
           cursor: pointer; white-space: nowrap; margin-bottom: -1px; }
    .tab.on { color: var(--ink); border-bottom-color: var(--lime); }
    .count { display: inline-block; min-width: 20px; margin-left: 6px; padding: 0 6px; border-radius: 10px; background: var(--surface-raised);
             font: 500 11px/18px var(--font-mono); text-align: center; color: var(--ink-muted); }
    .item { margin-bottom: var(--space-3); display: grid; gap: 6px; }
    .item header { display: flex; align-items: center; gap: var(--space-3); }
    .item p { margin: 0; }
    .item.dim { opacity: .6; }
    .grow { flex: 1; }
    .lab { font: 500 11px/16px var(--font-mono); letter-spacing: .1em; text-transform: uppercase; color: var(--ink-muted); margin-right: 8px; }
    .btn.small { padding: 4px 10px; font-size: 12.5px; }
    .noteform { display: flex; gap: var(--space-3); align-items: flex-start; margin-bottom: var(--space-3); }
    .noteform textarea, .settings textarea, .settings input, .settings select, .danger input {
      flex: 1; background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
      padding: 9px 12px; font: 400 14px/20px var(--font-sans); resize: vertical; }
    .settings { display: grid; gap: var(--space-4); margin-bottom: var(--space-6); }
    .field.wide { min-width: 0; }
    .warn { margin: 0; padding: 10px 12px; border: 1px solid var(--waiting); border-radius: var(--radius-sm); font-size: 13.5px; }
    .danger { border-color: var(--refused); }
    .danger .go input { max-width: 320px; }
    .dangerbtn { background: var(--refused); color: #fff; border-color: var(--refused); }
    .dangerbtn:disabled { opacity: .45; }
  `],
})
export class AutomationPage {
  private api = inject(Api);
  private runs = inject(Runs);
  private router = inject(Router);
  values: Record<string, string> = {};
  relearn = false; fresh = false; show = false;
  shot = false;
  busy = signal(false);
  error = signal('');

  logIn(a: AutomationDetail) {
    this.runs.logIn(a.name).subscribe({
      next: r => this.router.navigate(['/runs', r.id]),
      error: e => this.error.set(apiError(e, tr('The browser could not open.'))),
    });
  }

  run(a: AutomationDetail) {
    this.error.set(''); this.busy.set(true);
    this.runs.startAutomation(a.name, this.values, this.relearn, this.fresh, this.show, undefined, this.shot).subscribe({
      next: r => this.router.navigate(['/runs', r.id]),
      error: e => { this.busy.set(false); this.error.set(apiError(e, tr('The run could not start.'))); },
    });
  }
  name = input.required<string>();
  a = signal<AutomationDetail | null>(null);
  notFound = signal(false);
  stateWords = STATE_WORDS; stateClass = STATE_CLASS; host = host; runDate = runDate; parts = parts; modelName = modelName; isoDate = isoDate;
  action = (a: string) => tr(ACTIONS[a] ?? a);

  downloadLog(a: AutomationDetail) {
    this.api.lastLog(a.name).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const link = Object.assign(document.createElement('a'), { href: url, download: `anchor-${a.name}-last-run.json` });
        document.body.appendChild(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
      error: e => this.error.set(apiError(e, tr('The log could not be downloaded.'))),
    });
  }

  // ------------------------------------------------------------------ a spreadsheet
  sheet = signal<SheetCheck | null>(null);
  sheetName = signal('');
  sheetError = signal('');
  pickSheet(a: AutomationDetail, event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    this.sheet.set(null); this.sheetError.set('');
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) { this.sheetError.set('The spreadsheet is larger than 5 MB.'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const content = String(reader.result).split(',')[1] ?? '';
      this.api.checkSheet(a.name, file.name, content).subscribe({
        next: s => { this.sheet.set(s); this.sheetName.set(file.name); },
        error: e => this.sheetError.set(apiError(e, tr('The spreadsheet could not be read.'))),
      });
    };
    reader.readAsDataURL(file);
  }
  sheetOk(s: SheetCheck) { return !s.missing.length && !s.blank_rows.length && !s.too_many && s.rows > 0; }
  runSheet(a: AutomationDetail, s: SheetCheck) {
    this.error.set(''); this.busy.set(true);
    this.runs.startAutomation(a.name, {}, this.relearn, this.fresh, this.show, s.all, this.shot).subscribe({
      next: r => this.router.navigate(['/runs', r.id]),
      error: e => { this.busy.set(false); this.sheetError.set(apiError(e, tr('The run could not start.'))); },
    });
  }

  // ------------------------------------------------------------------ tabs
  tabs = [{ id: 'overview', label: 'Overview' }, { id: 'fixes', label: 'Fixes' }, { id: 'notes', label: 'Notes' },
          { id: 'decisions', label: 'Decisions' }, { id: 'choices', label: 'Choices' }, { id: 'settings', label: 'Settings' }];
  tab = signal('overview');
  fixes = signal<Fix[]>([]); notes = signal<Note[]>([]); decisions = signal<Decision[]>([]); choices = signal<Choice[]>([]);
  profiles = signal<Profile[]>([]);
  actionError = signal(''); saved = signal('');
  editing = signal<number | null>(null);
  newNote = ''; editText = ''; notesSent = 5;
  sRequest = ''; sUrl = ''; sProfile = ''; confirmName = '';

  count(a: AutomationDetail, id: string): number | null {
    return ({ fixes: a.recoveries, notes: a.notes, decisions: a.confirmations, choices: a.choices } as Record<string, number>)[id] ?? null;
  }
  open(id: string, a: AutomationDetail) {
    this.tab.set(id); this.actionError.set(''); this.saved.set('');
    const fail = (e: unknown) => this.actionError.set(apiError(e, tr('This could not be loaded.')));
    if (id === 'fixes') this.api.fixes(a.name).subscribe({ next: x => this.fixes.set(x), error: fail });
    if (id === 'notes') this.api.notes(a.name).subscribe({ next: x => this.notes.set(x), error: fail });
    if (id === 'decisions') this.api.decisions(a.name).subscribe({ next: x => this.decisions.set(x), error: fail });
    if (id === 'choices') this.api.choices(a.name).subscribe({ next: x => this.choices.set(x), error: fail });
    if (id === 'settings') {
      this.sRequest = a.request; this.sUrl = a.url; this.sProfile = a.profile; this.confirmName = '';
      this.runs.profiles().subscribe(p => this.profiles.set(p));
    }
  }
  private refresh(a: AutomationDetail, id: string) {
    this.api.automation(a.name).subscribe(d => { this.a.set(d); this.open(id, d); });
  }
  private failed = (e: unknown) => this.actionError.set(apiError(e, tr('This could not be done.')));
  stepText(s: PlanStep | null | undefined) { return s ? `${this.action(s.action)} ${s.description}${s.value !== null ? ' = "' + s.value + '"' : ''}` : '—'; }
  category(c: string) { return tr(({ delete: 'Delete', submit: 'Save or send', send: 'Send', pay: 'Pay', download: 'Download', upload: 'Upload', account: 'Act on your account' } as Record<string, string>)[c] ?? c); }

  undo(a: AutomationDetail, f: Fix) {
    const what = tr(f.method === 'replan' ? 'This brings the plan back to how it was before this fix (later plan fixes are undone too).'
                                          : 'ANCHOR forgets the element you chose, and asks again next time.');
    if (!confirm(tr('Undo fix #{n}?', { n: f.number }) + ' ' + what)) return;
    this.api.undoFix(a.name, f.number).subscribe({ next: () => this.refresh(a, 'fixes'), error: this.failed });
  }
  addNote(a: AutomationDetail) {
    this.api.addNote(a.name, this.newNote).subscribe({ next: () => { this.newNote = ''; this.refresh(a, 'notes'); }, error: this.failed });
  }
  startEdit(n: Note) { this.editing.set(n.number); this.editText = n.text; }
  saveEdit(a: AutomationDetail, n: Note) {
    this.api.editNote(a.name, n.number, this.editText).subscribe({ next: () => { this.editing.set(null); this.refresh(a, 'notes'); }, error: this.failed });
  }
  removeNote(a: AutomationDetail, n: Note) {
    if (!confirm(tr('Remove note #{n}?', { n: n.number }))) return;
    this.api.removeNote(a.name, n.number).subscribe({ next: () => this.refresh(a, 'notes'), error: this.failed });
  }
  forgetDecision(a: AutomationDetail, d: Decision) {
    if (!confirm(tr('Forget this decision? Next time, ANCHOR asks you again before: {what} “{element}”.', { what: this.category(d.category).toLowerCase(), element: d.element }))) return;
    this.api.forgetDecision(a.name, d.number).subscribe({ next: () => this.refresh(a, 'decisions'), error: this.failed });
  }
  forgetChoice(a: AutomationDetail, c: Choice) {
    if (!confirm(tr('Forget this choice? Next time, ANCHOR asks you again which element “{what}” means.', { what: c.description }))) return;
    this.api.forgetChoice(a.name, c.key).subscribe({ next: () => this.refresh(a, 'choices'), error: this.failed });
  }
  relearns(a: AutomationDetail) { return this.sRequest.trim() !== a.request || this.sUrl.trim() !== a.url; }
  changed(a: AutomationDetail) { return this.relearns(a) || this.sProfile !== a.profile; }
  save(a: AutomationDetail) {
    this.api.edit(a.name, this.sRequest, this.sUrl, this.sProfile).subscribe({
      next: r => { this.saved.set(r.relearn ? 'Saved. The next run learns the plan again.' : 'Saved.'); this.api.automation(a.name).subscribe(d => this.a.set(d)); },
      error: this.failed });
  }
  remove(a: AutomationDetail) {
    this.api.remove(a.name, this.confirmName).subscribe({ next: () => this.router.navigate(['/automations']), error: this.failed });
  }

  constructor() {
    const again = history.state as { values?: Record<string, string>; relearn?: boolean; fresh?: boolean; window?: boolean } | null;
    if (again?.values) {                                   // "Try again": the same values as the last run
      this.values = { ...again.values }; this.relearn = !!again.relearn; this.fresh = !!again.fresh; this.show = !!again.window;
    }
    effect(() => {
      const name = this.name();
      this.a.set(null); this.notFound.set(false);
      this.api.automation(name).subscribe({ next: d => this.a.set(d), error: () => this.notFound.set(true) });
    });
  }
}
