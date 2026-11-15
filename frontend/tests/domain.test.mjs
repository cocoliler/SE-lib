import assert from 'node:assert/strict';
import { test } from 'node:test';
import { build } from 'esbuild';
import { spec, task, plan } from './fixtures.mjs';

async function load(path) {
  const result = await build({ entryPoints: [path], bundle: true, platform: 'node', format: 'esm', write: false });
  return import('data:text/javascript;base64,' + Buffer.from(result.outputFiles[0].contents).toString('base64'));
}
const { assessPlan, emptyPlan, emptySpec, linkError, newTask, planState, removeTask, validateSpec, validatePlanStructure } = await load('src/plan.ts');
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
