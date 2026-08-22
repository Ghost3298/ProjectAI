import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';

// Apply any previously saved theme before the app renders, so there's no
// light-mode flash for users who have chosen dark mode.
const savedTheme = localStorage.getItem('ai-transcript.theme');
if (savedTheme === 'dark' || savedTheme === 'light') {
  document.documentElement.setAttribute('data-theme', savedTheme);
}

bootstrapApplication(App, appConfig)
  .catch((err) => console.error(err));
