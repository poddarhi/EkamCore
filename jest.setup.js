/**
 * Jest setup: stub the native modules so the JS test suite runs under Node
 * without the real llama.cpp / blob-util / clipboard bindings (which are
 * native-only and ship ESM that Jest can't execute).
 */

// --- @react-native-async-storage/async-storage (default import) ---
jest.mock('@react-native-async-storage/async-storage', () => {
  let store = {};
  return {
    __esModule: true,
    default: {
      getItem: jest.fn(key => Promise.resolve(key in store ? store[key] : null)),
      setItem: jest.fn((key, value) => {
        store[key] = value;
        return Promise.resolve();
      }),
      removeItem: jest.fn(key => {
        delete store[key];
        return Promise.resolve();
      }),
      clear: jest.fn(() => {
        store = {};
        return Promise.resolve();
      }),
      getAllKeys: jest.fn(() => Promise.resolve(Object.keys(store))),
      multiGet: jest.fn(keys =>
        Promise.resolve(keys.map(k => [k, k in store ? store[k] : null])),
      ),
      multiSet: jest.fn(pairs => {
        pairs.forEach(([k, v]) => {
          store[k] = v;
        });
        return Promise.resolve();
      }),
      multiRemove: jest.fn(keys => {
        keys.forEach(k => delete store[k]);
        return Promise.resolve();
      }),
    },
  };
});

// --- react-native-blob-util (default import; MODELS_DIR is computed at load) ---
jest.mock('react-native-blob-util', () => ({
  __esModule: true,
  default: {
    fs: {
      dirs: { DocumentDir: '/tmp/mock-documents', CacheDir: '/tmp/mock-cache' },
      exists: jest.fn(() => Promise.resolve(false)),
      mkdir: jest.fn(() => Promise.resolve()),
      mv: jest.fn(() => Promise.resolve()),
      unlink: jest.fn(() => Promise.resolve()),
      stat: jest.fn(() => Promise.resolve({ size: 0 })),
    },
    config: jest.fn(() => ({
      fetch: jest.fn(() =>
        Promise.resolve({ path: () => '/tmp/mock', info: () => ({ status: 200 }) }),
      ),
    })),
  },
}));

// --- llama.rn (named imports) ---
jest.mock('llama.rn', () => ({
  __esModule: true,
  initLlama: jest.fn(() =>
    Promise.resolve({
      completion: jest.fn(() => Promise.resolve({ text: '' })),
      release: jest.fn(() => Promise.resolve()),
    }),
  ),
  LlamaContext: class LlamaContext {},
  releaseAllLlama: jest.fn(() => Promise.resolve()),
}));

// --- @react-native-clipboard/clipboard (default import) ---
jest.mock('@react-native-clipboard/clipboard', () => ({
  __esModule: true,
  default: {
    setString: jest.fn(),
    getString: jest.fn(() => Promise.resolve('')),
  },
}));

// --- react-native-safe-area-context (provider + insets hooks) ---
jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const inset = { top: 0, right: 0, bottom: 0, left: 0 };
  const frame = { x: 0, y: 0, width: 390, height: 844 };
  const passthrough = ({ children }) =>
    React.createElement(React.Fragment, null, children);
  return {
    __esModule: true,
    SafeAreaProvider: passthrough,
    SafeAreaView: passthrough,
    SafeAreaInsetsContext: React.createContext(inset),
    useSafeAreaInsets: () => inset,
    useSafeAreaFrame: () => frame,
    initialWindowMetrics: { insets: inset, frame },
  };
});
