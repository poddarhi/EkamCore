# Design Tokens Reference (from ART-05)

## Colors
```css
--color-primary: #1F3864;       --color-primary-hover: #162A4D;
--color-primary-light: #2E75B6; --color-primary-surface: #E8EFF8;
--color-neutral-900: #1A1A1A;   --color-neutral-700: #404040;
--color-neutral-600: #666666;   --color-neutral-500: #888888;
--color-neutral-400: #AAAAAA;   --color-neutral-200: #D9D9D9;
--color-neutral-100: #F2F2F2;   --color-neutral-50: #F8F8F8;
--color-white: #FFFFFF;
--color-success: #28A745;       --color-success-surface: #E6F4EA;
--color-warning: #E6A817;       --color-warning-surface: #FFF8E1;
--color-error: #DC3545;         --color-error-surface: #FDEDED;
--color-info: #0D6EFD;          --color-info-surface: #E7F1FF;
```

## Confidence Badge Colors
| Level | Background | Text | Border |
|---|---|---|---|
| deterministic | (no badge shown) | — | — |
| high | #E6F4EA | #1B6E2E | #28A745 |
| medium | #FFF8E1 | #8A6D00 | #E6A817 |
| low | #F2F2F2 | #666666 | #AAAAAA |

## Typography
Font: Inter, -apple-system, sans-serif. Mono: JetBrains Mono, SF Mono, monospace.
| Token | Size | Weight | Usage |
|---|---|---|---|
| --text-display | 32/40 | 700 | Page titles |
| --text-h1 | 24/32 | 700 | Section heads |
| --text-h2 | 20/28 | 600 | Card titles |
| --text-h3 | 18/24 | 600 | Subsections |
| --text-body | 15/22 | 400 | Reading text |
| --text-small | 13/18 | 400 | Metadata |
| --text-caption | 12/16 | 500 | Badges |

## Spacing (4px base)
1=4px, 2=8px, 3=12px, 4=16px, 5=20px, 6=24px, 8=32px, 10=40px, 12=48px, 16=64px

## Shadows
sm: 0 1px 2px rgba(0,0,0,0.06); md: 0 4px 8px rgba(0,0,0,0.08); lg: 0 8px 24px rgba(0,0,0,0.12); focus: 0 0 0 3px rgba(30,117,182,0.3)

## Border Radius
sm=4px, md=8px, lg=12px, xl=16px, full=9999px

## Icons: Lucide React
Card types: event=Calendar, reminder=CheckCircle, person=User, file=FileText, photo=Image, status=Activity, suggestion=Lightbulb, pack=Package
Sizes: xs=14, sm=16, md=20, lg=24, xl=32

## Components (key specs)
- **Button**: Primary (#1F3864/white), Secondary (transparent/primary+border), Ghost (transparent/neutral-600), Danger (error/white). Sizes: sm(32px), md(40px), lg(48px). radius-md.
- **Card**: white bg, 1px neutral-200 border, radius-lg, shadow-sm(rest)/shadow-md(hover), sp-4 padding.
- **Input**: 40px height, radius-md, neutral-200 border. Focus: 2px primary-light. Error: 2px error + error-surface bg.
- **Badge**: 24px height, sp-1 hpad, radius-sm, caption text.
- **StatusIndicator**: 10px dot. healthy=green(pulse), degraded=amber, error=red, unknown=gray.
