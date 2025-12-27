# Product Guidelines - WingetGui

## Visual Identity
- **Theme:** Forced Dark Mode. High-contrast pure blacks (#000000) for the background with deep slate surfaces.
- **Accents:** Neon blue (#00F2FF) for primary borders and highlights; Electric Green (#39FF14) for successful actions.
- **Typography:** Monospaced fonts (e.g., Consolas or Cascadia Code) for headers and data tables to reinforce the "terminal" aesthetic.
- **Glow Effects:** Active update rows should feature a subtle neon green pulse or glow animation to indicate work in progress.

## UI Components
- **Buttons:** "Command-Center" style. Large, prominent buttons with thick high-contrast borders and clear hover states.
- **Data Table:** Grid lines should be minimal or dim neon to keep focus on the text. Checkboxes should be high-contrast neon blue.
- **Integrated Console:** Styled like a standard terminal (black background, light grey text) but embedded seamlessly at the bottom of the layout.

## Communication & Tone
- **Voice:** Friendly and Action-Oriented.
- **Style:** Clear, helpful status updates (e.g., "Checking for updates..." instead of "Executing winget -v").
- **Error Handling:** Use plain English to explain what went wrong and how to fix it, avoiding raw stack traces in the main UI status bar.

## Design Principles
- **Clarity Over Clutter:** Despite the "Cyber" look, prioritize the readability of the winget data.
- **Immediate Response:** The UI should feel snappy; use animations sparingly (mostly for status indicators).
- **No Mystery Meat:** Icons should be accompanied by text or be extremely standard to ensure the "Personal Productivity" goal is met.
