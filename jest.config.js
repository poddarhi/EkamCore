module.exports = {
  preset: '@react-native/jest-preset',
  setupFiles: ['<rootDir>/jest.setup.js'],
  // Use fake timers so component timers (e.g. SplashScreen's setTimeout) can't
  // fire after the test's environment is torn down.
  fakeTimers: { enableGlobally: true },
  // Native modules ship ESM/Flow that Jest can't run as-is. They are mocked in
  // jest.setup.js, but whitelist them (and RN packages) for transform so any
  // transitive code Jest does load gets compiled instead of failing to parse.
  transformIgnorePatterns: [
    'node_modules/(?!(?:jest-)?@?react-native|@react-native(-community|-clipboard|-async-storage)?|react-native-blob-util|react-native-safe-area-context|llama\\.rn)/',
  ],
};
