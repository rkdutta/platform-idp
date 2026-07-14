// Manages the portal's light/dark theme. Persists the user's choice in
// localStorage and reflects it as a `data-theme` attribute on <html>, which the
// CSS custom properties in styles.css key off. Default is dark.
import { Injectable } from '@angular/core';

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'teams-portal-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private current: Theme = 'dark';

  constructor() {
    this.current = this.load();
    this.apply(this.current);
  }

  get theme(): Theme {
    return this.current;
  }

  get isDark(): boolean {
    return this.current === 'dark';
  }

  toggle(): void {
    this.set(this.current === 'dark' ? 'light' : 'dark');
  }

  set(theme: Theme): void {
    this.current = theme;
    this.apply(theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // localStorage may be unavailable (private mode) — theme still applies
      // for this session, it just won't persist.
    }
  }

  private apply(theme: Theme): void {
    document.documentElement.setAttribute('data-theme', theme);
  }

  private load(): Theme {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'light' || saved === 'dark') {
        return saved;
      }
    } catch {
      // ignore and fall through to default
    }
    return 'dark';
  }
}
