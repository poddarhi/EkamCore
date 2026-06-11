import DeviceInfo from 'react-native-device-info';

export interface DeviceProfile {
  /** Total physical RAM in bytes, or null if it couldn't be read. */
  totalMemoryBytes: number | null;
  /** Marketing model name, e.g. "iPhone 17 Pro". */
  modelName: string;
}

/** Read the device's RAM + model once. Never throws. */
export async function getDeviceProfile(): Promise<DeviceProfile> {
  try {
    const totalMemoryBytes = await DeviceInfo.getTotalMemory();
    return {
      totalMemoryBytes:
        typeof totalMemoryBytes === 'number' && totalMemoryBytes > 0
          ? totalMemoryBytes
          : null,
      modelName: DeviceInfo.getModel() || '',
    };
  } catch {
    return { totalMemoryBytes: null, modelName: '' };
  }
}
