import { Component, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { History } from '../../features/history/history';
import { Toolkit } from '../../features/toolkit/toolkit';
import { Settings } from '../../features/settings/settings';
import { Speakers } from '../../features/speakers/speakers';

type PanelId = 'history' | 'toolkit' | 'speakers' | 'settings';

interface PanelTab {
  id: PanelId;
  label: string;
  icon: string;
}

@Component({
  selector: 'app-side',
  imports: [MatIconModule, History, Toolkit, Settings, Speakers],
  templateUrl: './side.html',
  styleUrl: './side.css',
})
export class Side {
  protected readonly tabs: PanelTab[] = [
    { id: 'history', label: 'History', icon: 'history' },
    // { id: 'toolkit', label: 'Toolkit', icon: 'build' },
    { id: 'speakers', label: 'Speakers', icon: 'group' },
    { id: 'settings', label: 'Settings', icon: 'tune' },
  ];

  protected readonly activePanel = signal<PanelId>('history');

  selectPanel(id: PanelId): void {
    this.activePanel.set(id);
  }
}
