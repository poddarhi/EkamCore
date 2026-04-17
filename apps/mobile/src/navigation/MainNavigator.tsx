import React, {useCallback} from 'react';
import {Alert, StyleSheet, Text, View} from 'react-native';
import {NavigationContainer} from '@react-navigation/native';
import {createBottomTabNavigator} from '@react-navigation/bottom-tabs';
import {createNativeStackNavigator} from '@react-navigation/native-stack';

import {useAuth} from '../contexts/AuthContext';
import {useFlags} from '../contexts/FlagContext';
import {LoginScreen} from '../screens/LoginScreen';
import {TodayScreen} from '../screens/TodayScreen';
import {RecapScreen} from '../screens/RecapScreen';
import {PlaceholderScreen} from '../screens/PlaceholderScreen';
import {Colors, Typography} from '../design-system/tokens';

// ── Stack param lists ──
export type AuthStackParams = {Login: undefined};
export type TodayStackParams = {Today: undefined};
export type RecapStackParams = {Recap: undefined};
export type SearchStackParams = {Search: undefined};
export type PeopleStackParams = {People: undefined};
export type SettingsStackParams = {Settings: undefined};

const AuthStack = createNativeStackNavigator<AuthStackParams>();
const Tab = createBottomTabNavigator();
const TodayStack = createNativeStackNavigator<TodayStackParams>();
const RecapStack = createNativeStackNavigator<RecapStackParams>();
const SearchStack = createNativeStackNavigator<SearchStackParams>();
const PeopleStack = createNativeStackNavigator<PeopleStackParams>();
const SettingsStack = createNativeStackNavigator<SettingsStackParams>();

function TodayNavigator() {
  return (
    <TodayStack.Navigator screenOptions={{headerShown: false}}>
      <TodayStack.Screen name="Today" component={TodayScreen} />
    </TodayStack.Navigator>
  );
}

function RecapNavigator() {
  return (
    <RecapStack.Navigator screenOptions={{headerShown: false}}>
      <RecapStack.Screen name="Recap" component={RecapScreen} />
    </RecapStack.Navigator>
  );
}

function SearchNavigator() {
  return (
    <SearchStack.Navigator screenOptions={{headerShown: false}}>
      <SearchStack.Screen
        name="Search"
        children={() => <PlaceholderScreen title="Search" />}
      />
    </SearchStack.Navigator>
  );
}

function PeopleNavigator() {
  return (
    <PeopleStack.Navigator screenOptions={{headerShown: false}}>
      <PeopleStack.Screen
        name="People"
        children={() => <PlaceholderScreen title="People" />}
      />
    </PeopleStack.Navigator>
  );
}

function SettingsNavigator() {
  return (
    <SettingsStack.Navigator screenOptions={{headerShown: false}}>
      <SettingsStack.Screen
        name="Settings"
        children={() => <PlaceholderScreen title="Settings" />}
      />
    </SettingsStack.Navigator>
  );
}

function TabIcon({
  label,
  focused,
  enabled,
}: {
  label: string;
  focused: boolean;
  enabled: boolean;
}) {
  return (
    <View style={tabStyles.iconWrap}>
      <Text
        style={[
          tabStyles.iconLabel,
          focused && enabled ? tabStyles.iconFocused : null,
          !enabled ? tabStyles.iconDisabled : null,
        ]}>
        {label}
      </Text>
    </View>
  );
}

function DisabledTabScreen() {
  return <View />;
}

function MainTabs() {
  const {useFlag} = useFlags();

  const recapEnabled = useFlag('recap.enabled');
  const searchEnabled = useFlag('search.enabled');
  const peopleEnabled = useFlag('people.enabled');

  const showComingSoon = useCallback(() => {
    Alert.alert('Coming soon', 'This feature will be available in a future update.');
  }, []);

  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: tabStyles.bar,
        tabBarActiveTintColor: Colors.primary,
        tabBarInactiveTintColor: Colors.neutral400,
      }}>
      <Tab.Screen
        name="TodayTab"
        component={TodayNavigator}
        options={{
          tabBarLabel: 'Today',
          tabBarIcon: ({focused}) => (
            <TabIcon label="◉" focused={focused} enabled />
          ),
          tabBarAccessibilityLabel: 'Today',
        }}
      />

      <Tab.Screen
        name="RecapTab"
        component={recapEnabled ? RecapNavigator : DisabledTabScreen}
        listeners={
          recapEnabled ? {} : {tabPress: e => { e.preventDefault(); showComingSoon(); }}
        }
        options={{
          tabBarLabel: 'Recap',
          tabBarIcon: ({focused}) => (
            <TabIcon label="◎" focused={focused} enabled={recapEnabled} />
          ),
          tabBarAccessibilityLabel: 'Recap',
        }}
      />

      <Tab.Screen
        name="SearchTab"
        component={searchEnabled ? SearchNavigator : DisabledTabScreen}
        listeners={
          searchEnabled ? {} : {tabPress: e => { e.preventDefault(); showComingSoon(); }}
        }
        options={{
          tabBarLabel: 'Search',
          tabBarIcon: ({focused}) => (
            <TabIcon label="⌕" focused={focused} enabled={searchEnabled} />
          ),
          tabBarAccessibilityLabel: 'Search',
        }}
      />

      <Tab.Screen
        name="PeopleTab"
        component={peopleEnabled ? PeopleNavigator : DisabledTabScreen}
        listeners={
          peopleEnabled ? {} : {tabPress: e => { e.preventDefault(); showComingSoon(); }}
        }
        options={{
          tabBarLabel: 'People',
          tabBarIcon: ({focused}) => (
            <TabIcon label="◯" focused={focused} enabled={peopleEnabled} />
          ),
          tabBarAccessibilityLabel: 'People',
        }}
      />

      <Tab.Screen
        name="SettingsTab"
        component={SettingsNavigator}
        options={{
          tabBarLabel: 'Settings',
          tabBarIcon: ({focused}) => (
            <TabIcon label="⚙" focused={focused} enabled />
          ),
          tabBarAccessibilityLabel: 'Settings',
        }}
      />
    </Tab.Navigator>
  );
}

export function MainNavigator() {
  const {isAuthenticated, isLoading} = useAuth();

  if (isLoading) return null;

  return (
    <NavigationContainer>
      {isAuthenticated ? (
        <MainTabs />
      ) : (
        <AuthStack.Navigator screenOptions={{headerShown: false}}>
          <AuthStack.Screen name="Login" component={LoginScreen} />
        </AuthStack.Navigator>
      )}
    </NavigationContainer>
  );
}

const tabStyles = StyleSheet.create({
  bar: {
    backgroundColor: Colors.white,
    borderTopColor: Colors.neutral200,
    borderTopWidth: 1,
  },
  iconWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 44,
    minHeight: 44,
  },
  iconLabel: {
    fontSize: 20,
    color: Colors.neutral400,
  },
  iconFocused: {
    color: Colors.primary,
  },
  iconDisabled: {
    color: Colors.neutral200,
  },
});
