/**
 * EkamCore — run language models fully offline on your phone.
 *
 * @format
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Keyboard,
  Platform,
  Pressable,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  SafeAreaProvider,
  useSafeAreaInsets,
} from 'react-native-safe-area-context';
import { HistoryPanel } from './src/components/HistoryPanel';
import { Icon, IconName } from './src/components/Icon';
import { Onboarding } from './src/components/Onboarding';
import { SplashScreen } from './src/components/SplashScreen';
import { AppProvider, useApp } from './src/context/AppContext';
import { ThemeProvider, useTheme } from './src/context/ThemeContext';
import { ChatScreen } from './src/screens/ChatScreen';
import { ModelsScreen } from './src/screens/ModelsScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { ToolRunnerScreen } from './src/screens/ToolRunnerScreen';
import { ToolsListScreen } from './src/screens/ToolsListScreen';
import { getTool } from './src/data/tools';
import {
  loadOnboardingSeen,
  saveOnboardingSeen,
} from './src/services/storage';
import { spacing, type ThemeColors } from './src/theme';
import { fonts } from './src/typography';

type Tab = 'chat' | 'tools' | 'models' | 'settings';

const TAB_META: Record<Tab, { title: string; icon: IconName }> = {
  chat: { title: 'Chat', icon: 'chat' },
  tools: { title: 'AI Tools', icon: 'grid' },
  models: { title: 'Models', icon: 'models' },
  settings: { title: 'Settings', icon: 'settings' },
};

function Shell() {
  const { colors } = useTheme();
  const styles = React.useMemo(() => makeStyles(colors), [colors]);
  const insets = useSafeAreaInsets();
  const [tab, setTab] = useState<Tab>('models');
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const { loadedModelId, downloadedIds, activeRemote } = useApp();

  const selectTab = (t: Tab) => {
    setTab(t);
    if (t !== 'tools') {
      setActiveTool(null);
    }
  };

  useEffect(() => {
    const showEvt =
      Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvt =
      Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const showSub = Keyboard.addListener(showEvt, e =>
      setKeyboardHeight(e.endCoordinates?.height ?? 0),
    );
    const hideSub = Keyboard.addListener(hideEvt, () => setKeyboardHeight(0));
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  const keyboardOpen = keyboardHeight > 0;

  const openTool = activeTool ? getTool(activeTool) : undefined;

  const headerTitle =
    tab === 'tools' && openTool ? openTool.title : TAB_META[tab].title;

  const subtitle =
    tab === 'chat'
      ? activeRemote
        ? 'Remote • your computer'
        : loadedModelId
        ? 'Offline • private'
        : 'No model loaded'
      : tab === 'tools'
      ? openTool
        ? openTool.tagline
        : 'Smart assistants, on-device'
      : tab === 'models'
      ? `${downloadedIds.length} downloaded`
      : 'Personalize your app';

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        {tab === 'tools' && openTool ? (
          <View style={styles.headerRow}>
            <Pressable
              onPress={() => setActiveTool(null)}
              hitSlop={10}
              style={styles.backBtn}>
              <Icon name="arrowLeft" size={22} color={colors.text} />
            </Pressable>
            <View style={{ flex: 1 }}>
              <Text style={styles.title} numberOfLines={1}>
                {headerTitle}
              </Text>
              <Text style={styles.subtitle} numberOfLines={1}>
                {subtitle}
              </Text>
            </View>
          </View>
        ) : tab === 'chat' ? (
          <View style={styles.headerRow}>
            <Pressable
              onPress={() => setHistoryOpen(true)}
              hitSlop={10}
              style={styles.backBtn}>
              <Icon name="history" size={22} color={colors.text} />
            </Pressable>
            <View style={{ flex: 1 }}>
              <Text style={styles.title} numberOfLines={1}>
                {headerTitle}
              </Text>
              <Text style={styles.subtitle} numberOfLines={1}>
                {subtitle}
              </Text>
            </View>
          </View>
        ) : (
          <>
            <Text style={styles.title}>{headerTitle}</Text>
            <Text style={styles.subtitle}>{subtitle}</Text>
          </>
        )}
      </View>

      <View style={styles.body}>
        {tab === 'chat' && (
          <ChatScreen
            onGoToModels={() => selectTab('models')}
            keyboardHeight={keyboardHeight}
          />
        )}
        {tab === 'tools' &&
          (activeTool ? (
            <ToolRunnerScreen
              toolId={activeTool}
              keyboardHeight={keyboardHeight}
              onGoToModels={() => selectTab('models')}
            />
          ) : (
            <ToolsListScreen
              onOpen={id => setActiveTool(id)}
              onGoToModels={() => selectTab('models')}
            />
          ))}
        {tab === 'models' && <ModelsScreen />}
        {tab === 'settings' && <SettingsScreen />}
      </View>

      {!keyboardOpen && (
        <View
          style={[styles.tabBar, { paddingBottom: insets.bottom + spacing.sm }]}>
          {(Object.keys(TAB_META) as Tab[]).map(t => (
            <TabButton
              key={t}
              icon={TAB_META[t].icon}
              label={TAB_META[t].title}
              active={tab === t}
              onPress={() => selectTab(t)}
              colors={colors}
            />
          ))}
        </View>
      )}

      <HistoryPanel
        visible={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />
    </View>
  );
}

function TabButton({
  label,
  icon,
  active,
  onPress,
  colors,
}: {
  label: string;
  icon: IconName;
  active: boolean;
  onPress: () => void;
  colors: ThemeColors;
}) {
  const anim = useRef(new Animated.Value(active ? 1 : 0)).current;
  useEffect(() => {
    Animated.spring(anim, {
      toValue: active ? 1 : 0,
      useNativeDriver: true,
      friction: 7,
      tension: 90,
    }).start();
  }, [active, anim]);

  const iconScale = anim.interpolate({ inputRange: [0, 1], outputRange: [1, 1.18] });
  const lift = anim.interpolate({ inputRange: [0, 1], outputRange: [0, -2] });

  return (
    <Pressable style={tabStyles.btn} onPress={onPress}>
      <Animated.View
        style={[
          tabStyles.pill,
          {
            backgroundColor: colors.primary,
            opacity: anim.interpolate({ inputRange: [0, 1], outputRange: [0, 0.16] }),
            transform: [{ scaleX: anim }],
          },
        ]}
      />
      <Animated.View style={{ transform: [{ scale: iconScale }, { translateY: lift }] }}>
        <Icon
          name={icon}
          size={22}
          color={active ? colors.primary : colors.textFaint}
        />
      </Animated.View>
      <Text
        style={[
          tabStyles.label,
          { color: active ? colors.primary : colors.textFaint },
        ]}>
        {label}
      </Text>
    </Pressable>
  );
}

function Root() {
  const { colors } = useTheme();
  const [showSplash, setShowSplash] = useState(true);
  const [showOnboarding, setShowOnboarding] = useState(false);

  useEffect(() => {
    loadOnboardingSeen()
      .then(seen => setShowOnboarding(!seen))
      .catch(() => {});
  }, []);

  const finishOnboarding = () => {
    setShowOnboarding(false);
    saveOnboardingSeen().catch(() => {});
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.bg} />
      <Shell />
      {showOnboarding && !showSplash && (
        <Onboarding onDone={finishOnboarding} />
      )}
      {showSplash && <SplashScreen onFinish={() => setShowSplash(false)} />}
    </View>
  );
}

function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <AppProvider>
          <Root />
        </AppProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}

const tabStyles = StyleSheet.create({
  btn: { flex: 1, alignItems: 'center', gap: 3, paddingTop: 6 },
  pill: {
    position: 'absolute',
    top: 0,
    width: 48,
    height: 34,
    borderRadius: 17,
  },
  label: { fontSize: 11, fontFamily: fonts.body.semibold, letterSpacing: 0.2 },
});

const makeStyles = (colors: ThemeColors) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: colors.bg },
    header: {
      paddingHorizontal: spacing.lg,
      paddingBottom: spacing.sm,
      backgroundColor: colors.bg,
    },
    title: {
      color: colors.text,
      fontSize: 27,
      fontFamily: fonts.display.bold,
      letterSpacing: -0.5,
    },
    subtitle: {
      color: colors.textDim,
      fontSize: 13,
      marginTop: 3,
      fontFamily: fonts.body.medium,
    },
    headerRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    backBtn: {
      width: 38,
      height: 38,
      borderRadius: 19,
      backgroundColor: colors.surfaceAlt,
      alignItems: 'center',
      justifyContent: 'center',
    },
    body: { flex: 1 },
    tabBar: {
      flexDirection: 'row',
      borderTopWidth: 1,
      borderTopColor: colors.border,
      backgroundColor: colors.surface,
      paddingTop: spacing.sm,
    },
  });

export default App;
