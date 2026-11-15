import { newTask, type Plan, type Spec, type Task } from './plan';
import { createProject, type Project } from './storage';

export const meetingRoomPresetName = '会议室预约';

const spec: Spec = {
  schema_version: '1.0',
  product_name: '会议室预约工具',
  background: '团队目前通过群聊预约会议室，容易发生时段冲突。',
  goals: ['让团队成员预约会议室，并阻止时段冲突'],
  target_users: ['需要预约会议室的团队成员'],
  requirements: [{
    id: 'REQ-01',
    kind: 'functional',
    text: '成员可以选择会议室和时段提交预约。同一会议室的预约时段不得重叠。',
    priority: 'must',
    acceptance_criteria: ['空闲时段可以成功预约', '时段重叠时拒绝预约并显示原因'],
  }],
  technical_constraints: [],
  development_constraints: [],
  delivery_requirements: ['预约界面、时段冲突校验和测试报告'],
  acceptance_criteria: ['成功预约与冲突拒绝两条流程均通过测试'],
  supplemental_text: '',
  confirmed_assumptions: [],
};

const rulesId = 'RULES';
const rulesOutput = 'OUT-RULES';
const rulesInput: Task['inputs'][number] = { kind: 'task', task_id: rulesId, deliverable_id: rulesOutput };

const plan: Plan = {
  schema_version: '1.0',
  blocking_questions: [],
  tasks: [
    {
      ...newTask(rulesId),
      name: '定义预约规则',
      description: '明确预约时段、重叠判定及冲突提示。',
      category: 'design',
      stage: 'design',
      priority: 'high',
      assigned_role: 'analyst',
      inputs: [{ kind: 'spec', requirement_id: 'REQ-01' }],
      deliverables: [{ id: rulesOutput, text: '预约规则说明' }],
      acceptance_criteria: ['说明重叠和首尾相邻时段的判定规则'],
      source_requirement_ids: ['REQ-01'],
    },
    {
      ...newTask('FORM'),
      name: '实现预约表单',
      description: '提供会议室和起止时间选择，并展示预约结果。',
      category: 'development',
      stage: 'build',
      priority: 'high',
      assigned_role: 'developer',
      dependencies: [rulesId],
      inputs: [rulesInput],
      deliverables: [{ id: 'OUT-FORM', text: '可操作的预约表单' }],
      acceptance_criteria: ['可以填写完整预约信息，冲突结果可见'],
      source_requirement_ids: ['REQ-01'],
    },
    {
      ...newTask('TESTS'),
      name: '编写预约测试用例',
      description: '根据预约规则设计空闲、重叠和首尾相邻三类测试用例。',
      category: 'testing',
      stage: 'build',
      assigned_role: 'tester',
      dependencies: [rulesId],
      inputs: [rulesInput],
      deliverables: [{ id: 'OUT-TESTS', text: '预约测试用例清单' }],
      acceptance_criteria: ['每条用例包含输入和预期结果'],
      source_requirement_ids: ['REQ-01'],
    },
  ],
};

export function createMeetingRoomProject(projects: readonly Project[]): Project {
  const names = new Set(projects.map((project) => project.name));
  let name = meetingRoomPresetName;
  for (let index = 2; names.has(name); index++) name = meetingRoomPresetName + '（' + index + '）';
  const project = createProject(name);
  return {
    ...project,
    workspace: {
      ...project.workspace,
      spec: structuredClone(spec),
      plan: structuredClone(plan),
      source: 'PRESET',
      layout: {
        notes: [],
        positions: { RULES: { x: 0, y: 64 }, FORM: { x: 320, y: 0 }, TESTS: { x: 320, y: 128 } },
      },
    },
  };
}
