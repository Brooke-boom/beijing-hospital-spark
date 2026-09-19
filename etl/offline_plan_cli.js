#!/usr/bin/env node
// 离线主线引擎的命令行入口：读 stdin 的 {cases:[...]}，输出每个用例的 plan 结果。
// 供 etl/verify_offline_plan.py 做「离线复算 vs 后端接口」的双端一致性比对。
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const { PlanEngine } = require(path.join(ROOT, 'web', 'app.plan.js'));

function readStdin() {
  return fs.readFileSync(0, 'utf8');
}

const payload = JSON.parse(fs.readFileSync(path.join(ROOT, 'web', 'offline_plan_data.json'), 'utf8'));
const snap = JSON.parse(fs.readFileSync(path.join(ROOT, 'web', 'snapshot_data.json'), 'utf8'));

const engine = PlanEngine.create(payload, snap.institutions);
const input = JSON.parse(readStdin() || '{}');
const out = (input.cases || []).map((c) => engine.run(c));

process.stdout.write(JSON.stringify({ ok: true, results: out }));
