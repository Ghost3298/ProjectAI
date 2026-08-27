import { Injectable, signal } from '@angular/core';

const OFFSET_KEY = 'ai-transcript.utcOffsetMinutes';

@Injectable({ providedIn: 'root' })
export class TimeSettingsService {
  // Not derived from the browser's own timezone APIs on purpose: browsers
  // with fingerprinting resistance enabled (common on privacy-focused
  // setups) deliberately report UTC as the local timezone regardless of the
  // OS's real one, so Date/Intl-based "local time" can silently be wrong by
  // whatever the real UTC offset is. This is a one-time manual setting
  // instead, applied via plain arithmetic that no browser privacy feature
  // can spoof.
  readonly utcOffsetMinutes = signal<number>(this.readOffset());

  setOffsetMinutes(minutes: number): void {
    this.utcOffsetMinutes.set(minutes);
    localStorage.setItem(OFFSET_KEY, String(minutes));
  }

  formatOffsetForDatePipe(): string {
    const minutes = this.utcOffsetMinutes();
    const sign = minutes >= 0 ? '+' : '-';
    const abs = Math.abs(minutes);
    const hh = String(Math.floor(abs / 60)).padStart(2, '0');
    const mm = String(abs % 60).padStart(2, '0');
    return `${sign}${hh}${mm}`;
  }

  private readOffset(): number {
    const stored = localStorage.getItem(OFFSET_KEY);
    if (stored !== null) {
      const parsed = parseInt(stored, 10);
      if (!Number.isNaN(parsed)) return parsed;
    }
    return -new Date().getTimezoneOffset();
  }
}
