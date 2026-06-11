/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

test('renders correctly', async () => {
  let tree: ReactTestRenderer.ReactTestRenderer | undefined;
  await ReactTestRenderer.act(() => {
    tree = ReactTestRenderer.create(<App />);
  });
  // Unmount so effect cleanups (e.g. SplashScreen's clearTimeout) run.
  await ReactTestRenderer.act(() => {
    tree?.unmount();
  });
});
