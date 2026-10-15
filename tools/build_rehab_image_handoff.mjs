import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const input = path.resolve(process.argv[2] || 'E:/git冲突问题/rehab image');
const runtime = path.join(root, '.runtime/rehab-image-handoff');
const requireRuntime = createRequire(path.join(runtime, 'package.json'));
const { Workbook } = await import(pathToFileURL(requireRuntime.resolve('@oai/artifact-tool')).href);
const docs = 'docs/rehab-library/image-handoff';
const assets = 'rehab_codex_single_camera_v2_1/assets/rehab-library-images';
const version = '1.0';
const sourceFile = path.join(root, 'docs/rehab-library/SOURCE_v1.0.md');
const planFile = path.join(input, '动作分步骤示范图制作清单_v1.0.md');
const selectionFile = path.join(root, 'tools/rehab-image-handoff/selection.json');
const requiredFields = [
  ['region', '区域'], ['level', '等级'], ['objective', '目标'],
  ['equipment', '器材'], ['start_conditions', '开始条件'],
  ['preparation', '准备与起始位'], ['instructions', '操作步骤'],
  ['key_points', '关键要领'], ['common_errors', '常见错误'],
  ['source_dose', '试做与候选剂量／评估协议'], ['regression', '退阶'],
  ['progression', '进阶'], ['stop_conditions', '停止或调整条件'],
  ['camera', '机位与画面'], ['observable', '视觉可以观察'],
  ['not_observable', '视觉不能直接判定'], ['insufficient_observation', '观察不足时'],
  ['action_sources', '动作出处与对应原文'], ['evidence_scope', '证据性质与适用范围'],
  ['basis', '依据'],
];
const optionalFields = [
  ['single_person', '单人适用'], ['vision_module', '视觉模块'],
  ['reassessment', '复评与训练成果'], ['design_trace', '设计与见习追溯'],
];
const categories = {
  mobility_balance: '步行、平衡与综合功能', hip: '髋与下肢后侧链',
  knee: '膝与坐站蹲起', ankle_foot: '踝足与小腿',
  lumbar_pelvis: '腰骨盆与躯干稳定', thoracic_trunk: '胸部与躯干活动',
  neck: '颈部', shoulder: '肩与肩带', elbow_forearm: '肘与前臂',
  wrist_hand: '腕与手', conditioning: '综合活动耐受与组合动作',
};

function categoryFor(n) {
  const overrides = {
    14: 'hip', 20: 'hip', 21: 'mobility_balance', 29: 'mobility_balance',
    30: 'mobility_balance', 33: 'mobility_balance', 42: 'lumbar_pelvis',
    62: 'wrist_hand', 70: 'hip', 101: 'mobility_balance',
    102: 'mobility_balance', 103: 'mobility_balance', 105: 'mobility_balance',
    122: 'ankle_foot', 131: 'lumbar_pelvis', 183: 'conditioning',
    184: 'hip', 185: 'conditioning',
  };
  if (overrides[n]) return overrides[n];
  for (const [end, category] of [
    [5, 'mobility_balance'], [10, 'hip'], [19, 'knee'], [20, 'hip'],
    [33, 'ankle_foot'], [37, 'lumbar_pelvis'], [42, 'thoracic_trunk'],
    [44, 'lumbar_pelvis'], [47, 'neck'], [56, 'shoulder'],
    [58, 'elbow_forearm'], [60, 'wrist_hand'], [61, 'elbow_forearm'],
    [63, 'wrist_hand'], [71, 'knee'], [91, 'hip'], [106, 'knee'],
    [118, 'ankle_foot'], [121, 'mobility_balance'], [126, 'lumbar_pelvis'],
    [132, 'thoracic_trunk'], [146, 'lumbar_pelvis'], [152, 'neck'],
    [173, 'shoulder'], [175, 'elbow_forearm'], [180, 'wrist_hand'],
    [182, 'elbow_forearm'],
  ]) if (n <= end) return category;
  throw new Error(`Unclassified sequence ${n}`);
}

const slash = value => value.split(path.sep).join('/');
const sha = buffer => createHash('sha256').update(buffer).digest('hex').toUpperCase();
const pad = n => String(n).padStart(2, '0');
const check = (condition, message) => { if (!condition) throw new Error(message); };
function field(body, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const matches = body.matchAll(new RegExp(`\\*\\*${escaped}[：:]?\\*\\*[：:]?\\s*(.*?)(?=\\*\\*|$)`, 'gs'));
  return [...matches].map(match => match[1].trim()).join('\n\n');
}
function lineField(body, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return [...body.matchAll(new RegExp(`^${escaped}：(.+)$`, 'gm'))].map(match => match[1].trim()).join('\n');
}
async function walk(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await walk(full));
    else if (entry.isFile()) result.push(full);
  }
  return result.sort();
}
async function save(relative, text) {
  const destination = path.join(root, relative);
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.writeFile(destination, text, 'utf8');
}
async function copyChecked(source, destination, sourceHash) {
  const target = path.join(root, destination);
  await fs.mkdir(path.dirname(target), { recursive: true });
  let current;
  try { current = await fs.readFile(target); } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  if (current) check(sha(current) === sourceHash, `Refusing to overwrite changed file: ${destination}`);
  else await fs.copyFile(source, target);
}
function pngInfo(buffer, filename) {
  check(buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])), `Invalid PNG: ${filename}`);
  check(buffer.toString('ascii', 12, 16) === 'IHDR', `Missing PNG header: ${filename}`);
  const width = buffer.readUInt32BE(16), height = buffer.readUInt32BE(20);
  check(width > 0 && height > 0, `Empty PNG dimensions: ${filename}`);
  return { sha256: sha(buffer), bytes: buffer.length, width, height };
}
function grouping(sequence, step) {
  if (['055', '158'].includes(sequence)) {
    const route = ['I', 'Y', 'T', 'W'][Math.floor((step - 1) / 2)];
    return { group_id: route, group_label: `${route}路线（独立图组）` };
  }
  if (sequence === '116') {
    const i = Math.floor((step - 1) / 2);
    return { group_id: ['dorsiflexion', 'plantarflexion', 'inversion', 'eversion'][i],
      group_label: `${['背屈', '跖屈', '内翻', '外翻'][i]}（独立方向）` };
  }
  if (sequence === '052') return { group_id: step <= 2 ? 'hair' : 'back',
    group_label: step <= 2 ? '梳头（独立任务）' : '够后腰（独立任务）' };
  return { group_id: 'base', group_label: '基础版本（执行顺序以顺序复用说明为准）' };
}

const sourceBuffer = await fs.readFile(sourceFile);
const planBuffer = await fs.readFile(planFile);
const source = sourceBuffer.toString('utf8').replace(/\r\n/g, '\n');
const plan = planBuffer.toString('utf8').replace(/\r\n/g, '\n');
const parsedCards = new Map();
for (const match of source.matchAll(/^#### ([ET]-[A-Z]+-\d+)｜([^\n]+)\n(.*?)(?=^#{1,4} |(?![\s\S]))/gms)) {
  const [, id, name, bodyRaw] = match;
  const body = bodyRaw.replace(/\s*(?:---\s*)?(?:<a id="[^"]+"><\/a>\s*)?$/, '').trim();
  check(!parsedCards.has(id), `Duplicate source action: ${id}`);
  const clinical = Object.fromEntries([...requiredFields, ...optionalFields].map(([key, label]) => [key, field(body, label)]));
  for (const [key] of requiredFields) check(clinical[key], `Missing required source field ${id}/${key}`);
  parsedCards.set(id, { id, name: name.trim(), source_content: body, ...clinical,
    source_refs: [...new Set([...body.matchAll(/\[([A-Z]+-S\d+)\]/g)].map(m => m[1]))] });
}
check(parsedCards.size === 185, `Expected 185 source cards, got ${parsedCards.size}`);

const plans = [];
for (const match of plan.matchAll(/^### (\d{3}) ([ET]-[A-Z]+-\d+)｜([^\n]+)\n(.*?)(?=^#{1,3} |(?![\s\S]))/gms)) {
  const [, sequence, id, name, body] = match;
  const expected = Number(body.match(/首轮示范图：\*\*(\d+)\s*张\*\*/)?.[1]);
  const frames = [];
  for (const line of body.split('\n')) {
    if (!/^\|\s*\d{2}\s*\|/.test(line)) continue;
    const columns = line.split('|').slice(1, -1).map(s => s.trim());
    check(columns.length === 3, `Unexpected step table in ${sequence}: ${line}`);
    frames.push({ step_number: Number(columns[0]), frame_description: columns[1], check_points: columns[2] });
  }
  check(Number.isInteger(expected) && frames.length === expected, `Step count mismatch ${sequence}`);
  check(frames.every((f, i) => f.step_number === i + 1), `Nonsequential frames ${sequence}`);
  check(parsedCards.get(id)?.name === name.trim(), `Action name/ID mismatch: ${sequence}/${id}`);
  plans.push({ sequence, id, name: name.trim(), expected,
    image_version_camera: lineField(body, '基础版本与机位'),
    image_type: body.match(/示范类型：([^\n]+)/)?.[1].trim() || '',
    sequence_reuse: lineField(body, '顺序／复用'),
    extensions: lineField(body, '扩展版本（不计入首轮）'), frames, image_plan_content: body.trim() });
}
check(plans.length === 185 && plans.reduce((n, a) => n + a.expected, 0) === 471, 'Expected 185 actions / 471 frames');
check(plans.every((a, i) => Number(a.sequence) === i + 1), 'Invalid global sequence');
const selection = JSON.parse(await fs.readFile(selectionFile, 'utf8'));
const overrides = selection.selections;
const inputFiles = await walk(input);
const imageInputs = inputFiles.filter(f => /\.png$/i.test(f) && /^(assess|train)\//.test(slash(path.relative(input, f))));
const candidates = [];
const slots = new Map();
const overviews = new Map();
for (const filename of imageInputs) {
  const relative = slash(path.relative(input, filename));
  const base = path.basename(filename);
  const stepMatch = base.match(/^(\d{3})_([ET]-[A-Z]+-\d+)_s(\d{2})(.*?)\.png$/i);
  const overviewMatch = base.match(/^(\d{3})_([ET]-[A-Z]+-\d+)_([^\n]+)\.png$/i);
  const candidate = { source_path: relative, source_filename: base, ...pngInfo(await fs.readFile(filename), relative),
    role: stepMatch ? 'step_candidate' : 'overview_candidate', selected: false,
    selection_basis: '', selection_evidence: [], archive_path: '' };
  const match = stepMatch || overviewMatch;
  check(match, `Unrecognized image name: ${relative}`);
  candidate.sequence = match[1]; candidate.action_id = match[2];
  check(plans[Number(candidate.sequence) - 1]?.id === candidate.action_id, `Image ID mismatch ${relative}`);
  if (stepMatch) {
    candidate.step_number = Number(stepMatch[3]);
    candidate.slot_id = `${candidate.sequence}_${candidate.action_id}_s${stepMatch[3]}`;
    candidate.is_standard_candidate = /^(_v\d+)?$/.test(stepMatch[4]);
    const list = slots.get(candidate.slot_id) || [];
    list.push(candidate); slots.set(candidate.slot_id, list);
  } else {
    candidate.slot_id = `${candidate.sequence}_${candidate.action_id}_overview`;
    const list = overviews.get(candidate.action_id) || [];
    list.push(candidate); overviews.set(candidate.action_id, list);
  }
  candidates.push(candidate);
}

const images = [], actions = [], steps = [], unresolvedSelections = [];
async function selectImage(slotId, list, destination) {
  let chosen;
  const override = overrides[slotId];
  const standard = list.filter(c => c.role === 'overview_candidate' || c.is_standard_candidate);
  const distinctNames = [...new Set(standard.map(c => c.source_filename))];
  const distinctHashes = [...new Set(standard.map(c => c.sha256))];
  if (override) {
    if (override.filename) chosen = standard.find(c => c.source_filename === override.filename && !c.source_path.includes('选用/'))
      || standard.find(c => c.source_filename === override.filename);
    check(!override.filename || chosen, `Recorded selection file missing: ${slotId}/${override.filename}`);
  } else if (distinctNames.length === 1 || distinctHashes.length === 1) chosen = standard.find(c => !c.source_path.includes('选用/')) || standard[0];
  else if (distinctNames.length > 1) unresolvedSelections.push(slotId);
  if (!chosen) return { slot_id: slotId, image_path: '', expected_image_path: destination,
    file_status: list.length ? 'selection_pending' : 'missing', sha256: '', bytes: 0,
    width: 0, height: 0, selected_source: '', selection_basis: override?.note || '',
    selection_evidence: [], pose_review_status: 'not_reaudited' };
  chosen.selected = true;
  chosen.selection_basis = override ? 'production_record_selection' :
    (distinctNames.length > 1 ? 'byte_identical_copies' : 'only_named_candidate');
  chosen.selection_evidence = override ? (Array.isArray(override.evidence) ? override.evidence : [override.evidence]).filter(Boolean) : [];
  chosen.selection_note = override?.note || '';
  await copyChecked(path.join(input, chosen.source_path), destination, chosen.sha256);
  return { slot_id: slotId, image_path: destination, expected_image_path: destination, file_status: 'present',
    sha256: chosen.sha256, bytes: chosen.bytes, width: chosen.width, height: chosen.height,
    selected_source: chosen.source_path, selection_basis: chosen.selection_basis,
    selection_evidence: chosen.selection_evidence, selection_note: chosen.selection_note,
    pose_review_status: 'not_reaudited' };
}

for (const item of plans) {
  const clinical = parsedCards.get(item.id);
  const kind = item.id.startsWith('E-') ? 'assessment' : 'training';
  const category = categoryFor(Number(item.sequence));
  const actionDir = `${assets}/${kind}/${category}/${item.sequence}_${item.id}`;
  const overview = await selectImage(`${item.sequence}_${item.id}_overview`, overviews.get(item.id) || [], `${actionDir}/overview.png`);
  const actionSteps = [];
  for (const frame of item.frames) {
    const slotId = `${item.sequence}_${item.id}_s${pad(frame.step_number)}`;
    const image = await selectImage(slotId, slots.get(slotId) || [], `${actionDir}/steps/${slotId}.png`);
    const step = { sequence: item.sequence, action_id: item.id, action_name: item.name,
      kind, category, step_id: `s${pad(frame.step_number)}`, ...frame,
      ...grouping(item.sequence, frame.step_number), ...image };
    actionSteps.push(step); steps.push(step); images.push({ ...step, role: 'step' });
  }
  images.push({ sequence: item.sequence, action_id: item.id, action_name: item.name,
    kind, category, role: 'overview', step_number: 0, ...overview });
  const available = actionSteps.filter(s => s.file_status === 'present').length;
  const sourceCardPath = `${docs}/cards/${item.sequence}_${item.id}.md`;
  await save(sourceCardPath, `# ${item.sequence} ${item.id}｜${item.name}\n\n${clinical.source_content}\n`);
  actions.push({ sequence: item.sequence, action_id: item.id, action_name: item.name,
    kind, kind_label: kind === 'assessment' ? '评估' : '训练', category,
    category_label: categories[category], ...Object.fromEntries([...requiredFields, ...optionalFields].map(([key]) => [key, clinical[key]])),
    introduction: clinical.objective, source_content: clinical.source_content, source_refs: clinical.source_refs,
    source_card_path: sourceCardPath, image_version_camera: item.image_version_camera,
    image_type: item.image_type, sequence_reuse: item.sequence_reuse, extensions: item.extensions,
    image_plan_content: item.image_plan_content, expected_steps: item.expected, available_steps: available,
    missing_steps: actionSteps.filter(s => s.file_status !== 'present').map(s => s.step_id),
    overview, steps: actionSteps, steps_directory: `${actionDir}/steps`,
    file_status: available === item.expected && overview.file_status === 'present' ? 'complete' : 'incomplete',
    pose_review_status: 'not_reaudited', runtime_mapping_status: 'not_integrated' });
  if (Number(item.sequence) % 25 === 0) console.log(`Copied selected assets for ${item.sequence}/185 actions`);
}
check(unresolvedSelections.length === 0, `Selections need explicit review: ${unresolvedSelections.join(', ')}`);

for (const candidate of candidates) {
  if (candidate.selected) {
    candidate.packaged_path = images.find(i => i.selected_source === candidate.source_path)?.image_path || '';
  } else {
    candidate.archive_path = `${assets}/archive/${candidate.source_path}`;
    candidate.packaged_path = candidate.archive_path;
    candidate.selection_basis = 'archived_not_for_runtime';
    await copyChecked(path.join(input, candidate.source_path), candidate.archive_path, candidate.sha256);
  }
}
const sourcePaths = { action_document: `${docs}/sources/SOURCE_v1.0.md`, image_plan: `${docs}/sources/STEP_IMAGE_PLAN_v1.0.md` };
await copyChecked(sourceFile, sourcePaths.action_document, sha(sourceBuffer));
await copyChecked(planFile, sourcePaths.image_plan, sha(planBuffer));
for (const record of inputFiles.filter(f => /\.(json|md)$/i.test(f) && path.resolve(f) !== path.resolve(planFile))) {
  const destination = `${docs}/sources/production-records/${slash(path.relative(input, record))}`;
  await copyChecked(record, destination, sha(await fs.readFile(record)));
}
const referenceImages = [];
for (const reference of inputFiles.filter(f => /^step-image-references\/[^/]+\.png$/.test(slash(path.relative(input, f))))) {
  const info = pngInfo(await fs.readFile(reference), reference);
  const destination = `${assets}/references/${path.basename(reference)}`;
  await copyChecked(reference, destination, info.sha256);
  referenceImages.push({ image_path: destination, ...info });
}

const actionColumns = [
  ['sequence', '序号'], ['action_id', '动作ID'], ['action_name', '动作名称'],
  ['kind_label', '动作类型'], ['category_label', '部位分类'], ['introduction', '文字介绍'],
  ...requiredFields, ...optionalFields, ['image_type', '图片示范类型'],
  ['image_version_camera', '首轮图片版本与机位'], ['sequence_reuse', '图片顺序与复用'],
  ['extensions', '扩展图片版本'], ['expected_steps', '首轮应有步骤图数'],
  ['available_steps', '已选用步骤图数'], ['missing_steps', '缺失或待定图号'],
  ['overview_path', '单图路径'], ['step_paths', '步骤图片路径JSON'],
  ['steps_directory', '步骤图片目录'], ['source_card_path', '完整原文卡片路径'],
  ['source_refs', '原文引用编号JSON'], ['file_status', '文件状态'],
  ['pose_review_status', '姿势复核状态'], ['runtime_mapping_status', '接入状态'],
];
const stepColumns = [
  ['sequence', '动作序号'], ['action_id', '动作ID'], ['action_name', '动作名称'],
  ['kind', '动作类型'], ['category', '部位分类'], ['step_id', '图号'],
  ['slot_id', '图片槽位'], ['group_id', '独立图组ID'], ['group_label', '独立图组名称'],
  ['frame_description', '画面动作'], ['check_points', '核对要点'],
  ['image_path', '图片路径'], ['file_status', '文件状态'], ['sha256', '图片SHA256'],
  ['bytes', '字节数'], ['width', '宽度'], ['height', '高度'],
  ['selected_source', '选用原文件'], ['selection_basis', '选用依据'],
  ['selection_evidence', '选用证据JSON'], ['selection_note', '选用备注'],
  ['pose_review_status', '姿势复核状态'],
];
const imageColumns = [
  ['sequence', '动作序号'], ['action_id', '动作ID'], ['action_name', '动作名称'],
  ['kind', '动作类型'], ['category', '部位分类'], ['role', '图片类型'],
  ['step_number', '步骤数字'], ['slot_id', '图片槽位'], ['image_path', '图片路径'],
  ['expected_image_path', '预期图片路径'], ['file_status', '文件状态'],
  ['sha256', '图片SHA256'], ['bytes', '字节数'], ['width', '宽度'], ['height', '高度'],
  ['selected_source', '选用原文件'], ['selection_basis', '选用依据'],
  ['selection_evidence', '选用证据JSON'], ['selection_note', '选用备注'],
  ['pose_review_status', '姿势复核状态'],
];
const candidateColumns = [
  ['sequence', '动作序号'], ['action_id', '动作ID'], ['slot_id', '图片槽位'],
  ['source_path', '来源相对路径'], ['source_filename', '原文件名'],
  ['selected', '是否正式选用'], ['packaged_path', '归档后图片路径'],
  ['selection_basis', '选择状态'], ['selection_evidence', '选用证据JSON'],
  ['selection_note', '选用备注'], ['sha256', '图片SHA256'],
  ['bytes', '字节数'], ['width', '宽度'], ['height', '高度'],
];
const csvColumns = { actions: actionColumns, steps: stepColumns, image_manifest: imageColumns, image_candidates: candidateColumns };
const workbook = Workbook.create();
const sheetNames = { actions: '动作说明', steps: '步骤说明', image_manifest: '图片索引', image_candidates: '候选版本' };
const tables = { actions: actions.map(a => ({ ...a, overview_path: a.overview.image_path,
  step_paths: a.steps.map(s => s.image_path) })), steps, image_manifest: images, image_candidates: candidates };
function csvValue(value) {
  if (Array.isArray(value) || (value && typeof value === 'object')) return JSON.stringify(value);
  return value ?? '';
}
for (const [table, columns] of Object.entries(csvColumns)) {
  const sheet = workbook.worksheets.add(sheetNames[table]);
  const matrix = [columns.map(([, label]) => label), ...tables[table].map(row => columns.map(([key]) => csvValue(row[key])))];
  sheet.getRangeByIndexes(0, 0, matrix.length, columns.length).values = matrix;
  sheet.showGridLines = false;
  sheet.getRangeByIndexes(0, 0, matrix.length, columns.length).format.font.name = 'Microsoft YaHei';
  sheet.getRangeByIndexes(0, 0, matrix.length, columns.length).format.font.size = 10;
  sheet.getRangeByIndexes(0, 0, matrix.length, 1).setNumberFormat('@');
  sheet.getRangeByIndexes(0, 0, 1, columns.length).format.fill = '#25352F';
  sheet.getRangeByIndexes(0, 0, 1, columns.length).format.font.color = '#FFFFFF';
  sheet.getRangeByIndexes(0, 0, 1, columns.length).format.font.bold = true;
  sheet.getRangeByIndexes(0, 0, matrix.length, Math.min(6, columns.length)).format.columnWidth = 24;
  const previewWidths = table === 'image_candidates' ? [8, 18, 32, 65, 65] : [8, 18, 58, 18, 34];
  previewWidths.forEach((width, col) => {
    sheet.getRangeByIndexes(0, col, matrix.length, 1).format.columnWidth = width;
  });
  sheet.getRangeByIndexes(1, 0, 5, 5).format.wrapText = true;
  sheet.getRangeByIndexes(1, 0, 5, 5).format.rowHeight = 52;
  sheet.getRangeByIndexes(0, 0, 1, columns.length).format.rowHeight = 28;
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(2);
  // CSV has no formatting; serialize the authored values with RFC 4180 quoting and an Excel UTF-8 BOM.
  const values = sheet.getRangeByIndexes(0, 0, matrix.length, columns.length).values;
  const csv = values.map(row => row.map(v => `"${String(v ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n') + '\r\n';
  await save(`${docs}/${table}.csv`, '\uFEFF' + csv);
}
workbook.recalculate();
const inspect = await workbook.inspect({ kind: 'table', range: '动作说明!A1:F4',
  include: 'values', tableMaxRows: 4, tableMaxCols: 6, tableMaxCellChars: 45, maxChars: 1600 });
console.log(inspect.ndjson);
for (const name of Object.values(sheetNames)) {
  const preview = await workbook.render({ sheetName: name, range: 'A1:E6', scale: 1.5 });
  await fs.mkdir(path.join(runtime, 'previews'), { recursive: true });
  await fs.writeFile(path.join(runtime, 'previews', `${name}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const counts = { actions: actions.length, assessment: actions.filter(a => a.kind === 'assessment').length,
  training: actions.filter(a => a.kind === 'training').length, expected_steps: steps.length,
  selected_steps: steps.filter(s => s.file_status === 'present').length,
  missing_steps: steps.filter(s => s.file_status !== 'present').length,
  selected_overviews: images.filter(i => i.role === 'overview' && i.file_status === 'present').length,
  source_image_files: candidates.length, archived_candidates: candidates.filter(c => !c.selected).length,
  reference_images: referenceImages.length };
const catalogue = { schema_version: 1, package_version: version, generated_at: new Date().toISOString(),
  repository_relative_paths: true, asset_root: assets, docs_root: docs, counts, categories, csv_columns: csvColumns,
  sources: { action_document: { path: sourcePaths.action_document, sha256: sha(sourceBuffer) },
    image_plan: { path: sourcePaths.image_plan, sha256: sha(planBuffer) } },
  actions, images, candidates, reference_images: referenceImages };
await save(`${docs}/catalogue.json`, JSON.stringify(catalogue, null, 2) + '\n');
await save(`${docs}/summary.json`, JSON.stringify({ package_version: version, counts,
  missing: steps.filter(s => s.file_status !== 'present').map(s => ({ slot_id: s.slot_id, reason: s.file_status })),
  categories: Object.keys(categories).map(category => ({ category, label: categories[category],
    actions: actions.filter(a => a.category === category).length,
    steps: steps.filter(s => s.category === category).length })) }, null, 2) + '\n');
console.log(JSON.stringify({ package_version: version, counts }, null, 2));
