import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { test } from 'node:test';
import { setTimeout as delay } from 'node:timers/promises';
import { spec, task } from './fixtures.mjs';

const executable = [
  process.env.CHROME_BIN,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/chromium',
  '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].find((path) => path && existsSync(path));

async function until(check, description, timeout = 15000) {
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
    if (!message.id) {
      events.push(message);
      return;
    }
    pending.get(message.id)?.(message);
    pending.delete(message.id);
  });
  return {
    events,
    ws,
    open: new Promise((done, fail) => {
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

function workspaceFixture() {
  const edgeSet = new Set();
  for (let index = 0; index < 99; index++) edgeSet.add(`${index}:${index + 1}`);
  let seed = 8118;
  while (edgeSet.size < 200) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const source = seed % 100;
    seed = (seed * 1664525 + 1013904223) >>> 0;
    const target = seed % 100;
    if (source < target) edgeSet.add(`${source}:${target}`);
  }
  const dependencies = Array.from({ length: 100 }, () => []);
  for (const edge of edgeSet) {
    const [source, target] = edge.split(':').map(Number);
    dependencies[target].push(`T${String(source).padStart(3, '0')}`);
  }
  const tasks = dependencies.map((deps, index) =>
    task(`T${String(index).padStart(3, '0')}`, deps));
  const positions = Object.fromEntries(tasks.map((item, index) => [
    item.task_id,
    { x: (index % 10) * 320, y: Math.floor(index / 10) * 140 },
  ]));
  return [{
    id: 'performance-project',
    name: '大图性能验收',
    history: [],
    workspace: {
      spec,
      plan: { schema_version: '1.0', tasks, blocking_questions: [] },
      source: 'MANUAL',
      edited: true,
      orchestrated: true,
      layout: { positions, notes: [], viewport: { x: 0, y: 0, zoom: 0.28 } },
    },
  }];
}

test('Q04/Q08 大图性能与可访问性', { timeout: 120000 }, async (t) => {
  assert.ok(executable, '设置 CHROME_BIN 指向 Chromium 或 Chrome 浏览器');
  const outputPath = process.env.FLOWSTUDIO_PERF_OUTPUT;
  const profile = await mkdtemp(join(tmpdir(), 'flowstudio-performance-'));
  const chrome = spawn(executable, [
    '--headless=new',
    '--remote-debugging-port=0',
    '--no-first-run',
    '--disable-background-networking',
    '--window-size=1920,1080',
    '--force-device-scale-factor=1',
    '--user-data-dir=' + profile,
    'about:blank',
  ], { windowsHide: true, stdio: 'ignore' });
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
    } catch {
      response.writeHead(404).end();
    }
  });
  t.after(async () => {
    server.close();
    chrome.kill();
    await delay(150);
    const base = resolve(tmpdir());
    if (resolve(profile).startsWith(join(base, 'flowstudio-performance-'))) {
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
  await cdp.command('Input.enable').catch(() => {});

  async function evaluate(fn, ...args) {
    const { result, exceptionDetails } = await cdp.command('Runtime.evaluate', {
      expression: '(' + fn + ')(...' + JSON.stringify(args) + ')',
      returnByValue: true,
      awaitPromise: true,
    });
    assert.ok(!exceptionDetails, exceptionDetails?.exception?.description ?? '浏览器执行错误');
    return result.value;
  }
  async function click(label) {
    assert.ok(await evaluate((name) => {
      const button = [...document.querySelectorAll('button')].find((element) => !element.disabled
        && (element.textContent.trim() === name || element.getAttribute('aria-label') === name));
      button?.click();
      return !!button;
    }, label), '找不到按钮：' + label);
  }
  async function mouse(type, point, buttons = 0) {
    await cdp.command('Input.dispatchMouseEvent', {
      type, ...point, button: type === 'mouseMoved' ? 'none' : 'left', buttons, clickCount: 1,
    });
  }
  const origin = `http://127.0.0.1:${server.address().port}`;

  await cdp.command('Page.navigate', { url: origin });
  await until(() => evaluate(() => document.body?.innerText.includes('暂无项目')), '首页加载');
  await evaluate((project) => {
    localStorage.setItem('flowstudio.workspace.v1', JSON.stringify(project));
  }, workspaceFixture());
  await cdp.command('Page.reload');
  await until(() => evaluate(() => document.body?.innerText.includes('大图性能验收')), '性能项目加载');
  await click('任务规划');
  await click('工作流');
  const interactive = await until(
    () => evaluate((minimum) => {
      const count = document.querySelectorAll('.react-flow__node-task').length;
      const edges = document.querySelectorAll('.react-flow__edge').length;
      return count === minimum && edges === 200 && {
        elapsed_ms: performance.now(),
        nodes: count,
        edges,
      };
    }, 100),
    '100 任务和 200 条边渲染',
  );

  const contrast = await evaluate(() => {
    function rgb(value) {
      const match = value.match(/^#([0-9a-f]{6}|[0-9a-f]{3})$/i);
      if (!match) throw new Error('Expected hex color: ' + value);
      const hex = match[1].length === 3
        ? match[1].split('').map((part) => part + part).join('')
        : match[1];
      return [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16) / 255);
    }
    function luminance(value) {
      return rgb(value).map((channel) => channel <= 0.04045
        ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
        .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
    }
    function ratio(foreground, background) {
      const [a, b] = [luminance(foreground), luminance(background)].sort((left, right) => right - left);
      return (a + 0.05) / (b + 0.05);
    }
    const style = getComputedStyle(document.querySelector('.application'));
    const variable = (name) => style.getPropertyValue(name).trim();
    const pairs = {
      text: [variable('--text'), variable('--surface')],
      muted: [variable('--text-muted'), variable('--surface')],
      accent: [variable('--accent-ink'), variable('--surface')],
      danger: [variable('--danger'), variable('--danger-bg')],
      warning: [variable('--warning'), variable('--warning-bg')],
      success: [variable('--success'), variable('--success-bg')],
    };
    return Object.fromEntries(Object.entries(pairs).map(([name, values]) => [name, ratio(...values)]));
  });

  await click('深色外观');
  const darkContrast = await evaluate(() => {
    function rgb(value) {
      const match = value.match(/^#([0-9a-f]{6}|[0-9a-f]{3})$/i);
      if (!match) throw new Error('Expected hex color: ' + value);
      const hex = match[1].length === 3
        ? match[1].split('').map((part) => part + part).join('')
        : match[1];
      return [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16) / 255);
    }
    function luminance(value) {
      return rgb(value).map((channel) => channel <= 0.04045
        ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4)
        .reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
    }
    function ratio(foreground, background) {
      const [a, b] = [luminance(foreground), luminance(background)].sort((left, right) => right - left);
      return (a + 0.05) / (b + 0.05);
    }
    const style = getComputedStyle(document.querySelector('.application'));
    const variable = (name) => style.getPropertyValue(name).trim();
    return {
      text: ratio(variable('--text'), variable('--surface')),
      muted: ratio(variable('--text-muted'), variable('--surface')),
      accent: ratio(variable('--accent-ink'), variable('--surface')),
      danger: ratio(variable('--danger'), variable('--danger-bg')),
      warning: ratio(variable('--warning'), variable('--warning-bg')),
      success: ratio(variable('--success'), variable('--success-bg')),
    };
  });
  await click('深色外观');

  await evaluate(() => document.querySelector('.brand')?.focus());
  const focusNames = [];
  for (let index = 0; index < 12; index++) {
    await cdp.command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    await cdp.command('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
    const name = await evaluate(() => {
      const active = document.activeElement;
      return active?.getAttribute('aria-label') || active?.textContent?.trim() || active?.getAttribute('name') || '';
    });
    if (name) focusNames.push(name);
  }

  await click('任务列表');
  const keyboardTaskFocused = await evaluate(() => {
    const link = document.querySelector('.task-table .link');
    link?.focus();
    return !!link && document.activeElement === link;
  });
  await cdp.command('Input.dispatchKeyEvent', {
    type: 'rawKeyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13,
    nativeVirtualKeyCode: 13,
  });
  await cdp.command('Input.dispatchKeyEvent', {
    type: 'char', key: 'Enter', code: 'Enter', text: '\r', unmodifiedText: '\r',
    windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13,
  });
  await cdp.command('Input.dispatchKeyEvent', {
    type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13,
    nativeVirtualKeyCode: 13,
  });
  const keyboardTaskOpened = await until(
    () => evaluate(() => !!document.querySelector('.inspector')),
    '键盘打开任务详情',
    5000,
  );
  await click('工作流');

  await evaluate(async () => {
    document.querySelector('.graph')?.scrollIntoView({ block: 'center', inline: 'nearest' });
    await new Promise(requestAnimationFrame);
  });
  await click('自动布局');
  await delay(500);
  const fpsRuns = [];
  for (let run = 0; run < 3; run++) {
    const point = await until(() => evaluate(() => {
      const nodes = [...document.querySelectorAll('.react-flow__node-task')];
      for (const node of nodes) {
        const bounds = node.getBoundingClientRect();
        const target = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
        if (bounds.width > 0 && bounds.height > 0 && target.x > 40 && target.x < innerWidth - 40
          && target.y > 40 && target.y < innerHeight - 40
          && node.contains(document.elementFromPoint(target.x, target.y))) {
          return target;
        }
      }
      return null;
    }), '可拖动的大图任务');
    await mouse('mousePressed', point, 1);
    const framesPromise = cdp.command('Runtime.evaluate', {
      expression: `new Promise((resolve) => {
        const started = performance.now();
        let frames = 0;
        let longTasks = 0;
        const observer = new PerformanceObserver((list) => { longTasks += list.getEntries().length; });
        try { observer.observe({ type: 'longtask', buffered: false }); } catch {}
        function tick(now) {
          frames++;
          if (now - started < 10000) requestAnimationFrame(tick);
          else {
            observer.disconnect();
            resolve({ duration_ms: now - started, frames, long_tasks: longTasks, fps: frames / ((now - started) / 1000) });
          }
        }
        requestAnimationFrame(tick);
      })`,
      returnByValue: true,
      awaitPromise: true,
    });
    for (let step = 1; step <= 100; step++) {
      await mouse('mouseMoved', {
        x: point.x + Math.sin(step / 8) * 36,
        y: point.y + Math.cos(step / 9) * 24,
      }, 1);
      await delay(100);
    }
    await mouse('mouseReleased', point);
    const measured = await framesPromise;
    assert.ok(!measured.exceptionDetails, measured.exceptionDetails?.exception?.description);
    fpsRuns.push(measured.result.value);
  }

  const averageFps = fpsRuns.reduce((sum, item) => sum + item.fps, 0) / fpsRuns.length;
  const result = {
    q04: {
      task_count: 100,
      edge_count: 200,
      interactive_ms: interactive.elapsed_ms,
      target_interactive_ms: 2000,
      average_fps: averageFps,
      target_fps: 30,
      runs: fpsRuns,
      status: interactive.elapsed_ms <= 2000 && averageFps >= 30 ? 'PASS' : 'FAIL',
    },
    q08: {
      light_contrast: contrast,
      dark_contrast: darkContrast,
      keyboard_focus_count: new Set(focusNames).size,
      keyboard_focus_labels: [...new Set(focusNames)],
      keyboard_task_focused: keyboardTaskFocused,
      keyboard_task_opened: keyboardTaskOpened,
      contrast_pass: [...Object.values(contrast), ...Object.values(darkContrast)].every((value) => value >= 4.5),
      keyboard_pass: new Set(focusNames).size >= 5 && keyboardTaskFocused && keyboardTaskOpened,
    },
  };
  result.q08.status = result.q08.contrast_pass && result.q08.keyboard_pass ? 'PASS' : 'FAIL';
  if (outputPath) await writeFile(outputPath, JSON.stringify(result, null, 2) + '\n', 'utf8');
  assert.equal(result.q04.status, 'PASS', JSON.stringify(result.q04));
  assert.equal(result.q08.status, 'PASS', JSON.stringify(result.q08));
  assert.equal(cdp.events.filter((event) => event.method === 'Runtime.exceptionThrown').length, 0);
});
