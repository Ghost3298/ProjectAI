import { Component, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

export interface TranscriptSession {
  id: string;
  title: string;
  createdAt: Date;
  durationLabel: string;
}

@Component({
  selector: 'app-history',
  imports: [MatIconModule],
  templateUrl: './history.html',
  styleUrl: './history.css',
})
export class History {
  /** Populated once sessions are actually recorded; starts empty on purpose. */
  protected readonly sessions = signal<TranscriptSession[]>([]);
  protected readonly query = signal('');

  updateQuery(value: string): void {
    this.query.set(value);
  }
}
