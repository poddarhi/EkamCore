/**
 * Typography for EkamCore.
 *
 * Fonts are referenced by their exact PostScript name, which we normalized to
 * match the file name (see assets/fonts). Referencing the explicit per-weight
 * face — instead of fontFamily + fontWeight — is what makes custom fonts render
 * identically on both iOS (PostScript lookup) and Android (file-name lookup).
 *
 * - `display` (Space Grotesk): geometric, characterful — used for titles,
 *    greetings, brand and anything that should feel like a headline.
 * - `body` (Inter): highly legible — used for everything else, including chat.
 */
export const fonts = {
  display: {
    medium: 'SpaceGrotesk-Medium',
    semibold: 'SpaceGrotesk-SemiBold',
    bold: 'SpaceGrotesk-Bold',
  },
  body: {
    regular: 'Inter-Regular',
    medium: 'Inter-Medium',
    semibold: 'Inter-SemiBold',
    bold: 'Inter-Bold',
    extrabold: 'Inter-ExtraBold',
  },
  mono: 'Menlo',
} as const;
