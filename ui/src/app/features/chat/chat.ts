import { Component, ElementRef, computed, signal, viewChild, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { Observable, map, of, tap } from 'rxjs';
import { JobService, JobTurn } from '../../services/jobs.service';
import { SessionDetail, SessionJob, SessionsService } from '../../services/sessions.service';
import { SessionSelectionService } from '../../services/session-selection.service';
import { TimeSettingsService } from '../../services/time-settings.service';

export interface TranscriptNote {
  id: string;
  text: string;
  time: Date;
  speaker?: string;
}

interface JobLike {
  status: string;
  transcript: string | null;
  error_message: string | null;
  created_at: string | null;
  turns: JobTurn[];
}

function formatSpeakerLabel(label: string): string {
  const match = label.match(/(\d+)$/);
  if (match) {
    return `Speaker ${parseInt(match[1], 10) + 1}`;
  }
  return label;
}

@Component({
  selector: 'app-chat',
  imports: [CommonModule, FormsModule, MatIconModule],
  templateUrl: './chat.html',
  styleUrl: './chat.css',
})
export class Chat {
  private readonly dialogueEl = viewChild<ElementRef<HTMLDivElement>>('dialogueRef');

  protected readonly notes = signal<TranscriptNote[]>([]);
  protected readonly draft = signal('');
  protected readonly isRecording = signal(false);
  protected readonly attachments = signal<string[]>([]);
  protected readonly copied = signal(false);

  private readonly currentSessionId = signal<string | null>(null);
  private readonly pollHandles = new Map<string, ReturnType<typeof setInterval>>();

  private mediaRecorder: MediaRecorder | null = null;
  private recordedChunks: Blob[] = [];

  protected readonly tzOffset;

  constructor(
    private jobService: JobService,
    private sessionsService: SessionsService,
    private sessionSelection: SessionSelectionService,
    private timeSettings: TimeSettingsService
  ) {
    this.tzOffset = computed(() => this.timeSettings.formatOffsetForDatePipe());

    effect(() => {
      this.notes();
      queueMicrotask(() => {
        const el = this.dialogueEl()?.nativeElement;
        if (el) el.scrollTop = el.scrollHeight;
      });
    });

    effect(() => {
      const sessionId = this.sessionSelection.selectedSessionId();
      if (sessionId) {
        this.loadHistoricalSession(sessionId);
      }
    });
  }

  private ensureSession(): Observable<string> {
    const existing = this.currentSessionId();
    if (existing) return of(existing);

    return this.sessionsService.createSession().pipe(
      map((response) => response.session_id),
      tap((id) => this.currentSessionId.set(id))
    );
  }

  private loadHistoricalSession(sessionId: string): void {
    this.sessionsService.getSession(sessionId).subscribe({
      next: (session) => {
        this.currentSessionId.set(sessionId);
        this.notes.set(this.buildNotesFromSession(session));
      },
      error: (err) => console.log(err),
    });
  }

  private buildNotesFromSession(session: SessionDetail): TranscriptNote[] {
    const jobNotes = session.jobs.flatMap((job) => this.buildNotesFromJob(job.job_id, job));
    const manualNotes: TranscriptNote[] = session.notes.map((note) => ({
      id: `note-${note.note_id}`,
      text: note.text,
      time: note.created_at ? new Date(note.created_at) : new Date(),
    }));

    return [...jobNotes, ...manualNotes].sort((a, b) => a.time.getTime() - b.time.getTime());
  }

  private buildNotesFromJob(idPrefix: string, job: JobLike | SessionJob): TranscriptNote[] {
    if (job.status === 'failed') {
      return [{ id: idPrefix, text: `Transcription failed: ${job.error_message ?? 'unknown error'}`, time: new Date() }];
    }

    if (job.status !== 'done') {
      return [{ id: idPrefix, text: `Transcription ${job.status}…`, time: new Date() }];
    }

    // Turns don't carry their own wall-clock time - the job's created_at is
    // the only real timestamp we have, so each turn's time is that plus how
    // far into the recording it occurred. Using "now" here (as before) made
    // every line in a reopened past session show the current time instead
    // of when the recording actually happened.
    const recordedAt = job.created_at ? new Date(job.created_at) : new Date();

    const turnsWithText = job.turns.filter((t) => t.text && t.text.trim());
    if (turnsWithText.length > 0) {
      return turnsWithText.map((turn, i) => ({
        id: `${idPrefix}-turn-${i}`,
        text: turn.text!.trim(),
        time: new Date(recordedAt.getTime() + turn.start_time * 1000),
        speaker: formatSpeakerLabel(turn.speaker_label),
      }));
    }

    return [{ id: idPrefix, text: job.transcript ?? '(empty transcript)', time: recordedAt }];
  }

  uploadFile(file: File): void {
    if (!file) return;

    this.ensureSession().subscribe({
      next: (sessionId) => {
        this.jobService.uploadJob(file, sessionId).subscribe({
          next: (response) => {
            const jobId = response.job_id;

            this.notes.update((current) => [
              ...current,
              { id: jobId, text: 'Queued for transcription…', time: new Date() },
            ]);

            this.pollJob(jobId);
          },
          error: (err) => console.log(err),
        });
      },
      error: (err) => console.log(err),
    });
  }

  private pollJob(jobId: string): void {
    const handle = setInterval(() => {
      this.jobService.getJob(jobId).subscribe({
        next: (job) => {
          const replacementNotes = this.buildNotesFromJob(jobId, job);
          this.notes.update((current) => {
            const index = current.findIndex((note) => note.id === jobId);
            if (index === -1) return current;
            return [...current.slice(0, index), ...replacementNotes, ...current.slice(index + 1)];
          });

          if (job.status === 'done' || job.status === 'failed') {
            clearInterval(this.pollHandles.get(jobId));
            this.pollHandles.delete(jobId);
          }
        },
        error: (err) => {
          console.log(err);
          clearInterval(this.pollHandles.get(jobId));
          this.pollHandles.delete(jobId);
          this.notes.update((current) =>
            current.map((note) =>
              note.id === jobId ? { ...note, text: 'Transcription failed.' } : note
            )
          );
        },
      });
    }, 2000);

    this.pollHandles.set(jobId, handle);
  }

  async toggleRecording():Promise<void>{
    if(this.isRecording()){
      this.mediaRecorder?.stop();
      this.isRecording.set(false);
      return;
    }

    try{
      const stream = await navigator.mediaDevices.getUserMedia({audio: true})
      this.recordedChunks = []

      this.mediaRecorder = new MediaRecorder(stream)

      this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size>0){
          this.recordedChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = () => {
        const audioBlob = new Blob(this.recordedChunks, {type: "audio/webm"});

        const audioFile = new File([audioBlob], 'recording.webm' ,{ type: 'audio/webm' });

        this.uploadFile(audioFile);

        stream.getTracks().forEach(track => track.stop())
      };

      this.mediaRecorder.start()
      this.isRecording.set(true);
    } catch (error) {
      console.error('Failed to record audio: ', error);
      this.notes.update((current) => [
        ...current,
        { id: crypto.randomUUID(), text: 'Could not access microphone.', time: new Date() },
      ]);
    }
  }

  updateDraft(value: string): void {
    this.draft.set(value);
  }

  submitNote(event: Event): void {
    event.preventDefault();
    const text = this.draft().trim();
    if (!text) return;

    this.draft.set('');

    this.ensureSession().subscribe({
      next: (sessionId) => {
        this.sessionsService.addNote(sessionId, text).subscribe({
          next: (note) => {
            this.notes.update((current) => [
              ...current,
              {
                id: `note-${note.note_id}`,
                text: note.text,
                time: note.created_at ? new Date(note.created_at) : new Date(),
              },
            ]);
          },
          error: (err) => console.log(err),
        });
      },
      error: (err) => console.log(err),
    });
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    const names = files.map((f) => f.name);
    if (names.length) {
      this.attachments.update((current) => [...current, ...names]);
    }
    input.value = '';

    files.forEach((file) => this.uploadFile(file));
  }

  removeAttachment(name: string): void {
    this.attachments.update((current) => current.filter((n) => n !== name));
  }

  startNewSession(): void {
    this.pollHandles.forEach((handle) => clearInterval(handle));
    this.pollHandles.clear();

    this.currentSessionId.set(null);
    this.notes.set([]);
    this.draft.set('');
    this.attachments.set([]);
  }

  async copyText(): Promise<void> {
    const text = this.buildTranscriptText();
    if (!text) return;
    await navigator.clipboard.writeText(text);
    this.copied.set(true);
    setTimeout(() => this.copied.set(false), 1500);
  }

  saveAsTxt(): void {
    const text = this.buildTranscriptText();
    if (!text) return;
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `transcript-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  }

  private formatTime(date: Date): string {
    // Plain arithmetic on the configured offset, not toLocaleTimeString()/
    // Intl - those can be spoofed to UTC by browser fingerprinting
    // resistance, which is exactly what caused this to be wrong before.
    const shifted = new Date(date.getTime() + this.timeSettings.utcOffsetMinutes() * 60000);
    let hours = shifted.getUTCHours();
    const minutes = shifted.getUTCMinutes();
    const period = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    return `${hours}:${String(minutes).padStart(2, '0')} ${period}`;
  }

  private buildTranscriptText(): string {
    return this.notes()
      .map((n) => `[${this.formatTime(n.time)}]${n.speaker ? ' ' + n.speaker + ':' : ''} ${n.text}`)
      .join('\n');
  }
}
