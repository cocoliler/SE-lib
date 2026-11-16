import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';
import { spec, task, plan } from './fixtures.mjs';

const executable = [
  process.env.CHROME_BIN,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].find((path) => path && existsSync(path));

async function until(check, description, timeout = 6000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const result = await check();
    if (result) return result;
    await delay(55);
  }
  assert.fail('等待失败：' + description);
}

function socket(url) {
  const ws = new WebSocket(url);
  const events = [];
  const pending = new Map();
  let index = 0;
  ws.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data);
    if (!message.id) { events.push(message); return; }
    pending.get(message.id)?.(message);
    pending.delete(message.id);
  });
  return {
    events, ws, open: new Promise((done, fail) => {
      ws.addEventListener('open', done, { once: true });
      ws.addEventListener('error', fail, { once: true });
    }),
    command(method, params = {}) {
      return new Promise((done, fail) => {
        const id = ++index;
        pending.set(id, ({ error, result }) => error ? fail(new Error(error.message)) : done(result));
        ws.send(JSON.stringify({ id, method, params }));
      });
    },
  };
}

test('浏览器中的空项目、规格、任务、依赖、快照和 PNG', { timeout: 60000 }, async (t) => {
  assert.ok(executable, '设置 CHROME_BIN 指向 Chromium 或 Chrome 浏览器');
  const profile = await mkdtemp(join(tmpdir(), 'flowstudio-browser-'));
  const chrome = spawn(executable, ['--headless=new', '--remote-debugging-port=0', '--no-first-run', '--disable-background-networking',
    '--window-size=1460,1000', '--user-data-dir=' + profile, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
  const dist = resolve('dist');
  const server = createServer(async (request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    const file = resolve(dist, '.' + (pathname === '/' ? '/index.html' : pathname));
    try {
      if (!file.startsWith(dist + sep)) throw new Error('Invalid path');
      const bytes = await readFile(file);
      const type = { js: 'text/javascript', css: 'text/css', html: 'text/html' }[file.split('.').pop()];
      response.writeHead(200, { 'Content-Type': (type ?? 'application/octet-stream') + '; charset=utf-8' });
      response.end(bytes);
    } catch { response.writeHead(404).end(); }
  });
  t.after(async () => {
    server.close();
    chrome.kill();
    await delay(150);
    const base = resolve(tmpdir());
    if (resolve(profile).startsWith(join(base, 'flowstudio-browser-'))) {
      await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 150 }).catch(() => {});
    }
  });
  await new Promise((done) => server.listen(0, '127.0.0.1', done));
  const port = await until(async () => {
    const content = await readFile(join(profile, 'DevToolsActivePort'), 'utf8').catch(() => '');
    return content.split('\n')[0];
  }, 'Chromium 调试端口', 12000);
  const targets = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
  const cdp = socket(targets.find((target) => target.type === 'page').webSocketDebuggerUrl);
  t.after(() => cdp.ws.close());
  await cdp.open;
  await cdp.command('Runtime.enable');
  await cdp.command('Page.enable');
  await cdp.command('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: profile });
  async function evaluate(fn, ...args) {
    const { result, exceptionDetails } = await cdp.command('Runtime.evaluate', {
      expression: '(' + fn + ')(...' + JSON.stringify(args) + ')', returnByValue: true, awaitPromise: true,
    });
    assert.ok(!exceptionDetails, exceptionDetails?.exception?.description ?? '浏览器执行错误');
    return result.value;
  }
  const text = (value) => until(() => evaluate((substring) => document.body?.innerText.includes(substring), value), value);
  const click = async (label) => {
    assert.ok(await evaluate((name) => {
      const button = [...document.querySelectorAll('button')].find((element) => !element.disabled
        && (element.textContent.trim() === name || element.getAttribute('aria-label') === name));
      button?.click();
      return !!button;
    }, label), '找不到按钮：' + label);
  };
  const field = async (label, value) => {
    assert.ok(await evaluate((name, next) => {
      const input = [...document.querySelectorAll('label')].find((item) => item.firstElementChild.textContent === name)
        ?.querySelector('input, textarea, select');
      if (!input) return false;
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set.call(input, next);
      input.dispatchEvent(new Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
      return true;
    }, label, value), '找不到字段：' + label);
  };
  const uploadText = async (json, filename) => {
    await evaluate((data, name) => {
      const input = document.querySelector('input[type=file]');
      const transfer = new DataTransfer();
      transfer.items.add(new File([data], name, { type: 'application/json' }));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, json, filename);
  };
  const upload = (value, filename) => uploadText(JSON.stringify(value), filename);
  // Optional production-build smoke test against a real FlowStudio backend.
  if (process.env.FLOWSTUDIO_TEST_BACKEND_URL) {
    await cdp.command('Page.navigate', { url: process.env.FLOWSTUDIO_TEST_BACKEND_URL });
    await text('暂无项目');
    await click('创建项目');
    await field('项目名称', '前后端联调');
    await click('创建');
    await click('导入规格 JSON');
    await upload({ ...spec, requirements: ['R1', 'R2'].map((id) => ({ ...spec.requirements[0], id })) }, 'diamond-spec.json');
    await text('导入预览');
    await click('应用导入');
    await evaluate(() => document.querySelector('.backend-panel').open = true);
    await click('创建同名服务端项目');
    await text('已连接');
    assert.ok(await evaluate(() => {
      const left = document.querySelector('.workspace-sidebar');
      const tabs = document.querySelector('.project-content .tabs');
      return left.getBoundingClientRect().right < tabs.getBoundingClientRect().left;
    }));
    await click('收起左栏');
    assert.equal(await evaluate(() => document.querySelector('.sidebar-body').hidden), true);
    assert.ok(await evaluate(() => document.querySelector('.project-content .tabs').getBoundingClientRect().height));
    await click('展开左栏');
    assert.equal(await evaluate(() => document.querySelector('.backend-panel').open), true);
    await click('保存规格版本');
    await text('规格 v1 已同步');
    await evaluate(() => {
      const select = document.querySelector('.backend-panel select');
      select.value = 'TEST';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await evaluate(() => {
      const fetchFromBackend = window.fetch.bind(window);
      let interrupt = true;
      window.fetch = (url, options) => {
        if (interrupt && String(url).startsWith('/api/v1/planning-runs/') && options.method === 'GET') {
          interrupt = false;
          return Promise.reject(new TypeError('模拟断线'));
        }
        return fetchFromBackend(url, options);
      };
    });
    await click('发起规划');
    await text('继续查询规划结果');
    await click('继续查询规划结果');
    await text('规划完成');
    await text('用 4 项候选任务替换当前草稿');
    await click('用 4 项候选任务替换当前草稿');
    await click('服务端编排');
    await text('服务端编排完成');
    await click('保存计划版本');
    await text('已保存服务端计划 v1 · TEST / TEST');
    await evaluate(() => document.querySelector('.backend-versions').open = true);
    await click('读取服务端布局');
    await text('已读取布局版本');
    await click('保存布局');
    await text('布局已保存');
    const bundle = await evaluate(async () => {
      const link = document.querySelector('.backend-panel a');
      const response = await fetch(link.href);
      if (!response.ok) throw new Error('导出失败：' + response.status);
      return response.json();
    });
    assert.equal(bundle.plan_revision.source, 'TEST');
    assert.equal(bundle.plan_revision.parallel_batches.length, 3);
    assert.equal(bundle.layout.revision, 2);
    await click('保存计划版本');
    await text('已保存服务端计划 v2');
  }

  await cdp.command('Page.navigate', { url: 'http://127.0.0.1:' + server.address().port });
  await text('暂无项目');
  assert.equal(await evaluate(() => localStorage.getItem('flowstudio.workspace.v1')), null);
  await click('创建项目');
  await field('项目名称', '浏览器验收');
  await click('创建');
  await text('空项目 · 尚无设计规格');
  assert.equal(await evaluate(() => [...document.querySelectorAll('button')].find((button) => button.textContent === '任务规划').disabled), true);
  await click('填写规格');
  await text('规格草稿');
  assert.equal(await evaluate(() => document.querySelector('.spec-options').open), false);
  await click('标示待填写项');
  await text('请填写产品名称');
  assert.equal(await evaluate(() => document.querySelector('.spec-form input').getAttribute('aria-invalid')), 'true');
  await click('隐藏必填提示');
  assert.equal(await evaluate(() => document.querySelector('.spec-form input').hasAttribute('aria-invalid')), false);
  await field('产品名称', spec.product_name);
  await field('产品背景', spec.background);
  await field('目标', spec.goals[0]);
  await field('目标用户', spec.target_users[0]);
  await field('交付要求', spec.delivery_requirements[0]);
  await field('总体验收标准', spec.acceptance_criteria[0]);
  await text('添加至少一项需求');
  assert.equal(await evaluate(() => !!document.querySelector('.spec-page .issues')), false);
  if (process.env.FLOWSTUDIO_SPEC_SCREENSHOT) {
    const image = await cdp.command('Page.captureScreenshot', { format: 'png' });
    await writeFile(process.env.FLOWSTUDIO_SPEC_SCREENSHOT, Buffer.from(image.data, 'base64'));
  }
  await cdp.command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  assert.ok(await evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  assert.equal(await evaluate(() => getComputedStyle(document.querySelector('.spec-grid')).gridTemplateColumns.split(' ').length), 1);
  await cdp.command('Emulation.clearDeviceMetricsOverride');
  await click('添加需求');
  await field('需求 ID', 'REQ_A');
  await field('需求描述', spec.requirements[0].text);
  await field('需求验收标准', spec.requirements[0].acceptance_criteria[0]);
  await text('规格已通过基础校验');
  await click('导出规格 JSON');
  const specFile = await until(async () => (await readdir(profile)).find((file) => file === 'design-spec.json'), '规格导出文件');
  assert.deepEqual(JSON.parse(await readFile(join(profile, specFile), 'utf8')), spec);
  await click('导入规格 JSON');
  await upload({ ...spec, product_name: '导入后规格', requirements: [
    ...spec.requirements, { ...spec.requirements[0], id: 'REQ_OPTIONAL', priority: 'should' },
  ] }, 'spec.json');
  await text('导入预览');
  await click('应用导入');
  assert.equal(await evaluate(() => document.querySelector('.spec-form input').value), '导入后规格');
  await click('进入任务规划');
  await text('从后端工作区发起规划，或手动编辑任务');
  await text('暂无任务规划');
  await click('创建首个任务');
  await text('计划有校验问题');
  await field('任务名称', '手动任务');
  await field('类别', 'dev');
  await field('阶段', 'build');
  await field('建议角色', 'developer');
  await field('任务描述', '完成工程变更');
  await click('添加交付物');
  await field('交付内容', '变更记录');
  await field('任务验收标准', '构建通过');
  await text('必需需求 REQ_A 未被任务覆盖');
  assert.equal(await evaluate(() => document.querySelector('.reorchestrate').disabled), true);
  await field('关联需求 ID', 'REQ_A');
  await text('需求 REQ_OPTIONAL 未被任务覆盖');
  await click('重新编排');
  await text('编排有效');
  await field('任务名称', '已修改任务');
  await text('待重新编排');
  assert.equal(await evaluate(() => !!document.querySelector('[aria-label="编排结果"]')), false);
  await click('重新编排');
  await text('编排有效');
  await click('导出任务 JSON');
  const planFile = await until(async () => (await readdir(profile)).find((file) => file === 'task-plan.json'), '任务导出文件');
  assert.equal(JSON.parse(await readFile(join(profile, planFile), 'utf8')).tasks[0].name, '已修改任务');
  await click('导入任务 JSON');
  await uploadText('{"tasks":[],"tasks":[]}', 'duplicate.json');
  await text('JSON 包含重复键："tasks"');
  await upload(plan(), 'empty-proposal.json');
  await text('任务为空时，提案必须包含至少一个待补充问题');
  await upload({ tasks: [{ task_id: 'A' }] }, 'invalid.json');
  await text('缺少必填字段');
  assert.match(await evaluate(() => document.body.innerText), /已修改任务/);
  await upload(plan(task('A', ['B']), task('B', ['A'])), 'cycle.json');
  await text('循环依赖');
  await click('取消导入');
  const critical = { ...task('A'), assumptions: [{ id: 'ASSUME_A', text: '仍需确认权限', impact: 'critical' }] };
  await upload(plan(critical), 'critical.json');
  await text('关键假设 ASSUME_A 需要补充信息');
  await click('应用导入');
  await text('计划有校验问题');
  assert.equal(await evaluate(() => document.querySelector('.reorchestrate').disabled), true);
  await click('保存到浏览器');
  await text('改动已保存到此浏览器');
  await upload(plan(task('A'), task('B'), task('C', ['A'])), 'valid.json');
  await text('导入预览');
  await text('校验通过');
  await text('校验通过 · 有警告');
  const importStats = await evaluate(() => [...document.querySelectorAll('.import-stats dd')].map((item) => item.textContent));
  assert.deepEqual(importStats, ['3', '1', '2', '2']);
  assert.match(await evaluate(() => document.querySelector('.json-preview pre').textContent), /schema_version/);
  await click('应用导入');
  await text('IMPORTED');
  await text('任务已就绪');
  await click('任务 B');
  const selected = await evaluate(() => {
    const select = document.querySelector('select[aria-label="上游任务"]');
    select.value = 'A';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return select.value;
  });
  assert.equal(selected, 'A');
  await click('添加依赖');
  await text('待重新编排');
  await click('重新编排');
  await text('2 个并行批次');
  await click('关闭任务详情');
  await click('工作流');
  await until(() => evaluate(() => document.querySelectorAll('.react-flow__node-task').length === 3), '三个任务节点');
  await until(() => evaluate(() => !!document.querySelector('.task-navigator')), '画布任务索引');
  await evaluate(() => {
    const input = document.querySelector('[aria-label="搜索画布任务"]');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '任务 C');
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await until(() => evaluate(() => document.querySelectorAll('.task-navigator li').length === 1), '过滤画布任务');
  await evaluate(() => document.querySelector('.task-navigator li button').click());
  await until(() => evaluate(() => document.querySelector('.inspector input').value === '任务 C'), '从索引定位任务');
  await click('关闭任务详情');
  await click('任务索引');
  assert.equal(await evaluate(() => !!document.querySelector('.task-navigator')), false);
  await click('任务索引');
  await click('深色外观');
  assert.equal(await evaluate(() => document.querySelector('.application').dataset.theme), 'dark');
  assert.equal(await evaluate(() => localStorage.getItem('flowstudio.theme')), 'dark');
  if (process.env.FLOWSTUDIO_DARK_SCREENSHOT) {
    const image = await cdp.command('Page.captureScreenshot', { format: 'png' });
    await writeFile(process.env.FLOWSTUDIO_DARK_SCREENSHOT, Buffer.from(image.data, 'base64'));
  }
  await click('深色外观');
  await until(() => evaluate(() => document.querySelector('.application').dataset.theme === 'light'), '恢复浅色外观');
  await click('自动布局');
  await until(() => evaluate(() => document.querySelectorAll('.react-flow__edge').length === 2), '两条依赖边');
  if (process.env.FLOWSTUDIO_SCREENSHOT) {
    const image = await cdp.command('Page.captureScreenshot', { format: 'png' });
    await writeFile(process.env.FLOWSTUDIO_SCREENSHOT, Buffer.from(image.data, 'base64'));
  }
  const node = await until(() => evaluate(async () => {
    for (let frame = 0; frame < 3; frame++) await new Promise(requestAnimationFrame);
    const item = document.querySelector('.react-flow__node-task');
    const bounds = item.getBoundingClientRect();
    const point = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
    return item.contains(document.elementFromPoint(point.x, point.y)) && { ...point, transform: item.style.transform };
  }), '可拖动的任务节点');
  async function mouse(type, point, buttons = 0) {
    await cdp.command('Input.dispatchMouseEvent', {
      type, ...point, button: type === 'mouseMoved' ? 'none' : 'left', buttons, clickCount: 1,
    });
  }
  const watchVisibility = (selector) => evaluate((target) => {
    const card = document.querySelector(target);
    const wasHidden = (records) => card.style.visibility === 'hidden'
      || records.some(({ oldValue }) => oldValue?.includes('visibility: hidden'));
    let hidden = false;
    const observer = new MutationObserver((records) => { hidden ||= wasHidden(records); });
    observer.observe(card, { attributes: true, attributeFilter: ['style'], attributeOldValue: true });
    window.finishDragVisibilityCheck = () => {
      hidden ||= wasHidden(observer.takeRecords());
      observer.disconnect();
      return hidden;
    };
  }, selector);
  await watchVisibility('.react-flow__node-task');
  const edgePath = await evaluate(() => {
    const canvas = document.querySelector('.graph');
    let edgeRemoved = false;
    function track(records) {
      for (const record of records) {
        for (const item of record.removedNodes) {
          if (item instanceof Element && (item.matches('.react-flow__edge') || item.querySelector('.react-flow__edge'))) {
            edgeRemoved = true;
          }
        }
      }
    }
    const observer = new MutationObserver(track);
    observer.observe(canvas, { childList: true, subtree: true });
    window.finishEdgeVisibilityCheck = () => {
      track(observer.takeRecords());
      observer.disconnect();
      return edgeRemoved;
    };
    return canvas.querySelector('.react-flow__edge-path').getAttribute('d');
  });
  await mouse('mousePressed', { x: node.x, y: node.y }, 1);
  await mouse('mouseMoved', { x: node.x + 35, y: node.y + 24 }, 1);
  await mouse('mouseMoved', { x: node.x + 65, y: node.y + 42 }, 1);
  await mouse('mouseReleased', { x: node.x + 65, y: node.y + 42 });
  await until(() => evaluate((transform) => document.querySelector('.react-flow__node-task').style.transform !== transform,
    node.transform), '拖动任务节点');
  const nextPaint = () => evaluate(async () => {
    for (let frame = 0; frame < 2; frame++) await new Promise(requestAnimationFrame);
  });
  await nextPaint();
  assert.equal(await evaluate(() => window.finishDragVisibilityCheck()), false, '任务卡在拖动和松手时持续可见');
  assert.equal(await evaluate(() => window.finishEdgeVisibilityCheck()), false, '连线在拖动和松手时持续挂载');
  assert.notEqual(await evaluate(() => document.querySelector('.react-flow__edge-path').getAttribute('d')), edgePath);
  await click('添加注释');
  await text('点击画布放置注释');
  const point = await evaluate(() => {
    const canvas = document.querySelector('.flow');
    canvas.scrollIntoView({ block: 'center' });
    const { x, y, width, height } = canvas.getBoundingClientRect();
    for (const horizontal of [0.18, 0.78, 0.12, 0.64]) {
      for (const vertical of [0.25, 0.45, 0.65]) {
        const point = { x: x + width * horizontal, y: y + height * vertical };
        if (document.elementFromPoint(point.x, point.y)?.classList.contains('react-flow__pane')) return point;
      }
    }
    throw new Error('找不到可放置注释的画布空白点');
  });
  await mouse('mousePressed', point, 1);
  await mouse('mouseReleased', point);
  const noteInput = '.note-card textarea';
  await until(() => evaluate((selector) => !!document.querySelector(selector), noteInput), '画布注释输入框');
  await evaluate((selector) => document.querySelector(selector).focus(), noteInput);
  await cdp.command('Input.insertText', { text: '拖动与画布持久化验证' });
  assert.equal(await evaluate((selector) => document.querySelector(selector).value, noteInput), '拖动与画布持久化验证');
  assert.equal(await evaluate(() => !!document.querySelector('[aria-label="注释详情"]')), false);
  await click('任务列表');
  await click('任务 A');
  await click('工作流');
  await text('任务详情');
  const noteDrag = await until(() => evaluate(async () => {
    await new Promise(requestAnimationFrame);
    const heading = document.querySelector('.note-heading strong');
    const node = heading.closest('.react-flow__node');
    const { x, y, width, height } = heading.getBoundingClientRect();
    const point = { x: x + width / 2, y: y + height / 2 };
    return heading.contains(document.elementFromPoint(point.x, point.y)) && {
      ...point, transform: node.style.transform, canvasWidth: document.querySelector('.graph').clientWidth,
    };
  }), '注释标题可拖动');
  await watchVisibility('.react-flow__node-note');
  await mouse('mousePressed', { x: noteDrag.x, y: noteDrag.y }, 1);
  await mouse('mouseMoved', { x: noteDrag.x + 7, y: noteDrag.y + 3 }, 1);
  let lastTransform = noteDrag.transform;
  for (const distance of [18, 36, 54, 72]) {
    await mouse('mouseMoved', { x: noteDrag.x + distance, y: noteDrag.y + distance / 2 }, 1);
    lastTransform = await until(() => evaluate((before) => {
      const node = document.querySelector('.react-flow__node-note');
      return node.style.transform !== before && node.style.visibility === 'visible' && node.style.transform;
    }, lastTransform), '拖动时注释持续可见并跟随鼠标');
    assert.equal(await evaluate(() => document.querySelector('.graph').clientWidth), noteDrag.canvasWidth);
  }
  await mouse('mouseReleased', { x: noteDrag.x + 72, y: noteDrag.y + 36 });
  await nextPaint();
  assert.equal(await evaluate(() => document.querySelector('.react-flow__node-note').style.transform), lastTransform);
  assert.equal(await evaluate(() => window.finishDragVisibilityCheck()), false, '注释在拖动和松手期间保持可见');
  const closeInspector = await evaluate(() => {
    const button = document.querySelector('[aria-label="关闭任务详情"]');
    button.scrollIntoView({ block: 'nearest' });
    const rect = button.getBoundingClientRect();
    return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
  });
  await mouse('mousePressed', closeInspector, 1);
  await mouse('mouseReleased', closeInspector);
  await until(() => evaluate(() => !document.querySelector('.inspector')), '任务详情已关闭');
  await click('自动布局');
  await nextPaint();
  assert.equal(await evaluate(() => document.querySelector('.react-flow__node-note').style.transform), lastTransform);
  await click('导出 PNG');
  const png = await until(async () => {
    const message = await evaluate(() => document.querySelector('.app-footer [role="status"]').textContent);
    assert.doesNotMatch(message, /无法|画布为空/);
    return (await readdir(profile)).find((file) => file.endsWith('.png'));
  }, 'PNG 文件');
  assert.equal((await readFile(join(profile, png))).subarray(1, 4).toString(), 'PNG');
  await click('保存快照');
  await text('记录快照');
  const saved = await evaluate(() => JSON.parse(localStorage.getItem('flowstudio.workspace.v1'))[0]);
  assert.deepEqual(saved.workspace.plan.tasks.find((item) => item.task_id === 'B').dependencies, ['A']);
  assert.ok(Object.keys(saved.workspace.layout.positions).length === 3);
  assert.equal(saved.history.length, 1);
  assert.equal(saved.workspace.layout.notes[0].text, '拖动与画布持久化验证');
  const savedPoint = saved.workspace.layout.notes[0];
  const renderedPoint = await evaluate((transform) => {
    const matrix = new DOMMatrix(transform);
    return { x: matrix.e, y: matrix.f };
  }, lastTransform);
  assert.ok(Math.abs(renderedPoint.x - savedPoint.x) < 0.01 && Math.abs(renderedPoint.y - savedPoint.y) < 0.01);
  await cdp.command('Page.reload');
  await text('浏览器验收');
  await text('规格已通过基础校验');
  await click('任务规划');
  await text('编排有效');
  await click('工作流');
  await until(() => evaluate(() => document.querySelectorAll('.react-flow__node-note').length === 1), '布局和注释恢复');
  assert.equal(await evaluate((selector) => document.querySelector(selector).value, noteInput), '拖动与画布持久化验证');
  await evaluate((selector) => document.querySelector(selector).focus(), noteInput);
  await click('删除注释');
  await until(() => evaluate((selector) => !document.querySelector(selector), noteInput), '从卡片删除注释');
  await click('任务列表');
  await click('任务 A');
  await click('删除任务');
  await click('确认删除');
  assert.equal(await evaluate(() => document.querySelectorAll('tbody tr').length), 2);
  await text('待重新编排');
  await click('本地历史');
  assert.ok(await evaluate(() => {
    const record = document.querySelector('.history-row > button');
    record?.click();
    return !!record;
  }));
  await text('只读快照');
  await click('任务 B');
  assert.equal(await evaluate(() => document.querySelector('.inspector fieldset').disabled), true);
  await cdp.command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  assert.ok(await evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await click('保存快照');
  await text('记录快照');
  await click('任务规划');
  await click('手动创建任务');
  await click('本地历史');
  await evaluate(() => { window.confirm = () => true; });
  await evaluate(() => {
    const row = document.querySelector('.history-row');
    row.querySelector('button').click();
    row.querySelector('button.danger').click();
  });
  await text('已删除本地快照');
  assert.equal(await evaluate(() => document.querySelectorAll('.history-row').length), 1);
  await click('清空本地历史');
  await text('暂无快照');
  const persisted = await evaluate(() => JSON.parse(localStorage.getItem('flowstudio.workspace.v1'))[0]);
  assert.equal(persisted.history.length, 0);
  assert.equal(persisted.workspace.plan.tasks.length, 2);
  await click('任务规划');
  assert.equal(await evaluate(() => document.querySelectorAll('tbody tr').length), 3);
  await click('保存到浏览器');
  await cdp.command('Page.reload');
  await text('规格已通过基础校验');
  await click('本地历史');
  await text('暂无快照');
  await click('新建项目');
  await click('从示例创建');
  await text('规格已通过基础校验');
  await click('进入任务规划');
  await text('PRESET');
  await text('定义预约规则');
  await click('重新编排');
  await text('2 个并行批次');
  const projects = await evaluate(() => JSON.parse(localStorage.getItem('flowstudio.workspace.v1')));
  assert.equal(projects.length, 2);
  assert.equal(projects[1].name, '会议室预约');
  assert.equal(projects[1].workspace.source, 'PRESET');
  assert.equal(projects[1].workspace.plan.tasks.length, 3);
  await click('切换项目');
  await click('浏览器验收');
  await click('切换项目');
  assert.equal(await evaluate(() => document.querySelectorAll('.project-remove').length), 1);
  assert.equal(await evaluate(() => document.querySelector('.project-remove').parentElement.dataset.active), 'true');
  await evaluate(() => { window.confirm = () => false; });
  await click('删除本地项目 浏览器验收');
  assert.equal(await evaluate(() => document.querySelectorAll('.project-option').length), 3);
  await evaluate(() => { window.confirm = () => true; });
  await click('删除本地项目 浏览器验收');
  await text('已删除本地项目');
  assert.equal(await evaluate(() => document.querySelector('.project-remove')), null);
  assert.deepEqual(await evaluate(() => JSON.parse(localStorage.getItem('flowstudio.workspace.v1'))), [projects[1]]);
  assert.deepEqual(cdp.events.filter((event) => event.method === 'Runtime.exceptionThrown'), []);
});
