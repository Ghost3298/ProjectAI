import { Component, OnDestroy, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { SpeakersService, SpeakerSummary } from '../../services/speakers.service';

const POLL_INTERVAL_MS = 3000;

@Component({
  selector: 'app-speakers',
  imports: [MatIconModule],
  templateUrl: './speakers.html',
  styleUrl: './speakers.css',
})
export class Speakers implements OnDestroy {
  protected readonly speakers = signal<SpeakerSummary[]>([]);
  protected readonly nameDraft = signal('');
  protected readonly isRecording = signal(false);

  private readonly pollHandle: ReturnType<typeof setInterval>;
  private mediaRecorder: MediaRecorder | null = null;
  private recordedChunks: Blob[] = [];

  constructor(private speakersService: SpeakersService) {
    this.refresh();
    this.pollHandle = setInterval(() => this.refresh(), POLL_INTERVAL_MS);
  }

  ngOnDestroy(): void {
    clearInterval(this.pollHandle);
  }

  private refresh(): void {
    this.speakersService.listSpeakers().subscribe({
      next: (speakers) => this.speakers.set(speakers),
      error: (err) => console.log(err),
    });
  }

  updateNameDraft(value: string): void {
    this.nameDraft.set(value);
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (file) this.enroll(file);
  }

  async toggleRecording(): Promise<void> {
    if (this.isRecording()) {
      this.mediaRecorder?.stop();
      this.isRecording.set(false);
      return;
    }

    const name = this.nameDraft().trim();
    if (!name) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.recordedChunks = [];
      this.mediaRecorder = new MediaRecorder(stream);

      this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
        if (event.data && event.data.size > 0) this.recordedChunks.push(event.data);
      };

      this.mediaRecorder.onstop = () => {
        const audioBlob = new Blob(this.recordedChunks, { type: 'audio/webm' });
        const audioFile = new File([audioBlob], `${name}-sample.webm`, { type: 'audio/webm' });
        this.enroll(audioFile);
        stream.getTracks().forEach((track) => track.stop());
      };

      this.mediaRecorder.start();
      this.isRecording.set(true);
    } catch (error) {
      console.error('Failed to record audio: ', error);
    }
  }

  private enroll(file: File): void {
    const name = this.nameDraft().trim();
    if (!name) return;

    this.speakersService.enrollSpeaker(name, file).subscribe({
      next: () => {
        this.nameDraft.set('');
        this.refresh();
      },
      error: (err) => console.log(err),
    });
  }

  deleteSpeaker(id: string, name: string): void {
    if (!window.confirm(`Delete "${name}"? Recognized names already saved on past transcripts won't change, but this speaker won't be matched anymore.`)) {
      return;
    }

    this.speakersService.deleteSpeaker(id).subscribe({
      next: () => this.refresh(),
      error: (err) => console.log(err),
    });
  }
}
