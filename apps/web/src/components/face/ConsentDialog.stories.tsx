/**
 * Storybook stories for ConsentDialog (S11-004).
 *
 * NOTE: Storybook is not yet installed in apps/web as of S11-004.
 * This file is kept as inline pseudo-CSF3 documentation so that when
 * Storybook is added, the stories can be uncommented and wired up
 * without re-designing the variants.
 *
 * The three variants exercised by the live tests in __tests__/ are:
 *   - Default:    Enable button disabled, scroll hint visible
 *   - Scrolled:   Enable button enabled, scroll hint hidden
 *   - Submitting: Spinner on Enable, escape/backdrop-click blocked
 *
 * When Storybook lands, restore this file to:
 *
 *   import type { Meta, StoryObj } from "@storybook/react";
 *   import ConsentDialog from "./ConsentDialog";
 *
 *   const meta: Meta<typeof ConsentDialog> = {
 *     title: "Face/ConsentDialog",
 *     component: ConsentDialog,
 *   };
 *   export default meta;
 *
 *   type Story = StoryObj<typeof ConsentDialog>;
 *
 *   export const Default: Story = {
 *     args: { open: true, onClose: () => {}, onAccepted: () => {} },
 *     parameters: {
 *       mockData: {
 *         "/api/v1/settings/face-clustering/consent": {
 *           GET: {
 *             accepted: false,
 *             version: null,
 *             granted_at: null,
 *             revoked_at: null,
 *             current_text_version: "v1.0-DRAFT-2026-04",
 *             current_text: "...long text...",
 *           },
 *         },
 *       },
 *     },
 *   };
 *
 *   export const Scrolled: Story = { ... simulate scroll to bottom };
 *   export const Submitting: Story = { ... block POST for 10s };
 */

// This file intentionally has no runtime exports. It exists to mark the
// intended Storybook surface until the dev dependency is installed.
export {};
