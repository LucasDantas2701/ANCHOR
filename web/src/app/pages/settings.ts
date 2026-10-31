import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { Api, Choice, DesktopInfo, SavedLogin, apiError, isoDate } from '../api';

/** Settings: for now, the choices remembered from requests (each automation keeps its own). */
@Component({
  selector: 'app-settings',
  imports: [RouterLink, FormsModule],
  template: `
    <p class="eyebrow">ANCHOR</p>
    <h1 class="title">Settings</h1>

    @if (desk()?.start_with_windows?.available) {
      <section>
        <p class="eyebrow">Start with Windows</p>
        <div class="card pad startrow">
          <div><b>Open ANCHOR, hidden near the clock, when you log in to Windows.</b>
            <p class="muted small">So schedules run without anyone opening ANCHOR. Turn it off if you do not use schedules.</p></div>
          <label class="check"><input type="checkbox" [checked]="desk()?.start_with_windows?.on" (change)="startWithWindows($any($event.target).checked)"> On</label>
        </div>
      </section>
    }

    <section>
      <p class="eyebrow">Saved logins</p>
      <div class="lead muted">
        <p>When a run reaches a login page, ANCHOR logs in by itself with a login saved here, and waits for you if it does not get in
          (a wrong password, or a code sent to your phone).</p>
        <ul class="rules">
          <li><b>Only on its exact address.</b> A login saved for <span class="mono">accounts.example.com</span> is not used on
            <span class="mono">mail.example.com</span>, on another port, or on a page without https.</li>
          <li><b>The password goes to Windows' Credential Manager</b>, never to a file, and is never shown again: you can replace it or delete it.</li>
          <li><b>The AI never sees it.</b> ANCHOR's own code types it, only into a password field, only on that site.</li>
          <li><b>Scheduled runs use a login only if you turn it on</b> for that login.</li>
        </ul>
      </div>
      <form class="card pad loginform" (ngSubmit)="addLogin()" autocomplete="off">
        <div class="field"><label for="l-site">Site address</label><input id="l-site" name="lSite" [(ngModel)]="lSite" placeholder="https://accounts.example.com"></div>
        <div class="field"><label for="l-user">User name or e-mail</label><input id="l-user" name="lUser" [(ngModel)]="lUser" autocomplete="off"></div>
        <div class="field"><label for="l-pass">Password</label><input id="l-pass" name="lPass" type="password" [(ngModel)]="lPass" autocomplete="new-password"></div>
        <label class="check"><input type="checkbox" name="lSched" [(ngModel)]="lSched"> Use in scheduled runs</label>
        <button class="btn primary" type="submit" [disabled]="!lSite.trim() || !lUser.trim() || !lPass">Save login</button>
      </form>
      @if (loginError()) { <p class="error" role="alert">{{ loginError() }}</p> }
      @for (l of logins(); track l.site + l.username) {
        <article class="card site">
          <header><span class="mono">{{ l.site }}</span><span class="muted">{{ l.username }}</span><span class="grow"></span>
            <label class="check small"><input type="checkbox" [checked]="l.scheduled" (change)="schedule(l, $any($event.target).checked)"> Use in scheduled runs</label>
            <button class="btn small" type="button" (click)="replacing.set(replacing() === key(l) ? '' : key(l))">Replace password</button>
            <button class="btn small" type="button" (click)="removeLogin(l)">Delete</button></header>
          <p class="muted small">Saved {{ isoDate(l.created) }}@if (l.last_used) { · last used {{ isoDate(l.last_used) }} } @else { · not used yet }</p>
          @if (replacing() === key(l)) {
            <form class="replace" (ngSubmit)="replace(l)" autocomplete="off">
              <input name="newPass" type="password" [(ngModel)]="newPass" autocomplete="new-password" placeholder="New password">
              <button class="btn primary small" type="submit" [disabled]="!newPass">Save</button>
            </form>
          }
        </article>
      } @empty { <div class="card pad muted">No saved logins. Runs that reach a login page wait for you to log in on the live view.</div> }
    </section>

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
    .site ul { list-style: none; margin: 0; padding: 0; }
    .site li { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: 10px 0; border-top: 1px solid var(--border); font-size: 14px; }
    .small { font-size: 12.5px; }
    .btn.small { padding: 4px 10px; font-size: 12.5px; }
    .pad { padding: var(--space-4) var(--space-6); }
    .error { color: var(--refused); }
    .rules { margin: var(--space-2) 0 0; padding-left: 18px; display: grid; gap: 4px; }
    .lead p { margin: 0; }
    .loginform { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--space-4); margin-bottom: var(--space-4); }
    .field { display: grid; gap: 6px; min-width: 220px; flex: 1; }
    .field label { font: 500 12px/16px var(--font-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--accent); }
    .field input, .replace input { background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
                   padding: 9px 12px; font: 400 14px/20px var(--font-sans); }
    .check { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--ink-muted); }
    .replace { display: flex; gap: var(--space-3); margin-top: var(--space-2); }
    .site p { margin: 4px 0 0; }
    .startrow { display: flex; justify-content: space-between; align-items: center; gap: var(--space-4); }
    .startrow p { margin: 4px 0 0; }
  `],
})
export class SettingsPage {
  private api = inject(Api);
  sites = signal<{ site: string; choices: Choice[] }[]>([]);
  error = signal('');
  isoDate = isoDate;

  logins = signal<SavedLogin[]>([]);
  loginError = signal('');
  replacing = signal('');
  lSite = ''; lUser = ''; lPass = ''; lSched = false; newPass = '';
  key(l: SavedLogin) { return l.site + ' ' + l.username; }

  desk = signal<DesktopInfo | null>(null);
  constructor() { this.load(); this.loadLogins(); this.api.desktop().subscribe({ next: d => this.desk.set(d), error: () => {} }); }
  startWithWindows(on: boolean) {
    this.api.startWithWindows(on).subscribe({ next: () => this.api.desktop().subscribe(d => this.desk.set(d)),
                                              error: e => this.loginError.set(apiError(e, 'This could not be changed.')) });
  }
  loadLogins() { this.api.logins().subscribe({ next: x => this.logins.set(x), error: e => this.loginError.set(apiError(e, 'The logins could not be loaded.')) }); }
  addLogin() {
    this.loginError.set('');
    const password = this.lPass;
    this.lPass = '';                                   // never kept in the page after it is sent
    this.api.addLogin(this.lSite, this.lUser, password, this.lSched).subscribe({
      next: () => { this.lSite = ''; this.lUser = ''; this.lSched = false; this.loadLogins(); },
      error: e => this.loginError.set(apiError(e, 'The login could not be saved.')),
    });
  }
  replace(l: SavedLogin) {
    const password = this.newPass;
    this.newPass = '';
    this.api.replacePassword(l.site, l.username, password).subscribe({
      next: () => { this.replacing.set(''); this.loadLogins(); },
      error: e => this.loginError.set(apiError(e, 'The password could not be replaced.')),
    });
  }
  schedule(l: SavedLogin, on: boolean) {
    this.api.setScheduled(l.site, l.username, on).subscribe({ next: () => this.loadLogins(), error: e => this.loginError.set(apiError(e, 'This could not be changed.')) });
  }
  removeLogin(l: SavedLogin) {
    if (!confirm(`Delete the login ${l.username} on ${l.site}? Its password is removed from Windows' Credential Manager too.`)) return;
    this.api.deleteLogin(l.site, l.username).subscribe({ next: () => this.loadLogins(), error: e => this.loginError.set(apiError(e, 'The login could not be deleted.')) });
  }
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
