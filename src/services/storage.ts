import AsyncStorage from '@react-native-async-storage/async-storage';
import { ModelInfo } from '../types';

const KEYS = {
  customModels: 'ekamcore.customModels.v1',
  lastModelId: 'ekamcore.lastModelId.v1',
  systemPrompt: 'ekamcore.systemPrompt.v1',
  themeMode: 'ekamcore.themeMode.v1',
  onboardingSeen: 'ekamcore.onboardingSeen.v1',
};

export async function loadOnboardingSeen(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEYS.onboardingSeen)) === 'true';
}

export async function saveOnboardingSeen(): Promise<void> {
  await AsyncStorage.setItem(KEYS.onboardingSeen, 'true');
}

export type ThemeMode = 'system' | 'light' | 'dark';

export async function loadThemeMode(): Promise<ThemeMode> {
  const raw = await AsyncStorage.getItem(KEYS.themeMode);
  if (raw === 'light' || raw === 'dark' || raw === 'system') {
    return raw;
  }
  return 'system';
}

export async function saveThemeMode(mode: ThemeMode): Promise<void> {
  await AsyncStorage.setItem(KEYS.themeMode, mode);
}

export async function loadCustomModels(): Promise<ModelInfo[]> {
  try {
    const raw = await AsyncStorage.getItem(KEYS.customModels);
    return raw ? (JSON.parse(raw) as ModelInfo[]) : [];
  } catch {
    return [];
  }
}

export async function saveCustomModels(models: ModelInfo[]): Promise<void> {
  await AsyncStorage.setItem(KEYS.customModels, JSON.stringify(models));
}

export async function loadLastModelId(): Promise<string | null> {
  return AsyncStorage.getItem(KEYS.lastModelId);
}

export async function saveLastModelId(id: string): Promise<void> {
  await AsyncStorage.setItem(KEYS.lastModelId, id);
}

const DEFAULT_SYSTEM_PROMPT =
  'You are a helpful AI assistant. Answer the user clearly, accurately, and concisely. Stay on the topic of the question.';

export async function loadSystemPrompt(): Promise<string> {
  const raw = await AsyncStorage.getItem(KEYS.systemPrompt);
  return raw ?? DEFAULT_SYSTEM_PROMPT;
}

export async function saveSystemPrompt(prompt: string): Promise<void> {
  await AsyncStorage.setItem(KEYS.systemPrompt, prompt);
}
