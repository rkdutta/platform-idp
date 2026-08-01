// src/app/components/project-form/project-form.component.ts
import { Component, Output, EventEmitter, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ProjectsService } from '../../services/projects.service';
import { ProjectCreate } from '../../models/project.model';

@Component({
  selector: 'app-project-form',
  templateUrl: './project-form.component.html',
  styleUrls: ['./project-form.component.css']
})
export class ProjectFormComponent implements OnInit {
  @Output() projectCreated = new EventEmitter<void>();

  projectForm: FormGroup;
  isSubmitting = false;
  errorMessage = '';

  // Repos are mandatory at creation (>=1). A project manager picks from the admin
  // global whitelist (repos connected via the GitHub App). To use a brand-new
  // repo, connect it on GitHub first (global whitelist, or the created project's
  // "Add repos from GitHub"). `selectedRepos` is the working set the form submits.
  whitelist: string[] = [];
  selectedRepos: string[] = [];

  constructor(
    private fb: FormBuilder,
    private projectsService: ProjectsService
  ) {
    this.projectForm = this.fb.group({
      name: ['', [Validators.required, Validators.minLength(2)]]
    });
  }

  ngOnInit() {
    this.projectsService.getGlobalSourceRepos().subscribe({
      next: (repos) => (this.whitelist = repos),
      // The whitelist is a convenience; a load failure must not block creation
      // (the manager can still add ad-hoc repos).
      error: (err) => console.error('Failed to load repo whitelist:', err),
    });
  }

  /** Whitelisted repos not yet selected — the pickable options. */
  get availableWhitelist(): string[] {
    return this.whitelist.filter((r) => !this.selectedRepos.includes(r));
  }

  addFromWhitelist(repo: string) {
    if (repo && !this.selectedRepos.includes(repo)) {
      this.selectedRepos.push(repo);
    }
  }

  removeRepo(repo: string) {
    this.selectedRepos = this.selectedRepos.filter((r) => r !== repo);
  }

  /** Compact chip label for a repo URL — "owner/repo", host+".git" stripped.
   *  Full URL stays available via the chip's title on hover. */
  shortRepo(url: string): string {
    try {
      const u = new URL(url);
      return u.pathname.replace(/^\/+/, "").replace(/\.git$/, "") || u.hostname;
    } catch {
      return url.replace(/^https?:\/\//, "").replace(/\.git$/, "");
    }
  }

  onSubmit() {
    if (this.projectForm.invalid) {
      return;
    }
    if (this.selectedRepos.length === 0) {
      this.errorMessage = 'Add at least one source repository.';
      return;
    }

    this.isSubmitting = true;
    this.errorMessage = '';

    const projectData: ProjectCreate = {
      name: this.projectForm.value.name.trim(),
      source_repos: [...this.selectedRepos],
    };

    this.projectsService.createProject(projectData).subscribe({
      next: () => {
        this.projectForm.reset();
        this.selectedRepos = [];
        this.projectCreated.emit();
        this.isSubmitting = false;
      },
      error: (error) => {
        this.errorMessage = error;
        this.isSubmitting = false;
      }
    });
  }

  get name() {
    return this.projectForm.get('name');
  }
}
