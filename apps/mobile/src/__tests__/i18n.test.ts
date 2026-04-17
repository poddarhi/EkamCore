import {t} from '../i18n';

describe('i18n t()', () => {
  it('resolves a simple key', () => {
    expect(t('app.name')).toBe('EkamCore');
  });

  it('resolves a nested key', () => {
    expect(t('auth.signIn')).toBe('Sign in');
  });

  it('returns key path for missing keys', () => {
    expect(t('missing.key')).toBe('missing.key');
  });

  it('interpolates parameters', () => {
    expect(t('search.noResults', {query: 'test'})).toBe('No results for "test"');
  });

  it('resolves connectivity strings', () => {
    expect(t('connectivity.connected')).toBe('Connected');
    expect(t('connectivity.hubSleeping')).toBe('Hub is asleep — reconnecting...');
  });
});
