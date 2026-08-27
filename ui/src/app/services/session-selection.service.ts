import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class SessionSelectionService {
    readonly selectedSessionId = signal<string | null>(null);

    select(sessionId: string): void {
        this.selectedSessionId.set(sessionId);
    }
}
