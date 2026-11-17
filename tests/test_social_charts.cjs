const test = require('node:test');
const assert = require('node:assert/strict');
const { renderBarChart } = require('../app/static/js/social-charts.js');

test('renders saved weekly, monthly and quarterly audience-growth values as accessible SVG charts', () => {
  const sampleFromAnalytics = [
    { platform: 'youtube', platform_name: 'YouTube', period: '2026-01-05', net_follower_growth: 100 },
    { platform: 'youtube', platform_name: 'YouTube', period: '2026-02', net_follower_growth: 240 },
    { platform: 'youtube', platform_name: 'YouTube', period: '2026-Q1', net_follower_growth: 310 },
  ];
  for (const [index, grain] of ['weekly', 'monthly', 'quarterly'].entries()) {
    const svg = renderBarChart([sampleFromAnalytics[index]], 'net_follower_growth', `${grain} audience growth`);
    assert.match(svg, /<svg[^>]+role="img"/);
    assert.match(svg, new RegExp(`${grain} audience growth`));
    assert.match(svg, /<rect /);
    assert.match(svg, /100|240|310/);
  }
});

test('shows missing analytics as N/A and never draws it as a zero bar', () => {
  const svg = renderBarChart([{ platform: 'facebook', platform_name: 'Facebook', period: '2026-Q1', reach: null }], 'reach', 'Reach');
  assert.match(svg, /N\/A/);
  assert.doesNotMatch(svg, /<rect /);
  assert.match(svg, /Missing data is N\/A, not zero/);
});

test('plots negative values in a distinct direction and safely escapes content labels', () => {
  const svg = renderBarChart([{ platform: 'x', platform_name: '<img onerror="x">', period: '2026-01', net: -5 }], 'net', 'Net growth');
  assert.match(svg, /fill="#a83939"/);
  assert.match(svg, /&lt;img/);
  assert.doesNotMatch(svg, /<img/);
});
