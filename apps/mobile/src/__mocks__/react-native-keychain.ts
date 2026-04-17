/** Jest mock for react-native-keychain (S16-002 — expanded). */

const store: Record<string, {username: string; password: string}> = {};

export const ACCESS_CONTROL = {
  BIOMETRY_ANY_OR_DEVICE_PASSCODE: 'BiometryAnyOrDevicePasscode',
  BIOMETRY_ANY: 'BiometryAny',
  DEVICE_PASSCODE: 'DevicePasscode',
};

export const ACCESSIBLE = {
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'WhenUnlockedThisDeviceOnly',
  WHEN_UNLOCKED: 'WhenUnlocked',
  AFTER_FIRST_UNLOCK: 'AfterFirstUnlock',
};

export const BIOMETRY_TYPE = {
  FACE_ID: 'FaceID',
  TOUCH_ID: 'TouchID',
  FINGERPRINT: 'Fingerprint',
  IRIS: 'Iris',
};

export const getGenericPassword = jest.fn(
  async (opts?: {service?: string}) => {
    const service = opts?.service ?? 'default';
    const entry = store[service];
    if (!entry) return false;
    return {
      username: entry.username,
      password: entry.password,
      service,
      storage: 'keychain',
    };
  },
);

export const setGenericPassword = jest.fn(
  async (
    username: string,
    password: string,
    opts?: {service?: string; accessControl?: string; accessible?: string},
  ) => {
    const service = opts?.service ?? 'default';
    store[service] = {username, password};
    return true;
  },
);

export const resetGenericPassword = jest.fn(
  async (opts?: {service?: string}) => {
    const service = opts?.service ?? 'default';
    delete store[service];
    return true;
  },
);

export const getAllGenericPasswordServices = jest.fn(async () => {
  return Object.keys(store);
});

let _biometryType: string | null = 'FaceID';

export const getSupportedBiometryType = jest.fn(async () => _biometryType);

/** Test helper: set the biometric type returned by getSupportedBiometryType. */
export function __setBiometryType(type: string | null) {
  _biometryType = type;
}

/** Test helper: clear all stored entries. */
export function __clearStore() {
  Object.keys(store).forEach(k => delete store[k]);
}
