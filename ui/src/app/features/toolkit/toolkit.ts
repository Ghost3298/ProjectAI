import { Component, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

export interface ConnectedTool {
  id: string;
  name: string;
  icon: string;
}

@Component({
  selector: 'app-toolkit',
  imports: [MatIconModule],
  templateUrl: './toolkit.html',
  styleUrl: './toolkit.css',
})
export class Toolkit {
  /** No tools are wired up yet — left empty until a real integration is added. */
  protected readonly tools = signal<ConnectedTool[]>([]);
}
