import "@testing-library/jest-dom/vitest";
import { expect } from "vitest";

/**
 * Custom vitest matcher: toHaveNoA11yViolations
 *
 * Requires axe-core to be installed (`pnpm add -D axe-core`).
 * Runs the WCAG 2.1 AA ruleset on the rendered DOM.
 *
 * Usage:
 *   const { container } = render(<MyComponent />);
 *   await expect(container).toHaveNoA11yViolations();
 *
 * The matcher dynamically imports axe-core so tests that don't use
 * a11y assertions still work even if axe isn't installed yet.
 */

interface A11yAssertion {
  pass: boolean;
  message: () => string;
}

// Cache the loaded module (or null if axe-core is unavailable).
// Typed as `any` because axe-core is an optional dev dependency and may
// not be installed in every environment.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let axeCache: any = undefined;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function loadAxe(): Promise<any> {
  if (axeCache !== undefined) return axeCache;
  try {
    // Dynamic specifier prevents TypeScript from resolving the module
    // at compile time when it isn't installed.
    const moduleName = "axe-core";
    const mod = await import(/* @vite-ignore */ moduleName);
    axeCache = mod.default ?? mod;
  } catch {
    axeCache = null;
  }
  return axeCache;
}

async function toHaveNoA11yViolations(
  this: unknown,
  received: Element,
  options?: Record<string, unknown>,
): Promise<A11yAssertion> {
  const axe = await loadAxe();
  if (!axe) {
    return {
      pass: false,
      message: () =>
        "axe-core is not installed. Run `pnpm add -D axe-core` in apps/web/ " +
        "to enable accessibility testing.",
    };
  }

  const defaultOptions = {
    runOnly: {
      type: "tag",
      values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
    },
    ...options,
  };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let results: any;
  try {
    results = await axe.run(received, defaultOptions);
  } catch (err) {
    return {
      pass: false,
      message: () => `axe.run threw an error: ${(err as Error).message}`,
    };
  }

  const violations = results.violations ?? [];
  const pass = violations.length === 0;

  if (pass) {
    return {
      pass: true,
      message: () => "Expected accessibility violations but found none.",
    };
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const formatted = violations
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    .map((v: any) => {
      const nodes = (v.nodes || [])
        .slice(0, 3)
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .map((n: any) => `    ${n.html}\n      ${n.failureSummary}`)
        .join("\n");
      return `  [${v.impact}] ${v.id}: ${v.description}\n${nodes}`;
    })
    .join("\n\n");

  return {
    pass: false,
    message: () =>
      `Expected no accessibility violations but found ${violations.length}:\n\n${formatted}\n\nHelp: https://dequeuniversity.com/rules/axe/`,
  };
}

expect.extend({ toHaveNoA11yViolations });

// TypeScript augmentation for the custom matcher
declare module "vitest" {
  interface Assertion {
    toHaveNoA11yViolations(options?: Record<string, unknown>): Promise<void>;
  }
  interface AsymmetricMatchersContaining {
    toHaveNoA11yViolations(options?: Record<string, unknown>): Promise<void>;
  }
}
