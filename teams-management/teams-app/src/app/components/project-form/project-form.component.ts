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

  // Repos are mandatory at creation (>=1). A project manager may pick any number
  // from the admin global whitelist and/or add ad-hoc URLs. `selectedRepos` is
  // the working set the form submits; `whitelist` seeds the checkboxes.
  whitelist: string[] = [];
  selectedRepos: string[] = [];
  newRepoUrl = '';

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

  addAdHocRepo() {
    const url = this.newRepoUrl.trim();
    if (!url) {
      return;
    }
    if (!/^(https?:\/\/|git@)/.test(url)) {
      this.errorMessage = 'Repo URL must start with https:// or git@';
      return;
    }
    if (!this.selectedRepos.includes(url)) {
      this.selectedRepos.push(url);
    }
    this.newRepoUrl = '';
    this.errorMessage = '';
  }

  removeRepo(repo: string) {
    this.selectedRepos = this.selectedRepos.filter((r) => r !== repo);
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
        this.newRepoUrl = '';
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
