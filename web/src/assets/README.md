# Renderer Assets

`src/assets/` stores image assets imported by the renderer through Vite.

Use this directory for production runtime assets that the app UI renders directly. Design references, mockups, and production candidates that still need handoff belong in `docs/design-assets/<feature>/` first. After an asset is accepted for product use, copy or move it here and import it from React/TypeScript.

Current groups:

- `brand/`: Novel brand mark and future app identity assets.
- `illustrations/novel/`: Novel brand illustrations for empty states and feature guidance.
- `library-covers/`: production 2:3 cover presets for the Library book-card grid.
- `workbench/`: production Workbench-specific runtime assets such as generation-state animation exports.
