import { Component, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

type Theme = 'light' | 'dark';

const THEME_KEY = 'ai-transcript.theme';
const AUTOSAVE_KEY = 'ai-transcript.autosave';
const TIMESTAMPS_KEY = 'ai-transcript.timestamps';

@Component({
  selector: 'app-settings',
  imports: [MatIconModule],
  templateUrl: './settings.html',
  styleUrl: './settings.css',
})
export class Settings {
  protected readonly theme = signal<Theme>(this.readTheme());
  protected readonly autosave = signal<boolean>(this.readBool(AUTOSAVE_KEY, true));
  protected readonly showTimestamps = signal<boolean>(this.readBool(TIMESTAMPS_KEY, true));

  toggleTheme(): void {
    const next: Theme = this.theme() === 'dark' ? 'light' : 'dark';
    this.theme.set(next);
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem(THEME_KEY, next);
  }

  toggleAutosave(): void {
    const next = !this.autosave();
    this.autosave.set(next);
    localStorage.setItem(AUTOSAVE_KEY, String(next));
  }

  toggleTimestamps(): void {
    const next = !this.showTimestamps();
    this.showTimestamps.set(next);
    localStorage.setItem(TIMESTAMPS_KEY, String(next));
  }

  private readTheme(): Theme {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === 'dark' || stored === 'light') {
      document.documentElement.setAttribute('data-theme', stored);
      return stored;
    }
    return 'light';
  }

  private readBool(key: string, fallback: boolean): boolean {
    const stored = localStorage.getItem(key);
    return stored === null ? fallback : stored === 'true';
  }
}
