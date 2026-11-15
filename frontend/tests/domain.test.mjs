import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { build } from 'esbuild';
import { spec, task, plan } from './fixtures.mjs';

async function load(path) {
  const result = await build({ entryPoints: [path], bundle: true, platform: 'node', format: 'esm', write: false });
  return import('data:text/javascript;base64,' + Buffer.from(result.outputFiles[0].contents).toString('base64'));
}
const { assessPlan, emptyPlan, emptySpec, linkError, newTask, planState, removeTask, validateSpec, validatePlanStructure, validateTaskProposal, normalizeContractText } = await load('src/plan.ts');
const { createProject, readProjects, writeProjects, snapshot, readJson } = await load('src/storage.ts');

test('空项目不包含规格和任务，空计划不报错', () => {
  const { workspace } = createProject('本地项目');
  assert.equal(workspace.spec, null);
  assert.deepEqual(workspace.plan.tasks, []);
  const assessment = assessPlan(workspace.plan, emptySpec());
  assert.deepEqual(assessment.issues, []);
  assert.equal(planState(workspace.plan, assessment, false, false), 'NO_PLAN');
});

test('规格必填、重复 ID、额外字段和有效 JSON', () => {
  assert.ok(validateSpec(emptySpec()).length > 0);
  assert.deepEqual(validateSpec(spec), []);
  assert.ok(validateSpec({ ...spec, product_name: ' ', requirements: [] }).length >= 2);
  assert.match(validateSpec({ ...spec, requirements: [...spec.requirements, ...spec.requirements] })[0].message, /重复/);
  assert.ok(validateSpec({ ...spec, unknown: true }).length);
});

test('任务 JSON 拒绝结构错误，草稿允许缺字段并提供诊断', async () => {
  assert.ok(validatePlanStructure({ tasks: [] }).length);
  assert.ok(validatePlanStructure(plan(newTask('A'))).length);
  assert.deepEqual(validatePlanStructure(plan(task('A'))), []);
  assert.deepEqual(await readJson(new File(['\uFEFF' + JSON.stringify(spec)], 'spec.json')), spec);
  await assert.rejects(readJson(new File(['{'], 'bad.json')), /无法读取 JSON/);
  await assert.rejects(readJson(new File([' '.repeat(1024 * 1024 + 1)], 'large.json')), /1 MiB/);
});

test('缺失、自环、重复依赖和实际回路均被拦截', () => {
  for (const [data, pattern] of [
    [plan(task('A', ['MISSING'])), /找不到上游/],
    [plan(task('A', ['A'])), /自身/],
    [plan(task('A'), task('B', ['A', 'A'])), /重复/],
    [plan(task('A', ['B']), task('B', ['A']), task('C', ['A'])), /A → B → A/],
  ]) {
    const result = assessPlan(data, spec);
    assert.equal(result.result, undefined);
    assert.match(result.issues[0].message, pattern);
  }
  assert.match(linkError(plan(task('A'), task('B', ['A'])), 'B', 'A'), /循环/);
});

test('按确定顺序为分叉汇合图计算并行层，编辑后原结果失效', () => {
  const data = plan(task('D', ['B', 'C']), task('C', ['A']), task('B', ['A']), task('A'));
  const assessment = assessPlan(data, spec);
  assert.deepEqual(assessment.result.batches, [['A'], ['B', 'C'], ['D']]);
  assert.deepEqual(assessment.result.order, ['A', 'B', 'C', 'D']);
  assert.equal(planState(data, assessment, false, false), 'PLAN_AVAILABLE');
  assert.equal(planState(data, assessment, true, false), 'PLAN_VALID');
  const edited = plan(task('A'), task('B', ['A']));
  assert.equal(planState(edited, assessPlan(edited, spec), false, true), 'REORCHESTRATION_REQUIRED');
  assert.deepEqual(assessPlan(edited, spec).result.batches, [['A'], ['B']]);
});

test('输入绑定必须指向直接上游及现有交付，删除任务时清理引用', () => {
  const a = task('A'), b = task('B', ['A']);
  b.inputs = [{ kind: 'task', task_id: 'A', deliverable_id: 'MISSING' }];
  assert.match(assessPlan(plan(a, b), spec).issues[0].message, /找不到上游交付/);
  b.inputs[0].deliverable_id = 'OUT';
  assert.ok(assessPlan(plan(a, b), spec).result);
  assert.deepEqual(removeTask(plan(a, b), 'A').tasks[0].inputs, []);
  assert.deepEqual(removeTask(plan(a, b), 'A').tasks[0].dependencies, []);
});

test('本地快照保留布局和来源，保存及恢复不覆盖旧草稿键', () => {
  const memory = new Map([['flowstudio-t04-draft', 'legacy']]);
  const storage = { setItem: (key, value) => memory.set(key, value), getItem: (key) => memory.get(key) ?? null };
  const project = createProject('项目');
  project.workspace = { ...project.workspace, spec, plan: plan(task('A')), source: 'IMPORTED', orchestrated: true,
    layout: { positions: { A: { x: 10, y: 20 } }, notes: [], viewport: { x: 5, y: 8, zoom: 1 } } };
  const saved = snapshot(project);
  assert.equal(snapshot(saved), saved);
  writeProjects(storage, [saved]);
  assert.deepEqual(readProjects(storage), [saved]);
  assert.equal(memory.get('flowstudio-t04-draft'), 'legacy');
  assert.equal(saved.history[0].workspace.layout.positions.A.x, 10);
  assert.equal(emptyPlan().tasks.length, 0);
});

test('未完成的草稿可以恢复，损坏的布局不会进入 UI', () => {
  let raw;
  const storage = { setItem: (_, value) => { raw = value; }, getItem: () => raw };
  const project = createProject('草稿');
  project.workspace.spec = emptySpec();
  project.workspace.plan = plan(newTask('Task_A'));
  writeProjects(storage, [project]);
  assert.deepEqual(readProjects(storage), [project]);
  project.workspace.layout.positions.Task_A = { x: '损坏', y: 0 };
  writeProjects(storage, [project]);
  assert.throws(() => readProjects(storage), /浏览器存储格式无法读取/);
});
test('会议室预约预设可编排，重复创建时项目名和数据彼此独立', async () => {
  const { createMeetingRoomProject } = await load('src/presets.ts');
  const first = createMeetingRoomProject([]);
  const second = createMeetingRoomProject([first]);
  assert.equal(second.name, '会议室预约（2）');
  assert.notEqual(first.id, second.id);
  assert.equal(second.workspace.source, 'PRESET');
  assert.deepEqual(validateSpec(second.workspace.spec), []);
  const assessment = assessPlan(second.workspace.plan, second.workspace.spec);
  assert.deepEqual(assessment.result.batches, [['RULES'], ['FORM', 'TESTS']]);
  first.workspace.plan.tasks[0].name = '修改后的名称';
  assert.equal(second.workspace.plan.tasks[0].name, '定义预约规则');
});

test('自动布局只移动任务，保留注释的坐标和内容', async () => {
  const { arrangeNodes } = await load('src/canvas-tools.ts');
  const note = { id: 'NOTE', type: 'note', position: { x: 640, y: -180 }, data: { text: '固定备注' } };
  const nodes = [
    { id: 'A', type: 'task', position: { x: 100, y: 160 } },
    note,
    { id: 'B', type: 'task', position: { x: -90, y: -200 } },
  ];
  const [first, annotation, second] = arrangeNodes(plan(task('A'), task('B', ['A'])), nodes);
  assert.deepEqual(first.position, { x: 0, y: 0 });
  assert.deepEqual(second.position, { x: 320, y: 0 });
  assert.equal(annotation, note);
});

test('统一契约样例可导入，拓扑批次和任务顺序与官方派生结果一致', async () => {
  async function example(name) {
    return JSON.parse(await readFile(new URL('../../tech/artifacts/examples/' + name + '.json', import.meta.url), 'utf8'));
  }
  const [officialSpec, proposal, blockedProposal, derivation, officialLayout] = await Promise.all(
    ['design-spec', 'task-proposal', 'task-proposal-blocked', 'plan-derivation', 'layout'].map(example),
  );
  assert.deepEqual(validateSpec(officialSpec), []);
  assert.deepEqual(validateTaskProposal(proposal), []);
  assert.deepEqual(validateTaskProposal(blockedProposal), []);
  const { issues, result } = assessPlan(proposal, officialSpec);
  assert.deepEqual(issues, []);
  assert.deepEqual(result.batches, derivation.parallel_batches);
  assert.deepEqual(result.order, derivation.ordered_task_ids);
  assert.ok(assessPlan(blockedProposal, officialSpec).issues.some(({ path }) => path.startsWith('/blocking_questions')));

  const { plan_revision_id, revision, ...geometry } = officialLayout;
  const { encodeLayout, decodeLayout } = await load('src/layout.ts');
  assert.deepEqual(encodeLayout(decodeLayout(geometry)), geometry);
});

test('空草稿可编辑，空提案必须有待补充问题', () => {
  assert.deepEqual(validatePlanStructure(emptyPlan()), []);
  assert.match(validateTaskProposal(emptyPlan())[0].message, /待补充问题/);
  assert.deepEqual(validateTaskProposal({ ...emptyPlan(), blocking_questions: ['请补充业务约束'] }), []);
  assert.deepEqual(validateTaskProposal(plan(task(' A '))), []);
  assert.equal(normalizeContractText(plan(task(' A '))).tasks[0].task_id, 'A');
  assert.match(validateTaskProposal(plan(task('A'), task(' A ')))[0].message, /重复/);
  const invalidSpec = { ...spec, background: '不合法\u0000字符' };
  assert.match(validateSpec(invalidSpec)[0].message, /控制字符/);
});

test('编排允许 1000 条依赖，超过契约上限则拒绝', () => {
  const dense = Array.from({ length: 46 }, (_, i) => task('T' + i, Array.from({ length: i }, (_, j) => 'T' + j)));
  const atLimit = plan(...dense.slice(0, -1), { ...dense.at(-1), dependencies: dense.at(-1).dependencies.slice(0, 10) });
  assert.equal(assessPlan(atLimit, spec).result.edges.length, 1000);
  assert.match(linkError(atLimit, 'T10', 'T45'), /1000/);
  const invalid = assessPlan(plan(...dense), spec);
  assert.equal(invalid.result, undefined);
  assert.match(invalid.issues[0].message, /1000.*1035/);
});

test('旧草稿与历史的嵌套注释坐标可读取，保存后按契约坐标往返', () => {
  const project = createProject('旧草稿');
  project.workspace.layout = {
    positions: { A: { x: 8, y: 12 } },
    notes: [{ id: 'note_1', position: { x: -20, y: 42 }, text: '备注', color: '#ffcc00' }],
    viewport: { x: 10, y: 15, zoom: 1.25 },
  };
  const withHistory = snapshot(project);
  let raw = JSON.stringify([withHistory]);
  const storage = { setItem: (_, value) => { raw = value; }, getItem: () => raw };
  assert.deepEqual(readProjects(storage), [withHistory]);
  writeProjects(storage, readProjects(storage));
  const stored = JSON.parse(raw)[0];
  for (const workspace of [stored.workspace, stored.history[0].workspace]) {
    assert.deepEqual(workspace.layout.notes[0], { id: 'note_1', x: -20, y: 42, text: '备注', color: '#ffcc00' });
  }
  assert.deepEqual(readProjects(storage), [withHistory]);
});

test('覆盖校验按需求优先级区分阻断和警告', () => {
  const requirement = spec.requirements[0];
  const mixedSpec = { ...spec, requirements: [
    requirement,
    { ...requirement, id: 'REQ_B', priority: 'should' },
    { ...requirement, id: 'REQ_C', priority: 'could' },
  ] };
  const noCoverage = { ...task('A'), source_requirement_ids: [], inputs: [{ kind: 'spec', requirement_id: 'REQ_A' }] };
  const blocked = assessPlan(plan(noCoverage), mixedSpec);
  assert.equal(blocked.result, undefined);
  assert.match(blocked.issues[0].message, /必需需求 REQ_A 未被任务覆盖/);
  assert.deepEqual(blocked.warnings.map(({ path }) => path), ['/requirements/1', '/requirements/2']);

  const valid = assessPlan(plan(task('A')), mixedSpec);
  assert.deepEqual(valid.issues, []);
  assert.deepEqual(valid.result.batches, [['A']]);
  assert.equal(valid.warnings.length, 2);
  assert.deepEqual(assessPlan(emptyPlan(), mixedSpec), { issues: [], warnings: [] });
});

test('关键假设和跨任务重复的假设 ID 阻止编排', () => {
  const a = { ...task('A'), assumptions: [{ id: 'ASSUME_A', text: '需要确认权限', impact: 'critical' }] };
  const b = { ...task('B'), assumptions: [{ id: ' ASSUME_A ', text: '估计可用', impact: 'low' }] };
  const assessment = assessPlan(plan(a, b), spec);
  assert.equal(assessment.result, undefined);
  assert.deepEqual(assessment.issues.map(({ path }) => path), ['/tasks/0/assumptions/0', '/tasks/1/assumptions/0']);
  assert.match(assessment.issues[0].message, /关键假设 ASSUME_A/);
  assert.match(assessment.issues[1].message, /假设 ID 重复.*任务 A/);
  assert.ok(assessPlan(plan(b), spec).result);
});

test('导入拒绝对象内的重复键，包括嵌套和转义等价键', async () => {
  for (const json of [
    '{"name":"first","name":"last"}',
    '{"items":[{"name":1,"\\u006eame":2}]}',
  ]) {
    await assert.rejects(readJson(new File([json], 'duplicate.json')), /JSON 包含重复键："name"/);
  }
  const separate = { items: [{ name: 1 }, { name: 2 }], text: '{"name":0,"name":0}' };
  assert.deepEqual(await readJson(new File([JSON.stringify(separate)], 'separate.json')), separate);
  await assert.rejects(readJson(new File([new Uint8Array([0xff])], 'invalid-encoding.json')), /UTF-8/);
});
