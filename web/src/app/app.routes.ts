import { Routes } from '@angular/router';

import { AutomationPage } from './pages/automation';
import { AutomationsPage } from './pages/automations';
import { SoonPage } from './pages/soon';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'automations' },
  { path: 'automations', component: AutomationsPage, title: 'Automations · ANCHOR' },
  { path: 'automations/:name', component: AutomationPage, title: 'Automation · ANCHOR' },
  { path: 'run', component: SoonPage, title: 'Run a request · ANCHOR', data: { what: 'Run a request' } },
  { path: 'schedules', component: SoonPage, title: 'Schedules · ANCHOR', data: { what: 'Schedules' } },
  { path: 'settings', component: SoonPage, title: 'Settings · ANCHOR', data: { what: 'Settings' } },
  { path: '**', redirectTo: 'automations' },
];
