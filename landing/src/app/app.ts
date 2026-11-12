import { Component, computed, effect, signal } from '@angular/core';

import { Changed } from './changed';
import { COPY, DOCS_URL, DOWNLOAD_URL, Lang, OLLAMA_URL, REPO_URL, SPACE_URL, TESTS_URL } from './copy';
import { Demo } from './demo';
import { Results } from './results';
import { Schedule } from './schedule';
import { Trick } from './trick';

type Theme = 'dark' | 'light';

function stored(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

function store(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* private mode: the choice lasts for this visit */ }
}

/** The language asked for in the address (?lang=pt), else the one chosen before, else the browser's. */
function firstLanguage(): Lang {
  const asked = new URLSearchParams(location.search).get('lang') ?? stored('anchor-site-lang');
  if (asked === 'pt' || asked === 'en') return asked;
  return navigator.language.toLowerCase().startsWith('pt') ? 'pt' : 'en';
}

@Component({
  selector: 'app-root',
  imports: [Demo, Trick, Changed, Schedule, Results],
  template: `
    <header class="top">
      <a class="top-mark" href="./" [attr.aria-label]="t().nav.home">
        <img [src]="theme() === 'dark' ? 'brand/anchor-wordmark-on-dark.svg' : 'brand/anchor-wordmark-on-light.svg'" alt="ANCHOR" height="18">
      </a>
      <nav class="top-links" aria-label="ANCHOR">
        <a href="#how">{{ t().nav.how }}</a>
        <a href="#uses">{{ t().nav.uses }}</a>
        <a href="#install">{{ t().nav.install }}</a>
        <a [href]="docs">{{ t().nav.docs }}</a>
        <button type="button" (click)="lang.set(lang() === 'pt' ? 'en' : 'pt')">{{ t().nav.otherLanguage }}</button>
        <button type="button" (click)="theme.set(theme() === 'dark' ? 'light' : 'dark')">
          {{ theme() === 'dark' ? t().nav.lightTheme : t().nav.darkTheme }}</button>
        <a class="pill go" [href]="download">{{ t().nav.download }}</a>
      </nav>
    </header>

    <main>
      <section class="hero">
        <div class="hero-words">
          <h1><span>{{ t().hero.line1 }}</span> <em>{{ t().hero.line2 }}</em></h1>
          <p class="lead">{{ t().hero.lead }}</p>
          <div class="hero-actions">
            <a class="pill go big" [href]="download">{{ t().hero.download }}</a>
            <a class="pill big" href="#how">{{ t().hero.how }}</a>
          </div>
          <p class="facts">{{ t().hero.facts }}</p>
        </div>
        <app-demo [t]="t().demo" />
      </section>

      <section class="block" id="how">
        <h2 class="title"><span>{{ t().how.heading[0] }}</span> <em>{{ t().how.heading[1] }}</em></h2>
        <ol class="steps3">
          @for (step of t().how.steps; track $index) {
            <li><h3>{{ step.title }}</h3><p>{{ step.text }}</p></li>
          }
        </ol>
        <div class="times">
          <div class="seg" role="group" [attr.aria-label]="t().how.first">
            <button type="button" [class.on]="!learned()" [attr.aria-pressed]="!learned()" (click)="learned.set(false)">{{ t().how.first }}</button>
            <button type="button" [class.on]="learned()" [attr.aria-pressed]="learned()" (click)="learned.set(true)">{{ t().how.next }}</button>
          </div>
          <p class="times-text" aria-live="polite">{{ learned() ? t().how.nextText : t().how.firstText }}</p>
          <div class="times-bar" aria-hidden="true"><i [class.short]="learned()"></i></div>
          <p class="times-label">{{ learned() ? t().how.nextTime : t().how.firstTime }}</p>
          <p class="fine">{{ t().how.measured }}</p>
        </div>
      </section>

      <div class="band" [attr.data-theme]="other()">
        <section class="block" id="uses">
          <h2 class="title"><span>{{ t().uses.heading[0] }}</span> <em>{{ t().uses.heading[1] }}</em></h2>
          <p class="lead" id="uses-lead">{{ t().uses.lead }}</p>
          <div class="seg wrap" role="group" aria-labelledby="uses-lead">
            @for (group of t().uses.groups; track $index) {
              <button type="button" [class.on]="place() === $index" [attr.aria-pressed]="place() === $index" (click)="place.set($index)">{{ group.name }}</button>
            }
          </div>
          <ul class="requests" aria-live="polite">
            @for (request of t().uses.groups[place()].requests; track request) { <li>{{ request }}</li> }
          </ul>
          <p class="fine">{{ t().uses.note }}</p>
        </section>
      </div>

      <section class="block" id="control">
        <h2 class="title"><span>{{ t().control.heading[0] }}</span> <em>{{ t().control.heading[1] }}</em></h2>
        <ul class="cards">
          @for (card of t().control.cards; track $index) { <li><h3>{{ card.title }}</h3><p>{{ card.text }}</p></li> }
        </ul>
        <div class="feature">
          <h3>{{ t().control.trick.title }}</h3>
          <p class="lead">{{ t().control.trick.text }}</p>
          <app-trick [t]="t().control.trick" />
        </div>
      </section>

      <section class="block" id="changes">
        <h2 class="title"><span>{{ t().changes.heading[0] }}</span> <em>{{ t().changes.heading[1] }}</em></h2>
        <p class="lead">{{ t().changes.lead }}</p>
        <app-changed [t]="t().changes" />
        <p class="proof">{{ t().changes.proof }} <a href="#results">{{ t().changes.proofLink }}</a></p>
      </section>

      <div class="band" [attr.data-theme]="other()">
        <section class="block" id="results">
          <h2 class="title"><span>{{ t().results.heading[0] }}</span> <em>{{ t().results.heading[1] }}</em></h2>
          <p class="lead">{{ t().results.lead }}</p>
          <app-results [t]="t().results" />
        </section>
      </div>

      <section class="block" id="repeat">
        <h2 class="title"><span>{{ t().repeat.heading[0] }}</span> <em>{{ t().repeat.heading[1] }}</em></h2>
        <div class="split">
          <ul class="points">
            @for (point of t().repeat.points; track $index) { <li><h3>{{ point.title }}</h3><p>{{ point.text }}</p></li> }
          </ul>
          <app-schedule [t]="t().repeat" [lang]="lang()" />
        </div>
      </section>

      <div class="band" [attr.data-theme]="other()">
        <section class="block" id="install">
          <h2 class="title"><span>{{ t().install.heading[0] }}</span> <em>{{ t().install.heading[1] }}</em></h2>
          <ol class="steps3">
            @for (step of t().install.steps; track $index) {
              <li>
                <h3>{{ step.title }}</h3><p>{{ step.text }}</p>
                @if ($index === 0) { <a class="pill" [href]="ollama">{{ t().install.ollama }}</a> }
                @if ($index === 1) { <a class="pill go" [href]="download">{{ t().install.download }}</a> }
              </li>
            }
          </ol>
          <p class="fine">{{ t().install.needs }}</p>
          <p class="fine">{{ t().install.warning }}</p>
        </section>
      </div>
    </main>

    <footer class="foot">
      <div>
        <p class="foot-title">{{ t().footer.forDevs }}</p>
        <p class="foot-links">
          <a [href]="repo">{{ t().footer.code }}</a>
          <a [href]="docs">{{ t().footer.docs }}</a>
          <a [href]="tests">{{ t().footer.tests }}</a>
          <a [href]="space">{{ t().footer.demo }}</a>
        </p>
      </div>
      <p>{{ t().footer.license }}</p>
    </footer>
  `,
})
export class App {
  readonly lang = signal<Lang>(firstLanguage());
  readonly theme = signal<Theme>(stored('anchor-site-theme') === 'light' ? 'light' : 'dark');
  /** The other theme, for the bands that alternate with the page (their tokens are scoped by data-theme). */
  readonly other = computed<Theme>(() => (this.theme() === 'dark' ? 'light' : 'dark'));
  readonly t = computed(() => COPY[this.lang()]);
  readonly learned = signal(false);        // "how it works": the first time, or the next times
  readonly place = signal(0);              // "what it is for": which group of requests is shown

  readonly download = DOWNLOAD_URL;
  readonly ollama = OLLAMA_URL;
  readonly repo = REPO_URL;
  readonly docs = DOCS_URL;
  readonly tests = TESTS_URL;
  readonly space = SPACE_URL;

  constructor() {
    effect(() => {
      document.documentElement.lang = this.lang() === 'pt' ? 'pt-BR' : 'en';
      store('anchor-site-lang', this.lang());
    });
    effect(() => {
      document.documentElement.dataset['theme'] = this.theme();
      store('anchor-site-theme', this.theme());
    });
  }
}
