import { Component, OnDestroy, computed, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { SessionSummary, SessionsService } from '../../services/sessions.service';
import { SessionSelectionService } from '../../services/session-selection.service';

export interface TranscriptSession {
  id: string;
  title: string;
  createdAt: Date | null;
  subLabel: string;
}

const POLL_INTERVAL_MS = 5000;

@Component({
  selector: 'app-history',
  imports: [MatIconModule],
  templateUrl: './history.html',
  styleUrl: './history.css',
})
export class History implements OnDestroy {
  private readonly sessionSummaries = signal<SessionSummary[]>([]);
  protected readonly query = signal('');

  protected readonly sessions = computed<TranscriptSession[]>(() => {
    const q = this.query().trim().toLowerCase();
    return this.sessionSummaries()
      .filter((session) => {
        if (!q) return true;
        return (session.name ?? '').toLowerCase().includes(q) || (session.first_recording_name ?? '').toLowerCase().includes(q);
      })
      .map((session) => ({
        id: session.session_id,
        title: session.name || session.first_recording_name || 'Untitled session',
        createdAt: session.created_at ? new Date(session.created_at) : null,
        subLabel: this.subLabel(session),
      }));
  });

  private readonly pollHandle: ReturnType<typeof setInterval>;

  constructor(
    private sessionsService: SessionsService,
    private sessionSelection: SessionSelectionService
  ) {
    this.refresh();
    this.pollHandle = setInterval(() => this.refresh(), POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    clearInterval(this.pollHandle);
  }

  private refresh(): void {
    this.sessionsService.listSessions().subscribe({
      next: (sessions) => this.sessionSummaries.set(sessions),
      error: (err) => console.log(err),
    });
  }

  private subLabel(session: SessionSummary): string {
    const recordings = session.recording_count === 1 ? '1 recording' : `${session.recording_count} recordings`;
    const language = session.detected_language ? ` · ${session.detected_language}` : '';
    return `${session.status} · ${recordings}${language}`;
  }

  updateQuery(value: string): void {
    this.query.set(value);
  }

  openSession(id: string): void {
    this.sessionSelection.select(id);
  }

  renameSession(id: string, currentTitle: string): void {
    const name = window.prompt('Name this session', currentTitle);
    if (name === null) return;

    const trimmed = name.trim();
    if (!trimmed || trimmed === currentTitle) return;

    this.sessionsService.renameSession(id, trimmed).subscribe({
      next: () => this.refresh(),
      error: (err) => console.log(err),
    });
  }
}
