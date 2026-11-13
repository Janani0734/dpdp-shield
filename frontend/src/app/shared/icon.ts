import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

const PATHS: Record<string, string> = {
  shield: 'M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3z',
  dashboard: 'M4 4h7v8H4zM13 4h7v5h-7zM13 11h7v9h-7zM4 14h7v6H4z',
  folder: 'M4 6h6l2 2h8v11H4z',
  chat: 'M4 5h16v11H10l-4 4v-4H4z',
  report: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7',
  audit: 'M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3zM9 12l2 2 4-4',
  upload: 'M12 16V5m0 0L8 9m4-4l4 4M5 19h14',
  trash: 'M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13',
  copy: 'M9 9h10v11H9zM5 15V5h10',
  alert: 'M12 4l9 16H3zM12 10v4M12 17v.01',
  check: 'M5 12l4 4 10-10',
  info: 'M12 3a9 9 0 100 18 9 9 0 000-18zM12 11v6M12 7.5v.01',
  x: 'M6 6l12 12M18 6L6 18',
  send: 'M4 12L20 4l-6 16-3-7z',
  refresh: 'M20 11a8 8 0 10-2.3 5.7M20 4v7h-7',
};

@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
      <path [attr.d]="path()" />
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      font-size: 1.15em;
      vertical-align: middle;
    }
  `,
})
export class AppIcon {
  readonly name = input.required<string>();
  protected readonly path = computed(() => PATHS[this.name()] ?? PATHS['info']);
}
