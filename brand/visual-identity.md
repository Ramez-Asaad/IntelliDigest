# IntelliDigest — Visual Identity

tone: calm, precise, quietly premium
imagery: minimal with generous negative space; cool blues cooling into cyan; soft depth and clean diagrams over stock photography

## Personality
Minimal · Calm · Premium — the product feels considered and unhurried. It shows
one clear action at a time, trusts whitespace, and never shouts. Confidence
through restraint, not decoration.

## Do
- Keep layouts uncluttered; let the logo breathe (clear space = logo height).
- Use the palette in `color-system.json` exactly — no eyeballed colors.
- Anchor screens in deep blue `#1E3A8A`; use cyan `#22D3EE` as a single focal accent.
- Prefer diagrams, structure, and real UI over stock imagery.

## Don't
- Stretch, rotate, or recolor the logo.
- Set body text below the `minContrast` ratio in `color-system.json`.
- Use cyan for text or long copy — it is an accent-fill color only.
- Add warm tones; the system is cool blue → cyan, end to end.

## Reference notes
Derived from the shipped product design tokens (`frontend/styles.css`) and the
technical-documentation system: deep-blue primary, cyan accent, Inter throughout,
layered light surfaces (`#F0F4F9` background, `#FFFFFF` cards, `#CEDAE6` borders).
On-brand examples: the architecture diagrams in `docs/documentation-src/` — flat
fills, thin borders, one accent per figure.
