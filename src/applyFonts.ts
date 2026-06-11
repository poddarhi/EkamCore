import React from 'react';
import { StyleSheet, Text, TextInput } from 'react-native';
import { fonts } from './typography';

/**
 * Custom fonts only render reliably on BOTH iOS and Android when you reference
 * an explicit per-weight face (e.g. "Inter-SemiBold") rather than fontFamily +
 * fontWeight. Editing every stylesheet by hand is error-prone, so instead we
 * patch <Text> once: for any text without its own fontFamily we map its
 * fontWeight to the matching Inter face. Headlines that opt into the display
 * face (Space Grotesk) set fontFamily explicitly and are left untouched.
 */
function interFaceForWeight(weight?: string | number): string {
  switch (String(weight)) {
    case '500':
      return fonts.body.medium;
    case '600':
      return fonts.body.semibold;
    case '700':
    case 'bold':
      return fonts.body.bold;
    case '800':
    case '900':
      return fonts.body.extrabold;
    default:
      return fonts.body.regular;
  }
}

type StyledElement = React.ReactElement<{ style?: unknown }>;
type Renderable = {
  render?: (...args: unknown[]) => StyledElement;
  __fontPatched?: boolean;
  defaultProps?: Record<string, unknown>;
};

const TextAny = Text as unknown as Renderable;
if (TextAny.render && !TextAny.__fontPatched) {
  const original = TextAny.render;
  TextAny.render = function patchedRender(...args: unknown[]) {
    const element = original.apply(this, args);
    const flat = (StyleSheet.flatten(element.props.style) ?? {}) as {
      fontFamily?: string;
      fontWeight?: string | number;
    };
    const family = flat.fontFamily ?? interFaceForWeight(flat.fontWeight);
    return React.cloneElement(element, {
      style: [{ fontFamily: family }, element.props.style],
    });
  };
  TextAny.__fontPatched = true;
}

const TextInputAny = TextInput as unknown as Renderable;
TextInputAny.defaultProps = {
  ...(TextInputAny.defaultProps ?? {}),
  style: { fontFamily: fonts.body.regular },
};
