# Design notes: OceanAI reference → ForgeAI

Source: https://oceanai.ai/ only, read on 2026-11-27 through the browser's computed styles and stylesheets. It is a
WordPress **Divi** site (child theme `ocean-ai-divi-child/style.css`, `et-core-unified` cache CSS), not Elementor.
"Measured" means the value was read from the live page. "ForgeAI" means the value is our own, because the reference has
no equivalent. No images, logos or copy were taken from the site.

## 1. What the reference uses (measured)

### Colour
| Role | Value | Where it appears |
|---|---|---|
| Theme colour | `#1363FA` | `<meta name="theme-color">` |
| Primary button | `#1758FC` (rgb 23,88,252) | "EXPLORE" / "BROCHURE" pills |
| Primary gradient | `linear-gradient(90deg, #0F6BFF, #256DFF)` | blue bands |
| Button glow | `rgba(0,98,255,0.25) 0 3px 8px` | primary buttons |
| Light accent blue | `#2EA3F2` | links / accents (Divi accent) |
| Indigo button | `#3B2FA6` | product "Explore" pills |
| Deep navy | `#050581` | product card |
| Near-black ink | `#191826` | product card |
| Green | `#1FAC6B` | product card |
| Crimson | `#C80330` | product card |
| Other product tints | `#6E68E2`, `#7F3DC3`, `#A31492`, `#C73059`, `#9C1B37`, `#0C59F5`, `#4B4B4B` | one colour per product card |
| Page background | `#FFFFFF` | body |
| Glass surface | `rgba(255,255,255,0.8)` | feature cards on the swirl background |
| Heading text | `#000000` | h1 / h2 on light |
| Sub-heading text | `#333333` | h3 |
| Body text | `#666666` | body, paragraphs (most frequent colour on the page) |
| Secondary text | `#4E4E4E`, `#888888` | captions, timeline year pills |
| Borders | `#D0D0D0`, `#ABABAB` | inputs and dividers |

There is no warning (amber) colour anywhere on the site. Success and danger only exist as product-card tints (`#1FAC6B`, `#C80330`).

### Typography
- Family: **Barlow** (Google Fonts, 100–900 + italics) on 100% of measured elements. Open Sans is loaded but unused in the visible page.
- Weights: 500 body (most common), 400, 600 buttons, 700 stats and section titles, 800 hero h1.
- Sizes: h1 60px / 60px line-height / 800; h2 40px / 700 (section) and 36px / 700 (product names); h3 30px / 400 (feature titles)
  and 18px / 500 (product subtitles); body 14px / 23.8px; stats numbers 34px / 700; stat labels 20px / 300; small 13px.

### Components
- **Buttons:** pill, radius 30px (product pills 50px), padding 10px 28px, 14px / 600, white text on `#1758FC`, glow shadow
  `rgba(0,98,255,.25) 0 3px 8px`. Product pills are uppercase (`EXPLORE`); hero pills are sentence-styled text.
- **Cards:** radius 25px, background `rgba(255,255,255,.8)`, shadow `rgba(0,0,0,.05) 0 1px 12px`. Product cards are solid
  colour blocks with a white 36px name, an 18px subtitle and an "Explore" pill.
- **Stats band:** white 34px / 700 numbers ("99%+", "50+", "10+", "30%+") with 20px / 300 labels, padding 20px 0.
- **Roadmap timeline:** year pills (`tl-year`): radius 999px, white background, `#888` 13px text, padding 6px 14px.
- **Radius values seen:** 0 (most layout), 8, 15, 20, 25, 30, 50, 999px.
- **Shadows seen:** `0 1px 12px rgba(0,0,0,.05)`, `0 3px 8px rgba(0,98,255,.25)`, `0 4px 6px rgba(0,0,0,.2)`, `0 40px 80px rgba(0,0,0,.25)`.
- **Spacing seen:** 6/14 (pills), 10/28 (buttons), 12/16, 20, 30, 40 (h2 bottom), 50px (section top).
- **Header:** transparent, 99px tall. **Footer:** transparent with contact call-to-action.
- **Imagery:** blue swirl/wave background images and ship photography (not reused).

### Tone of copy
Three-beat imperative headline ("Predict. Prevent. Perform."), one-line benefit subtitles, product = bold name + short
promise ("Effortless AI-driven Document Search"), big confident numbers with tiny labels, short calls to action
("Explore", "Schedule A Demo").

## 2. ForgeAI design system (what we built)

Same family as OceanAI: Barlow, the OceanAI blue, the same text greys, pill buttons with blue glow, 25px glass cards, a
stats band, icon cards, a year-pill-style timeline. Original elements are a navy maritime hero drawn in inline SVG
(sonar rings + wave lines, no photos), a pipeline stepper, a dark mode, and a full semantic state palette.

### Tokens (CSS variables in `web/styles.css`)
| Token | Light | Dark | Origin |
|---|---|---|---|
| `--primary` | `#1363FA` | `#5B93FF` | measured / ForgeAI (lighter for dark-mode contrast) |
| `--primary-strong` | `#0F4FD6` | `#8AB2FF` | ForgeAI (hover / text-on-tint) |
| `--grad` | `#0F6BFF → #256DFF` | same | measured |
| `--accent` | `#2EA3F2` | `#5CC0FF` | measured |
| `--violet` | `#3B2FA6` | `#8F86F0` | measured |
| `--navy` | `#050581` | – | measured (hero) |
| `--ink` | `#191826` | – | measured (hero base) |
| `--bg` | `#F4F7FD` | `#0B0F1E` | ForgeAI (blue-tinted white / navy) |
| `--surface` | `#FFFFFF` | `#131A2E` | measured / ForgeAI |
| `--surface-2` | `#EEF3FF` | `#1A2240` | ForgeAI |
| `--glass` | `rgba(255,255,255,.8)` | `rgba(19,26,46,.8)` | measured / ForgeAI |
| `--heading` | `#000000` | `#FFFFFF` | measured |
| `--text` | `#333333` | `#E4E8F3` | measured |
| `--muted` | `#666666` | `#A6AEC6` | measured |
| `--border` | `#D0D0D0` | `#2C3656` | measured / ForgeAI |
| `--success` | `#13794A` | `#3DD68C` | darkened from measured `#1FAC6B` to reach 4.5:1 |
| `--warning` | `#9A5B00` | `#F5B544` | ForgeAI (no amber on the reference) |
| `--danger` | `#C80330` | `#FF6B81` | measured |

Contrast checks (WCAG AA needs 4.5:1 for normal text), computed with the WCAG luminance formula:
`#666` on white 5.74:1; `#1363FA` on white 5.01:1 (white on `#1363FA` the same); `#13794A` on white 5.44:1; `#9A5B00` on
white 5.43:1; `#C80330` on white 5.98:1. Dark mode on `#131A2E`: `#A6AEC6` 7.81:1, `#5B93FF` 5.81:1, `#3DD68C` 9.22:1,
`#F5B544` 9.53:1, `#FF6B81` 6.31:1, body `#E4E8F3` 14.1:1. White on the measured gradient's end `#256DFF` is only
4.46:1, so button text sits on solid `#1363FA` and the gradient is used only behind large (34px) stat numbers, where
3:1 is enough.

### Type scale
Barlow 400/500/600/700/800. Hero 56px/800 (clamps to 34px on phones), h2 32px/700, h3 20px/700, stat numbers
34px/700, body 15px/1.6 at weight 500 (one step larger than the reference's 14px, for readability), small 13px.

### Shape, depth and spacing
- Radius: cards 25px (`--r-lg`), inner panels 16px, inputs 12px, pills 999px.
- Shadow: `--shadow` `0 1px 12px rgba(0,0,0,.05)` (measured), `--shadow-lift` `0 18px 40px rgba(16,40,100,.12)` (hover),
  `--glow` `0 3px 8px rgba(0,98,255,.25)` (measured, buttons).
- Spacing scale (4-based, covers the measured 6/10/14/20/28/40/50px): 4, 8, 12, 16, 20, 24, 32, 40, 56, 80px.
- Buttons: pill, padding 10px 28px, 15px/600. Primary is solid `#1363FA` with the measured glow (the gradient fails AA for 15px text); secondary is outlined.

### Copy
The hero follows the three-beat pattern with original words: **"Describe. Build. Prove."** Every view has a one-line
subtitle, labels are short, numbers are big. Scores are always labelled honestly: a score below target is shown in
amber with "below target", never with celebratory wording.
