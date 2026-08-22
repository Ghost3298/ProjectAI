import { Component, ElementRef, signal, viewChild, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { JobService } from '../../services/jobs.service';

export interface TranscriptNote {
  id: string;
  text: string;
  time: Date;
}

@Component({
  selector: 'app-chat',
  imports: [CommonModule, MatIconModule],
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

  private readonly pollHandles = new Map<string, ReturnType<typeof setInterval>>();

  private mediaRecorder: MediaRecorder | null = null;
  private recordedChunks: Blob[] = [];

  constructor(private jobService: JobService) {
    effect(() => {
      this.notes();
      queueMicrotask(() => {
        const el = this.dialogueEl()?.nativeElement;
        if (el) el.scrollTop = el.scrollHeight;
      });
    });
  }

  uploadFile(file: File): void {
    if (!file) return;

    this.jobService.uploadJob(file).subscribe({
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
  }

  private pollJob(jobId: string): void {
    const handle = setInterval(() => {
      this.jobService.getJob(jobId).subscribe({
        next: (job) => {
          this.notes.update((current) =>
            current.map((note) =>
              note.id === jobId
                ? {
                    ...note,
                    text:
                      job.status === 'done'
                        ? job.transcript ?? '(empty transcript)'
                        : `Transcription ${job.status}…`,
                  }
                : note
            )
          );

          if (job.status === 'done') {
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

    this.notes.update((current) => [
      ...current,
      { id: crypto.randomUUID(), text, time: new Date() },
    ]);
    this.draft.set('');
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

  private buildTranscriptText(): string {
    return this.notes()
      .map((n) => `[${n.time.toLocaleTimeString()}] ${n.text}`)
      .join('\n');
  }
}