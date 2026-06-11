module.exports = {
  root: true,
  extends: '@react-native',
  overrides: [
    {
      // Jest config/setup run under Node with Jest globals.
      files: ['jest.setup.js', 'jest.config.js'],
      env: { jest: true, node: true },
    },
  ],
};
