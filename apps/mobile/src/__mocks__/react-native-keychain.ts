/** Jest mock for react-native-keychain. */

const store: Record<string, string> = {};

export const getGenericPassword = jest.fn(
  async ({service}: {service: string}) => {
    const val = store[service];
    if (!val) return false;
    return {username: 'refresh', password: val, service, storage: 'keychain'};
  },
);

export const setGenericPassword = jest.fn(
  async (_username: string, password: string, {service}: {service: string}) => {
    store[service] = password;
    return true;
  },
);

export const resetGenericPassword = jest.fn(
  async ({service}: {service: string}) => {
    delete store[service];
    return true;
  },
);

export function __clearStore() {
  Object.keys(store).forEach(k => delete store[k]);
}
