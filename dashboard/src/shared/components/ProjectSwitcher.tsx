import { useEffect, useMemo } from "react";

import { Project } from "@/shared/api/types";
import { clearActiveProjectId, getActiveProjectId, setActiveProjectId } from "@/shared/utils/storage";

type ProjectSwitcherProps = {
  tenantId: string;
  projects: Project[];
  value: string;
  onChange: (projectId: string) => void;
  disabled?: boolean;
  className?: string;
};

export function ProjectSwitcher({
  tenantId,
  projects,
  value,
  onChange,
  disabled,
  className,
}: ProjectSwitcherProps): JSX.Element {
  const hasProjects = projects.length > 0;
  const projectIds = useMemo(() => new Set(projects.map((project) => project.id)), [projects]);

  useEffect(() => {
    if (!tenantId) {
      return;
    }

    if (!hasProjects) {
      clearActiveProjectId(tenantId);
      if (value) {
        onChange("");
      }
      return;
    }

    if (value && projectIds.has(value)) {
      setActiveProjectId(tenantId, value);
      return;
    }

    const persisted = getActiveProjectId(tenantId);
    if (persisted && projectIds.has(persisted)) {
      onChange(persisted);
      return;
    }

    const fallback = projects[0].id;
    setActiveProjectId(tenantId, fallback);
    onChange(fallback);
  }, [tenantId, projects, value, onChange, hasProjects, projectIds]);

  return (
    <label className={`inline-flex min-w-64 items-center gap-2 text-sm text-slate-600 ${className ?? ""}`}>
      <span className="font-medium text-slate-700">Project</span>
      <select
        value={value}
        disabled={disabled || !hasProjects}
        onChange={(event) => {
          const nextProjectId = event.target.value;
          onChange(nextProjectId);
          if (tenantId && nextProjectId) {
            setActiveProjectId(tenantId, nextProjectId);
          }
        }}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800"
      >
        {!hasProjects ? <option value="">No projects</option> : null}
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
    </label>
  );
}
