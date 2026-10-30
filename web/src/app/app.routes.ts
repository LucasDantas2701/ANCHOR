import { RunsPage } from './pages/runs';
import { Routes } from '@angular/router';

import { AutomationPage } from './pages/automation';
import { AutomationsPage } from './pages/automations';
import { NewAutomationPage } from './pages/new-automation';
import { RequestPage } from './pages/request';
import { RunPage } from './pages/run';
import { SoonPage } from './pages/soon';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'automations' },
  { path: 'automations', component: AutomationsPage, title: 'Automations · ANCHOR' },
  { path: 'automations/new', component: NewAutomationPage, title: 'New automation · ANCHOR' },
  { path: 'automations/:name', component: AutomationPage, title: 'Automation · ANCHOR' },
  { path: 'run', component: RequestPage, title: 'Run a request · ANCHOR' },
  { path: 'runs', component: RunsPage, title: 'Runs · ANCHOR' },
  { path: 'runs/:id', component: RunPage, title: 'Run · ANCHOR' },
  { path: 'schedules', component: SoonPage, title: 'Schedules · ANCHOR', data: { what: 'Schedules' } },
  { path: 'settings', component: SoonPage, title: 'Settings · ANCHOR', data: { what: 'Settings' } },
  { path: '**', redirectTo: 'automations' },
];
