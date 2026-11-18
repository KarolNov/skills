import { expect, test } from 'claude-code/testing'

import { tabAt } from './tabs'

test('the tab bar finds the tab under a click', () => {
  expect(tabAt(0)).toBe('comment')
  expect(tabAt(10)).toBe('comment')
  expect(tabAt(11)).toBe('suggest')
  expect(tabAt(28)).toBe('suggest')
  expect(tabAt(29)).toBeUndefined()
})
