import { Component, afterNextRender, computed, input, signal } from '@angular/core';

import { Copy } from './copy';

type ScenarioId = 'jobs' | 'save' | 'pick';
type Phase = 'typing' | 'planning' | 'running' | 'asking' | 'done' | 'stopped';
type StepState = 'pending' | 'doing' | 'waiting' | 'checked' | 'denied' | 'chosen';

interface Page {
  query: boolean; city: boolean; searched: boolean; read: boolean;       // jobs
  name: boolean; email: boolean; saved: boolean;                         // save
  picked: number | null;                                                 // pick: the row the visitor chose
}

const EMPTY: Page = { query: false, city: false, searched: false, read: false, name: false, email: false, saved: false, picked: null };
const SCENARIOS: ScenarioId[] = ['jobs', 'save', 'pick'];

/**
 * A simulation of ANCHOR's interface, for the page's hero: the visitor picks a request and sees it typed,
 * planned and done step by step on a small page, each step checked. In "save" ANCHOR stops and asks before
 * the sensitive click (the visitor allows or denies); in "pick" it asks which of two elements is meant (the
 * visitor clicks the row). Nothing here calls a model or a site: it is scripted, and says so.
 */
@Component({
  selector: 'app-demo',
  template: `
    <div class="demo" role="group" [attr.aria-label]="t().label">
      <div class="demo-bar">
        <span class="demo-dots" aria-hidden="true"><i></i><i></i><i></i></span>
        <span class="demo-name">ANCHOR</span>
        <span class="demo-tag">{{ t().label }}</span>
      </div>

      <p class="demo-hint" id="demo-hint">{{ t().hint }}</p>
      <div class="demo-chips" role="group" aria-labelledby="demo-hint">
        @for (id of scenarios; track id) {
          <button type="button" class="demo-chip" [class.on]="scenario() === id" [attr.aria-pressed]="scenario() === id"
                  (click)="play(id)">{{ t()[id].chip }}</button>
        }
      </div>

      <div class="demo-request">
        <span class="demo-request-label">{{ t().request }}</span>
        <span class="demo-request-text">{{ typed() }}<span class="demo-caret" [class.blink]="phase() !== 'typing'" aria-hidden="true"></span></span>
      </div>

      <div class="demo-panes">
        <!-- the small page ANCHOR works on: another site, so it keeps its own (light) colours -->
        <div class="site" aria-hidden="true">
          <div class="site-bar"><i></i>{{ t()[scenario()].site }}</div>
          <div class="site-body">
            @switch (scenario()) {
              @case ('jobs') {
                <div class="site-row">
                  <span class="site-input" [class.touched]="page().query">{{ page().query ? t().jobs.query : t().jobs.search }}</span>
                  <span class="site-input short" [class.touched]="page().city">{{ page().city ? 'Manaus' : t().jobs.anyCity }}</span>
                  <span class="site-btn" [class.pressed]="page().searched">{{ t().jobs.button }}</span>
                </div>
                <ul class="site-list" [class.read]="page().read">
                  @for (job of t().jobs.results; track job[0]) {
                    <li [class.shown]="page().searched"><b>{{ job[0] }}</b><span>{{ job[1] }}</span></li>
                  }
                </ul>
              }
              @case ('save') {
                <label class="site-field"><span>{{ t().save.name }}</span>
                  <span class="site-input" [class.touched]="page().name">{{ page().name ? t().save.nameValue : '' }}</span></label>
                <label class="site-field"><span>{{ t().save.email }}</span>
                  <span class="site-input" [class.touched]="page().email">{{ page().email ? t().save.emailValue : '' }}</span></label>
                <div class="site-row">
                  <span class="site-btn" [class.pressed]="page().saved" [class.asked]="phase() === 'asking'">{{ t().save.button }}</span>
                  <span class="site-btn danger">{{ t().save.remove }}</span>
                </div>
                @if (page().saved) { <p class="site-ok">{{ t().save.saved }}</p> }
              }
              @case ('pick') {
                <ul class="site-people">
                  @for (person of t().pick.people; track $index) {
                    <li [class.candidate]="phase() === 'asking' && person[0] === 'Bruno Lima'" [class.picked]="page().picked === $index"
                        (click)="pickRow($index, person[0])">
                      <span><b>{{ person[0] }}</b> {{ person[1] }}</span><span class="site-link">{{ t().pick.open }}</span>
                    </li>
                  }
                </ul>
                @if (page().picked !== null) {
                  <p class="site-ok">{{ t().pick.opened }} {{ t().pick.people[page().picked!][0] }}, {{ t().pick.people[page().picked!][1] }}</p>
                }
              }
            }
          </div>
        </div>

        <div class="log">
          <div class="log-title">{{ t().happened }}</div>
          @if (phase() === 'typing') { <p class="log-idle">&nbsp;</p> }
          @if (phase() === 'planning') { <p class="log-plan">{{ t().planning }}</p> }
          <ol class="log-steps">
            @for (step of steps(); track $index) {
              <li [class]="'s-' + step.state">
                <span class="log-text">{{ step.text }}</span>
                <span class="log-state">{{ label(step.state) }}</span>
              </li>
            }
          </ol>

          @if (phase() === 'asking' && scenario() === 'save') {
            <div class="ask" role="alertdialog" [attr.aria-label]="t().save.ask">
              <p>{{ t().save.ask }}</p>
              <div class="ask-buttons">
                <button type="button" class="btn-go" (click)="answer('allow')">{{ t().save.allow }}</button>
                <button type="button" class="btn-line" (click)="answer('deny')">{{ t().save.deny }}</button>
              </div>
            </div>
          }
          @if (phase() === 'asking' && scenario() === 'pick') {
            <div class="ask" role="alertdialog" [attr.aria-label]="t().pick.ask">
              <p>{{ t().pick.ask }}</p>
              <div class="ask-buttons">
                @for (person of t().pick.people; track $index) {
                  @if (person[0] === 'Bruno Lima') {
                    <button type="button" class="btn-line" (click)="answer('' + $index)">{{ person[0] }}, {{ person[1] }}</button>
                  }
                }
              </div>
            </div>
          }
        </div>
      </div>

      <div class="demo-foot" aria-live="polite">
        @if (phase() === 'done') {
          <span class="outcome ok">{{ scenario() === 'pick' ? t().pick.remembered : t().done }}</span>
          @if (scenario() === 'jobs') { <span class="file">{{ t().file }}</span> }
        }
        @if (phase() === 'stopped') { <span class="outcome stop">{{ t().save.stopped }}</span> }
        @if (phase() === 'done' || phase() === 'stopped') {
          <button type="button" class="btn-line small" (click)="play(scenario())">{{ t().again }}</button>
        }
      </div>
    </div>
  `,
})
export class Demo {
  readonly t = input.required<Copy['demo']>();

  readonly scenarios = SCENARIOS;
  readonly scenario = signal<ScenarioId>('jobs');
  readonly phase = signal<Phase>('typing');
  private readonly letters = signal(0);              // how much of the request is typed: its words follow the language
  readonly typed = computed(() => this.t()[this.scenario()].request.slice(0, this.letters()));
  readonly page = signal<Page>({ ...EMPTY });
  private readonly states = signal<StepState[]>([]);
  /** The steps shown: their words follow the page's language even in the middle of a run. */
  readonly steps = computed(() => this.states().map((state, i) => ({ state, text: this.t()[this.scenario()].steps[i] })));

  private run = 0;                                   // a new run cancels the one before it
  private resolve: ((value: string) => void) | null = null;
  private readonly still = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  constructor() {
    afterNextRender(() => { void this.play('jobs'); });
  }

  label(state: StepState): string {
    const t = this.t();
    return { pending: '', doing: t.doing, waiting: t.waiting, checked: t.checked, denied: t.save.denied, chosen: t.pick.chosen }[state];
  }

  /** A click on a row of the small page: it answers the question when that row is one of the two candidates. */
  pickRow(index: number, name: string): void {
    if (this.phase() === 'asking' && this.scenario() === 'pick' && name === 'Bruno Lima') this.answer('' + index);
  }

  /** The visitor's answer to ANCHOR's question (allow, deny, or the row chosen). */
  answer(value: string): void {
    this.resolve?.(value);
    this.resolve = null;
  }

  async play(id: ScenarioId): Promise<void> {
    const run = ++this.run;
    const alive = () => run === this.run;
    this.resolve = null;
    this.scenario.set(id);
    this.page.set({ ...EMPTY });
    this.states.set([]);
    this.phase.set('typing');

    this.letters.set(0);
    const length = this.t()[id].request.length;
    for (let i = this.still ? length : 1; i <= length; i++) {
      this.letters.set(i);
      await this.wait(16);
      if (!alive()) return;
    }
    this.letters.set(Infinity);                      // the whole request, whatever the language becomes
    this.phase.set('planning');
    await this.wait(750);
    if (!alive()) return;

    const count = this.t()[id].steps.length;
    this.states.set(Array<StepState>(count).fill('pending'));
    this.phase.set('running');
    for (let i = 0; i < count; i++) {
      this.mark(i, 'doing');
      await this.wait(520);
      if (!alive()) return;
      const outcome = await this.act(id, i, alive);
      if (!alive()) return;
      if (outcome === 'denied') {
        this.mark(i, 'denied');
        this.phase.set('stopped');
        return;
      }
      await this.wait(380);
      if (!alive()) return;
      this.mark(i, outcome);
    }
    this.phase.set('done');
  }

  /** What step i does on the small page; "save" and "pick" stop to ask the visitor first. */
  private async act(id: ScenarioId, i: number, alive: () => boolean): Promise<StepState> {
    const set = (change: Partial<Page>) => this.page.update((p) => ({ ...p, ...change }));
    if (id === 'jobs') {
      set([{ query: true }, { city: true }, { searched: true }, { read: true }][i]);
      return 'checked';
    }
    if (id === 'save') {
      if (i === 0) set({ name: true });
      if (i === 1) set({ email: true });
      if (i === 2) {
        const reply = await this.ask(i);
        if (!alive() || reply === 'deny') return 'denied';
        set({ saved: true });
      }
      return 'checked';
    }
    const reply = await this.ask(i);
    if (!alive()) return 'pending';
    set({ picked: Number(reply) });
    return 'chosen';
  }

  private ask(i: number): Promise<string> {
    this.mark(i, 'waiting');
    this.phase.set('asking');
    return new Promise<string>((resolve) => { this.resolve = resolve; }).then((value) => {
      this.phase.set('running');
      return value;
    });
  }

  private mark(i: number, state: StepState): void {
    this.states.update((all) => all.map((s, n) => (n === i ? state : s)));
  }

  private wait(ms: number): Promise<void> {
    return new Promise((done) => setTimeout(done, this.still ? 0 : ms));
  }
}
