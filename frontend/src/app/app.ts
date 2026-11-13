import { ChangeDetectionStrategy, Component, DOCUMENT, inject, OnInit } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { filter } from 'rxjs';
import { ServerStatusStore } from './core/server-status.store';
import { AppIcon } from './shared/icon';

interface NavItem {
  path: string;
  label: string;
  icon: string;
}

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatButtonModule, AppIcon],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  protected readonly server = inject(ServerStatusStore);
  private readonly router = inject(Router);
  private readonly doc = inject(DOCUMENT);

  protected readonly nav: NavItem[] = [
    { path: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
    { path: '/workspace', label: 'Policy workspace', icon: 'folder' },
    { path: '/chat', label: 'Ask questions', icon: 'chat' },
    { path: '/report', label: 'Gap report', icon: 'report' },
    { path: '/audit', label: 'Audit', icon: 'audit' },
  ];

  ngOnInit(): void {
    this.server.load();
    // Move focus to the main region after navigation so keyboard/screen-reader users land on the new page.
    let first = true;
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {
      if (first) {
        first = false;
        return;
      }
      this.doc.getElementById('main')?.focus({ preventScroll: true });
    });
  }
}
