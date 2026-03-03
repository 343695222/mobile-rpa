import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import type {
  Action,
  OperationTemplate,
  TemplateParam,
  TemplateStep,
  ResolvedTemplate,
  TemplateSummary,
  ValidationResult,
  ExecutionHistory,
} from "./types";

// === TemplateEngine Interface ===

export interface TemplateEngine {
  loadTemplates(dir: string): Promise<OperationTemplate[]>;
  getTemplate(name: string): OperationTemplate | undefined;
  listTemplates(): TemplateSummary[];
  saveTemplate(template: OperationTemplate, dir: string): Promise<void>;
  validateTemplate(template: unknown): ValidationResult;
  resolveParams(template: OperationTemplate, params: Record<string, string>): ResolvedTemplate;
  generateFromHistory(history: ExecutionHistory, taskName: string): OperationTemplate;
  findMatchingTemplate(taskDescription: string): OperationTemplate | undefined;
  serialize(template: OperationTemplate): string;
  deserialize(json: string): OperationTemplate;
}

// === DefaultTemplateEngine Implementation ===

export class DefaultTemplateEngine implements TemplateEngine {
  private templates: Map<string, OperationTemplate> = new Map();

  validateTemplate(template: unknown): ValidationResult {
    const errors: string[] = [];

    if (typeof template !== "object" || template === null || Array.isArray(template)) {
      return { valid: false, errors: ["Template must be a non-null object"] };
    }

    const t = template as Record<string, unknown>;

    // Check name
    if (typeof t.name !== "string" || t.name.trim() === "") {
      errors.push("Missing or invalid field: name (must be a non-empty string)");
    }

    // Check description
    if (typeof t.description !== "string" || t.description.trim() === "") {
      errors.push("Missing or invalid field: description (must be a non-empty string)");
    }

    // Check params
    if (!Array.isArray(t.params)) {
      errors.push("Missing or invalid field: params (must be an array)");
    } else {
      for (let i = 0; i < t.params.length; i++) {
        const p = t.params[i];
        if (typeof p !== "object" || p === null) {
          errors.push(`params[${i}]: must be an object`);
          continue;
        }
        if (typeof p.name !== "string" || p.name.trim() === "") {
          errors.push(`params[${i}]: missing or invalid field 'name'`);
        }
        if (typeof p.description !== "string") {
          errors.push(`params[${i}]: missing or invalid field 'description'`);
        }
        if (typeof p.required !== "boolean") {
          errors.push(`params[${i}]: missing or invalid field 'required'`);
        }
      }
    }

    // Check steps
    if (!Array.isArray(t.steps)) {
      errors.push("Missing or invalid field: steps (must be an array)");
    } else {
      for (let i = 0; i < t.steps.length; i++) {
        const s = t.steps[i];
        if (typeof s !== "object" || s === null) {
          errors.push(`steps[${i}]: must be an object`);
          continue;
        }
        if (typeof s.order !== "number") {
          errors.push(`steps[${i}]: missing or invalid field 'order'`);
        }
        if (typeof s.action !== "object" || s.action === null) {
          errors.push(`steps[${i}]: missing or invalid field 'action'`);
        }
        if (typeof s.description !== "string") {
          errors.push(`steps[${i}]: missing or invalid field 'description'`);
        }
      }
    }

    // Check metadata (optional but if present must be valid)
    if (t.metadata !== undefined) {
      if (typeof t.metadata !== "object" || t.metadata === null) {
        errors.push("Invalid field: metadata (must be an object)");
      } else {
        const m = t.metadata as Record<string, unknown>;
        if (typeof m.createdAt !== "string") {
          errors.push("metadata: missing or invalid field 'createdAt'");
        }
        if (m.source !== "manual" && m.source !== "auto-generated") {
          errors.push("metadata: 'source' must be 'manual' or 'auto-generated'");
        }
      }
    }

    return { valid: errors.length === 0, errors };
  }

  serialize(template: OperationTemplate): string {
    return JSON.stringify(template, null, 2);
  }

  deserialize(json: string): OperationTemplate {
    let parsed: unknown;
    try {
      parsed = JSON.parse(json);
    } catch {
      throw new Error("Invalid JSON string");
    }

    const result = this.validateTemplate(parsed);
    if (!result.valid) {
      throw new Error(`Invalid template: ${result.errors.join("; ")}`);
    }

    return parsed as OperationTemplate;
  }

  resolveParams(template: OperationTemplate, params: Record<string, string>): ResolvedTemplate {
    // Build effective params: apply defaults first, then provided values
    const effectiveParams: Record<string, string> = {};
    for (const p of template.params) {
      if (p.defaultValue !== undefined) {
        effectiveParams[p.name] = p.defaultValue;
      }
    }
    Object.assign(effectiveParams, params);

    // Check for missing required params
    const missing = template.params
      .filter((p) => p.required && !(p.name in effectiveParams))
      .map((p) => p.name);

    if (missing.length > 0) {
      throw new Error(`Missing required parameters: ${missing.join(", ")}`);
    }

    // Deep clone steps and replace placeholders
    const resolvedSteps: TemplateStep[] = JSON.parse(JSON.stringify(template.steps));

    for (const step of resolvedSteps) {
      step.description = this.replacePlaceholders(step.description, effectiveParams);
      if (step.expectedScreenHint) {
        step.expectedScreenHint = this.replacePlaceholders(step.expectedScreenHint, effectiveParams);
      }
      // Replace placeholders in action text fields
      step.action = JSON.parse(
        this.replacePlaceholders(JSON.stringify(step.action), effectiveParams)
      );
    }

    return { name: template.name, steps: resolvedSteps };
  }

  private replacePlaceholders(text: string, params: Record<string, string>): string {
    return text.replace(/\{\{(\w+)\}\}/g, (match, paramName) => {
      if (paramName in params) {
        return params[paramName];
      }
      return match; // Leave unresolved if not in params
    });
  }

  async loadTemplates(dir: string): Promise<OperationTemplate[]> {
    const loaded: OperationTemplate[] = [];

    let entries: string[];
    try {
      entries = await readdir(dir);
    } catch {
      return loaded;
    }

    const jsonFiles = entries.filter((f) => f.endsWith(".json"));

    for (const file of jsonFiles) {
      try {
        const content = await readFile(join(dir, file), "utf-8");
        const parsed = JSON.parse(content);
        const result = this.validateTemplate(parsed);
        if (result.valid) {
          const template = parsed as OperationTemplate;
          this.templates.set(template.name, template);
          loaded.push(template);
        }
      } catch {
        // Skip invalid files
        continue;
      }
    }

    return loaded;
  }

  getTemplate(name: string): OperationTemplate | undefined {
    return this.templates.get(name);
  }

  listTemplates(): TemplateSummary[] {
    return Array.from(this.templates.values()).map((t) => ({
      name: t.name,
      description: t.description,
      params: t.params,
    }));
  }

  async saveTemplate(template: OperationTemplate, dir: string): Promise<void> {
    await mkdir(dir, { recursive: true });
    const filePath = join(dir, `${template.name}.json`);
    await writeFile(filePath, this.serialize(template), "utf-8");
    this.templates.set(template.name, template);
  }

  generateFromHistory(history: ExecutionHistory, taskName: string): OperationTemplate {
    const params: TemplateParam[] = [];
    let paramIndex = 0;

    const steps: TemplateStep[] = history.steps.map((step, i) => {
      // Deep clone the action so we don't mutate the original
      let action: Action = JSON.parse(JSON.stringify(step.action));
      let description = `Step ${i + 1}: ${step.action.type}`;

      // Identify variable parts: input_text actions have user-provided text
      if (action.type === "input_text") {
        const paramName = `param_${paramIndex}`;
        paramIndex++;

        params.push({
          name: paramName,
          description: `Text input from step ${i + 1}`,
          required: true,
          defaultValue: action.text,
        });

        // Replace the text with a placeholder
        (action as { type: "input_text"; text: string }).text = `{{${paramName}}}`;
        description = `Input {{${paramName}}}`;
      }

      return {
        order: i + 1,
        action,
        description,
      };
    });

    return {
      name: taskName.toLowerCase().replace(/\s+/g, "-"),
      description: `Auto-generated template from task: ${taskName}`,
      params,
      steps,
      metadata: {
        createdAt: new Date().toISOString(),
        source: "auto-generated",
        taskDescription: taskName,
      },
    };
  }

  findMatchingTemplate(taskDescription: string): OperationTemplate | undefined {
    if (!taskDescription.trim()) return undefined;

    const queryWords = taskDescription.toLowerCase().split(/\s+/).filter(Boolean);
    let bestMatch: OperationTemplate | undefined;
    let bestScore = 0;

    for (const template of this.templates.values()) {
      // Build a searchable text from template name, description, and metadata
      const searchText = [
        template.name,
        template.description,
        template.metadata?.taskDescription ?? "",
      ]
        .join(" ")
        .toLowerCase();

      // Score = number of query words found in the search text
      const score = queryWords.filter((w) => searchText.includes(w)).length;

      if (score > bestScore) {
        bestScore = score;
        bestMatch = template;
      }
    }

    // Require at least one word match
    return bestScore > 0 ? bestMatch : undefined;
  }
}
