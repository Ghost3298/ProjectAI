import { Component, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { TimeSettingsService } from '../../services/time-settings.service';

type Theme = 'light' | 'dark';

const THEME_KEY = 'ai-transcript.theme';
const AUTOSAVE_KEY = 'ai-transcript.autosave';
const TIMESTAMPS_KEY = 'ai-transcript.timestamps';

export interface TimezoneOption {
  minutes: number;
  label: string;
}

function buildTimezoneOptions(): TimezoneOption[] {
  const options: TimezoneOption[] = [];
  for (let minutes = -12 * 60; minutes <= 14 * 60; minutes += 30) {
    const sign = minutes >= 0 ? '+' : '-';
    const abs = Math.abs(minutes);
    const hh = Math.floor(abs / 60);
    const mm = abs % 60;
    options.push({ minutes, label: `UTC${sign}${hh}${mm ? ':30' : ''}` });
  }
  return options;
}

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
  protected readonly timezoneOptions = buildTimezoneOptions();
  protected readonly utcOffsetMinutes;

  constructor(private timeSettings: TimeSettingsService) {
    this.utcOffsetMinutes = this.timeSettings.utcOffsetMinutes;
  }

  updateUtcOffset(value: string): void {
    const minutes = parseInt(value, 10);
    if (!Number.isNaN(minutes)) this.timeSettings.setOffsetMinutes(minutes);
  }

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
