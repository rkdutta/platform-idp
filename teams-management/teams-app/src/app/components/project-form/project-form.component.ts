// src/app/components/project-form/project-form.component.ts
import { Component, Output, EventEmitter } from '@angular/core';
import { FormBuilder, FormGroup, Validators } from '@angular/forms';
import { ProjectsService } from '../../services/projects.service';
import { ProjectCreate } from '../../models/project.model';

@Component({
  selector: 'app-project-form',
  templateUrl: './project-form.component.html',
  styleUrls: ['./project-form.component.css']
})
export class ProjectFormComponent {
  @Output() projectCreated = new EventEmitter<void>();

  projectForm: FormGroup;
  isSubmitting = false;
  errorMessage = '';

  constructor(
    private fb: FormBuilder,
    private projectsService: ProjectsService
  ) {
    this.projectForm = this.fb.group({
      name: ['', [Validators.required, Validators.minLength(2)]]
    });
  }

  onSubmit() {
    if (this.projectForm.invalid) {
      return;
    }

    this.isSubmitting = true;
    this.errorMessage = '';

    // Repos are no longer required at creation — a project starts empty and the
    // owner registers a GitHub connection from its card to add repos later.
    const projectData: ProjectCreate = {
      name: this.projectForm.value.name.trim(),
      source_repos: [],
    };

    this.projectsService.createProject(projectData).subscribe({
      next: () => {
        this.projectForm.reset();
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
