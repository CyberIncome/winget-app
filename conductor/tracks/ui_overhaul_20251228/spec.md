# Track Specification - UI/UX Overhaul: Modern Dark Mode & Glassmorphism

## Overview
Transform the current high-contrast "Matrix" interface into a modern, professional dark mode experience with glassmorphism touches, increased spacing, and refined typography.

## Technical Requirements

### 1. Visual Refresh (QSS)
- **Backgrounds:** Transition from #000000 to a deep navy/slate (#1A1B26).
- **Glass Effects:** Use `rgba(36, 40, 59, 200)` for surface containers with rounded corners (`border-radius: 12px`).
- **Typography:** Set the application font to 'Segoe UI' or 'Inter'. Only use 'Cascadia Code' for the console.
- **Accents:** Replace neon cyan with a softer blue (#7AA2F7) and emerald green (#9ECE6A) for the primary "Update All" button.

### 2. Layout & Spacing
- **Margins:** Increase window and container margins to 20px.
- **Table Refinement:** 
    - Remove vertical grid lines.
    - Add padding to cells.
    - Implement alternating row background colors for better readability.
- **Component Balancing:** 
    - Adjust the console height to be less dominant.
    - Add a split layout that feels more intentional.

### 3. Polish
- **Hover States:** Implement soft transitions for button hovers (e.g., subtle glow or brightness increase).
- **Icons:** (Optional but preferred) Add placeholder emoji or simple unicode characters if assets are not available to help with visual cues.
