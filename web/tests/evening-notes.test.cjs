const test = require('node:test');
const assert = require('node:assert/strict');

const { buildEveningNotes } = require('../src/lib/evening-notes.mjs');

test('evening-only notes use reported state and breadth without a morning source', () => {
  const reports = [{
    id: '2026-09-28-evening', date: '2026-09-28', kind: 'evening',
    sections: [
      { title: '一、市场状态', paragraphs: ['- 状态: 偏冷。', '- 热度 / 脆弱度: 20 / 44.7（观察分）。'] },
      { title: '三、市场总览', paragraphs: ['上涨 1200 家 | 下跌 4000 家 | 上涨率 23.1%'] },
    ],
  }];
  assert.deepEqual(buildEveningNotes(reports), [{
    date: '2026-09-28', reportId: '2026-09-28-evening',
    text: '市场状态偏冷；上涨率 23.1%。', source: 'evening',
  }]);
});

test('evening-only notes ignore old mornings, old evenings, and missing facts', () => {
  assert.deepEqual(buildEveningNotes([
    { id: 'old', date: '2026-09-24', kind: 'evening', sections: [] },
    { id: 'morning', date: '2026-09-28', kind: 'morning', sections: [] },
    { id: 'empty', date: '2026-09-29', kind: 'evening', sections: [] },
  ]), []);
});
