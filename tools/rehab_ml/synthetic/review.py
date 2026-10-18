"""Loopback-only, blinded human engineering review of original synthetic video.

Playback coverage and reviewer roles are declarations, not identity verification.
No model answer, requested scenario, or generation prompt reaches this page.
Every save is an immutable version; generation manifests are never overwritten.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import secrets
from threading import Lock
from urllib.parse import urlsplit
import uuid

from . import contracts as c

VERSION = 'rehab_synthetic_review/v1'
MAX_REQUEST = 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _within(root, reference):
    path = Path(reference)
    path = path.resolve() if path.is_absolute() else (root/'manifests'/path).resolve()
    if not path.is_relative_to(root):
        raise ValueError('file_outside_declared_dataset_root')
    return path


def _directory(root, relative):
    path = root/relative
    if not path.resolve().is_relative_to(root):
        raise ValueError('review_output_outside_dataset_root')
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _json(path):
    return c._read_json(path)


def _dataset(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('existing_dataset_root_required')
    path = root/'manifests/dataset.json'
    if not path.resolve().is_relative_to(root):
        raise ValueError('manifest_outside_dataset_root')
    # Validate one manifest snapshot; do not reread it between an allowlist check
    # and opening a media path (the generator may append a new candidate).
    manifest = c.load_manifest(path, verify_files=False)
    timelines = {}
    from .video import probe_video
    for row in manifest['samples']:
        video = row['video']
        source, index = _within(root, video['path']), _within(root, video['timeline_path'])
        if _hash(source) != video['sha256'] or _hash(index) != video['timeline_sha256']:
            raise ValueError('dataset_source_or_timeline_hash_changed')
        saved = _json(index)
        c.validate_timeline(saved, row)
        decoded = probe_video(source)
        if any(saved[key] != decoded[key] for key in
               ('video_sha256', 'frame_count', 'width', 'height', 'time_basis', 'presentation_s')):
            raise ValueError('actual_decoded_pts_disagree_with_saved_index')
        if 'frames' in saved and saved['frames'] != decoded['frames']:
            raise ValueError('actual_frame_fingerprints_disagree_with_saved_index')
        timelines[row['sample_id']] = saved
    c.validate_manifest(manifest, timelines)
    return root, manifest, timelines


def prepare(root):
    """Return empty, unreviewed forms. This does not create human references."""
    _, manifest, timelines = _dataset(root)
    return [c.prepare_review(row, timelines[row['sample_id']]) for row in manifest['samples']]


def _version_directory(root, sample_id):
    # Neither reviewer identity nor arbitrary client paths enter output names.
    key = hashlib.sha256(sample_id.encode('utf-8')).hexdigest()
    return _directory(root, 'annotations/review-versions/'+key)


def _latest(root, manifest):
    result = {}
    for sample in manifest['samples']:
        directory = root/'annotations/review-versions'/hashlib.sha256(sample['sample_id'].encode()).hexdigest()
        if not directory.exists():
            continue
        if not directory.resolve().is_relative_to(root):
            raise ValueError('review_history_outside_dataset_root')
        files = sorted(directory.glob('*.json'))
        if not files:
            continue
        if not files[-1].resolve().is_relative_to(root):
            raise ValueError('review_history_file_outside_dataset_root')
        record = _json(files[-1])
        if (record.get('schema_version') != VERSION or record.get('sample_id') != sample['sample_id']
                or record.get('source_video_sha256') != sample['video']['sha256']
                or record.get('source_timeline_sha256') != sample['video']['timeline_sha256']
                or c.canonical_hash(record.get('annotation')) != record.get('annotation_sha256')):
            raise ValueError('review_history_source_or_annotation_changed')
        result[sample['sample_id']] = record
    return result


def load_reviewed(root):
    """Apply explicitly saved review decisions in memory; retain full cohort."""
    root, manifest, timelines = _dataset(root)
    latest = _latest(root, manifest)
    annotations = []
    for sample in manifest['samples']:
        record = latest.get(sample['sample_id'])
        if record is not None:
            patch = record.get('source_patch', {})
            if set(patch)-{'status', 'acceptance', 'exclusion_reason'}:
                raise ValueError('review_history_may_only_change_review_status')
            sample.update(copy.deepcopy(patch))
            row = record['annotation']
            c.validate_annotation(row, sample, timelines[sample['sample_id']])
            annotations.append(copy.deepcopy(row))
    c.validate_manifest(manifest, timelines)
    return dict(manifest=manifest, timelines=timelines, annotations=annotations,
                eligible_annotations=c.load_eligible_annotations(annotations, manifest, timelines))


class ReviewStore:
    def __init__(self, root):
        self.root, self.manifest, self.timelines = _dataset(root)
        self.by_id = {row['sample_id']: row for row in self.manifest['samples']}
        self.tokens = {secrets.token_urlsafe(24): key for key in self.by_id}
        self.csrf = secrets.token_urlsafe(32)
        self.lock = Lock()

    def _refresh_unlocked(self):
        """Allow append-only candidates while retaining every old review token."""
        _, manifest, timelines = _dataset(self.root)
        incoming = {row['sample_id']: row for row in manifest['samples']}
        if (manifest['dataset_id'] != self.manifest['dataset_id']
                or manifest['schema_version'] != self.manifest['schema_version']):
            raise ValueError('existing_review_dataset_identity_changed')
        for key, previous in self.by_id.items():
            if key not in incoming:
                raise ValueError('existing_review_source_disappeared')
            if incoming[key] != previous:
                raise ValueError('existing_review_source_row_changed')
        if self.manifest.get('split_freeze') is not None and manifest.get('split_freeze') != self.manifest['split_freeze']:
            raise ValueError('existing_review_split_freeze_changed')
        known = set(self.by_id)
        added = [row['sample_id'] for row in manifest['samples'] if row['sample_id'] not in known]
        # Publish only after the entire new snapshot has passed full raw/PTS
        # verification. Failed refreshes leave old tokens and snapshots intact.
        self.manifest, self.by_id, self.timelines = manifest, incoming, timelines
        for key in added:
            self.tokens[secrets.token_urlsafe(24)] = key
        return len(added)

    def refresh(self):
        with self.lock:
            return self._refresh_unlocked()

    def catalog(self):
        with self.lock:
            self._refresh_unlocked()
            latest = _latest(self.root, self.manifest)
            result = []
            for index, (token, key) in enumerate(self.tokens.items(), 1):
                source = self.by_id[key]
                form = c.prepare_review(source, self.timelines[key])
                # Only a fresh blank form is shown. Prior labels are not prediction
                # answers for a different reviewer and are never silently prefilled.
                form['sample_id'] = token
                result.append(dict(token=token, label='片段 '+str(index), form=form,
                    width=source['video']['width'], height=source['video']['height'],
                    frame_count=source['video']['frame_count'],
                    presentation_s=self.timelines[key]['presentation_s'],
                    saved_versions=bool(key in latest)))
            return dict(schema_version=VERSION, samples=result)

    def media(self, token):
        if token not in self.tokens:
            raise ValueError('unknown_opaque_sample_token')
        row = self.by_id[self.tokens[token]]
        path = _within(self.root, row['video']['path'])
        if _hash(path) != row['video']['sha256']:
            raise ValueError('source_changed_since_review_started')
        return path

    def submit(self, payload):
        if not isinstance(payload, dict) or set(payload)-{'token', 'decision', 'reason', 'annotation', 'playback_coverage'}:
            raise ValueError('explicit_review_fields_only')
        token = payload.get('token')
        if token not in self.tokens:
            raise ValueError('unknown_opaque_sample_token')
        # An old unsaved page keeps its token, but may not approve a source whose
        # immutable manifest row was changed while it was being watched.
        self.refresh()
        key = self.tokens[token]
        source = copy.deepcopy(self.by_id[key])
        # Recheck immutable source/index hashes before binding a human assertion.
        self.media(token)
        if _hash(_within(self.root, source['video']['timeline_path'])) != source['video']['timeline_sha256']:
            raise ValueError('source_timeline_changed_since_review_started')
        annotation = copy.deepcopy(payload.get('annotation'))
        if not isinstance(annotation, dict) or annotation.get('sample_id') != token:
            raise ValueError('annotation_token_must_match_current_sample')
        annotation['sample_id'] = key
        decision = payload.get('decision')
        if decision not in ('pending', 'accepted', 'excluded'):
            raise ValueError('explicit_review_decision_required')
        reason = payload.get('reason', '')
        if not isinstance(reason, str) or len(reason) > 4096:
            raise ValueError('bounded_review_note_required')
        annotation['operator_note'] = reason.strip()
        watched = annotation.get('review', {}).get('full_video_watched')
        if type(watched) is not bool:
            raise ValueError('explicit_full_video_watched_required')
        now = _now()
        annotation['review'] = dict(full_video_watched=watched,
            reviewed_video_sha256=source['video']['sha256'] if watched else None,
            reviewed_frame_count=source['video']['frame_count'] if watched else None,
            watched_at=now if watched else None)
        patch = dict(status=decision)
        if decision == 'accepted':
            if annotation.get('reviewer_role') != 'human_operator' or not watched:
                raise ValueError('acceptance_requires_explicit_human_full_video_review')
            patch['acceptance'] = dict(reviewer_id=annotation.get('reviewer_id'), reviewer_role='human_operator',
                                       **annotation['review'])
        if decision == 'excluded':
            if not reason.strip():
                raise ValueError('exclusion_reason_required')
            patch['exclusion_reason'] = reason.strip()
        source.update(patch)
        audit = c.validate_annotation(annotation, source, self.timelines[key])
        coverage = payload.get('playback_coverage', [])
        last = self.timelines[key]['presentation_s'][-1]
        if not isinstance(coverage, list) or len(coverage) > 20000:
            raise ValueError('bounded_playback_coverage_required')
        for interval in coverage:
            if (not isinstance(interval, list) or len(interval) != 2
                    or any(type(t) not in (int, float) or not math.isfinite(t) for t in interval)
                    or not 0 <= interval[0] <= interval[1] <= last+.001):
                raise ValueError('playback_coverage_outside_original_pts')
        version = now.replace(':', '').replace('+', '_')+'-'+uuid.uuid4().hex
        record = dict(schema_version=VERSION, version=version, saved_at=now, sample_id=key,
            source_video_sha256=source['video']['sha256'],
            source_timeline_sha256=source['video']['timeline_sha256'], source_patch=patch,
            annotation=annotation, annotation_sha256=c.canonical_hash(annotation),
            playback_coverage=coverage, playback_coverage_is_identity_proof=False,
            reviewer_identity_is_verified=False, **audit)
        with self.lock:
            target = _version_directory(self.root, key)/(version+'.json')
            with target.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(record, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.write('\n')
        return dict(version=version, **audit)


HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>康复原片审核</title><style nonce="__NONCE__">
:root{color-scheme:light;--ink:#182c43;--blue:#23638d;--paper:#eef3f7;--line:#c8d5df;--warn:#8b5b00}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 'Microsoft YaHei UI','Microsoft YaHei',sans-serif}header{padding:20px 30px;border-bottom:1px solid var(--line);background:#fff;display:flex;align-items:baseline;gap:24px}h1{font-size:24px;margin:0;font-weight:650}header p{margin:0;color:#516a80}main{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,1fr);gap:24px;padding:24px 30px;max-width:1640px;margin:auto}section{min-width:0}video{width:100%;max-height:62vh;object-fit:contain;aspect-ratio:5 / 3;background:#111;display:block;border-radius:8px}label{display:block;margin:12px 0 5px}button,input,select,textarea{font:inherit}button{border:1px solid var(--line);border-radius:5px;background:#fff;color:var(--ink);padding:8px 13px;cursor:pointer}button:hover{border-color:var(--blue)}button.primary{background:var(--blue);color:#fff;border-color:var(--blue)}:focus-visible{outline:3px solid #e5a92d;outline-offset:2px}input,select,textarea{padding:8px;border:1px solid #aabcc9;border-radius:4px;background:#fff;color:var(--ink);max-width:100%}input[type=number]{width:100px}input[type=checkbox]{margin-right:8px;width:18px;height:18px;vertical-align:middle}textarea{width:100%;min-height:72px}h2{font-size:18px;margin:0 0 14px}h3{font-size:16px;margin:22px 0 8px}.work{padding:22px;background:#fff;border-radius:10px}.row{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin:12px 0}.help{color:#526c80;font-size:13px;max-width:74ch}.warning{color:var(--warn)}table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}th,td{text-align:left;padding:7px 4px;border-bottom:1px solid var(--line)}td button{font-size:12px;padding:4px 7px}td input{width:100%;min-width:70px;padding:4px}output{font-variant-numeric:tabular-nums}#message{white-space:pre-wrap;min-height:3em;padding:12px 0}.check{display:flex;align-items:flex-start;gap:6px}.check input{flex:none}details{margin:16px 0}summary{cursor:pointer}#repList{font-size:13px}.quiet{color:#526c80}footer{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}.rail{margin-bottom:14px}.ptslider{width:100%}@media(max-width:950px){main{grid-template-columns:1fr;padding:16px}header{padding:16px;display:block}video{max-height:55vh}.work{padding:16px}}
</style><header><h1>康复原片审核</h1><p>先完整观看，再记录画面中能确认的事实。</p></header><main><section><div class="row rail"><label for="sample">待审核原片</label><select id="sample"></select><button id="reload">刷新片单</button></div><video id="video" controls preload="metadata"></video><div class="row"><button id="prev">上一帧</button><button id="next">下一帧</button><output id="position">尚未选择原片</output></div><input class="ptslider" id="frame" aria-label="按原片实际PTS定位帧" type="range" min="0" max="0" value="0"><p class="help">单帧定位使用原片实际呈现时间。播放记录只用于辅助审阅，不能证明操作者身份或代替完整观看。</p><h3>可确认的阶段区间</h3><div class="row"><select id="phase"><option value="ready">准备</option><option value="outbound">出程</option><option value="endpoint_or_hold">端点／保持</option><option value="return">回程</option><option value="rest_or_other">休息／无关活动</option></select><button id="markStart">记下起点</button><output id="start">起点未记</output><button id="markEnd">以当前帧为终点添加</button></div><table><thead><tr><th>阶段</th><th>起点（秒）</th><th>终点（秒）</th><th></th></tr></thead><tbody id="intervals"></tbody></table><p class="help">不确定的时间留空，不用“休息”填补未知区间。区间不得重叠。</p><details><summary>记录一次动作的五个边界</summary><div class="row"><button id="addRep">添加一次动作记录</button></div><div id="repList"></div><p class="help">每个边界独立确认。肩外展完整一次需要明确出程、端点、回程与回位证据；未知完成状态不计为0次。</p></details></section><section class="work"><h2>这条原片的人工记录</h2><p class="help">本页不显示生成要求、模型骨骼或预测答案。只标可观察事件，专业质量保持未标注。</p><label for="reviewer">操作者标识</label><input id="reviewer" autocomplete="off" placeholder="由实际操作者填写"><label for="role">记录来源</label><select id="role"><option value="">请选择</option><option value="human_operator">本人观看后填写（人工）</option><option value="ai_draft">AI草稿（不得训练）</option></select><label for="side">画面中实际测试侧</label><select id="side"><option value="">未知／未确认</option><option value="left">解剖左侧</option><option value="right">解剖右侧</option><option value="bilateral">双侧</option></select><label for="count">可确认的完整动作次数</label><input id="count" type="number" min="0" step="1" placeholder="留空"><label class="check"><input id="countKnown" type="checkbox"><span>我已清点全部动作，以上次数可确认</span></label><p class="help">空白不是0次。填写大于0的次数时，请展开左侧“一次动作”记录相应边界与完成状态。</p><label class="check"><input id="watched" type="checkbox"><span>我是实际操作者，已完整观看本条原片；此声明仅记录本人陈述。</span></label><label for="decision">原片筛查结果</label><select id="decision"><option value="pending">仍待审核／保存草稿</option><option value="accepted">原片通过人工筛查</option><option value="excluded">排除原片</option></select><label for="reason">排除原因或复核备注</label><textarea id="reason" placeholder="排除时必须说明原因"></textarea><footer><button class="primary" id="save">保存新的审核版本</button><p class="help">每次保存另建版本，保留原片、旧记录与未知标签。通过筛查不等于临床有效。</p><div id="message" role="status" aria-live="polite"></div></footer></section></main><script nonce="__NONCE__">
const csrf='__CSRF__', $=id=>document.getElementById(id), phaseNames={ready:'准备',outbound:'出程',endpoint_or_hold:'端点／保持',return:'回程',rest_or_other:'休息／无关'};
let entries=[],item=null,form=null,start=null,coverage=[],lastTime=null;
const phases=Object.keys(phaseNames), vid=$('video');
const errors={count_must_match_explicit_observable_completions:'次数需要与每次动作记录中明确完成的数量一致。',unknown_completion_inventory_cannot_set_count:'仍有动作的完成状态未知，暂时不能确认总次数。',complete_shoulder_roundtrip_requires_all_boundaries:'完整肩外展需要确认五个动作边界；不确定时保留完成状态未知。',phase_intervals_must_be_ordered_nonoverlapping:'阶段区间重叠或顺序有误，请核对原片。',observable_count_known_value_required:'请填写可确认的非负整数次数，或取消次数已确认。',acceptance_requires_explicit_human_full_video_review:'通过筛查需要实际人工填写，并声明已完整观看。',clinical_quality_requires_independent_qualified_review:'专业质量尚无独立资格审核，请保留未标注。',exclusion_reason_required:'请填写排除原片的原因。'};
async function api(url,body){const r=await fetch(url,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(errors[data.error]||'记录尚未保存，请核对所填侧别、次数、阶段边界与观看声明。');return data}
function msg(s){$('message').textContent=s}
function nearest(t){let best=0;for(let i=1;i<item.presentation_s.length;i++)if(Math.abs(item.presentation_s[i]-t)<Math.abs(item.presentation_s[best]-t))best=i;return best}
function stamp(){return item.presentation_s[nearest(vid.currentTime)]}
function locate(i){i=Math.min(item.presentation_s.length-1,Math.max(0,i));vid.pause();lastTime=null;vid.currentTime=item.presentation_s[i];$('frame').value=i;$('position').textContent=`第 ${i+1} / ${item.frame_count} 帧，PTS ${item.presentation_s[i].toFixed(6)} 秒`}
function draw(){const tbody=$('intervals');tbody.replaceChildren();form.phase_intervals.forEach((r,i)=>{let tr=document.createElement('tr');for(const text of [phaseNames[r.phase],r.start_s.toFixed(6),r.end_s.toFixed(6)]){let td=document.createElement('td');td.textContent=text;tr.append(td)}let td=document.createElement('td'),b=document.createElement('button');b.textContent='删除';b.onclick=()=>{form.phase_intervals.splice(i,1);draw()};td.append(b);tr.append(td);tbody.append(tr)});const list=$('repList');list.replaceChildren();form.repetitions.forEach((rep,i)=>{let box=document.createElement('div'),h=document.createElement('h3');h.textContent=`动作记录 ${i+1}`;box.append(h);phases.forEach(p=>{let row=document.createElement('div');row.className='row';let label=document.createElement('label');label.textContent=phaseNames[p];let output=document.createElement('output');output.textContent=rep.boundary_masks[p]?rep.boundaries[p].toFixed(6)+' 秒':'未知';let mark=document.createElement('button');mark.textContent='记当前帧';mark.onclick=()=>{rep.boundaries[p]=stamp();rep.boundary_masks[p]=true;draw()};let clear=document.createElement('button');clear.textContent='清空';clear.onclick=()=>{rep.boundaries[p]=null;rep.boundary_masks[p]=false;draw()};row.append(label,output,mark,clear);box.append(row)});let sel=document.createElement('select');for(const [value,text] of [['','完成状态未知'],['yes','可确认完整完成'],['no','可确认部分动作']]){let o=document.createElement('option');o.value=value;o.textContent=text;sel.append(o)}sel.value=rep.observable_completion_mask?(rep.observable_completion?'yes':'no'):'';sel.onchange=()=>{rep.observable_completion_mask=!!sel.value;rep.observable_completion=sel.value?sel.value==='yes':null};let del=document.createElement('button');del.textContent='删除动作记录';del.onclick=()=>{form.repetitions.splice(i,1);draw()};box.append(sel,del);list.append(box)})}
function choose(){item=entries[Number($('sample').value)];if(!item)return;form=structuredClone(item.form);start=null;coverage=[];lastTime=null;vid.src='/media/'+item.token;vid.style.aspectRatio=item.width+' / '+item.height;$('frame').max=item.frame_count-1;$('frame').value=0;for(const id of ['reviewer','side','count','reason','role'])$(id).value='';for(const id of ['countKnown','watched'])$(id).checked=false;$('decision').value='pending';$('start').textContent='起点未记';msg(item.saved_versions?'这条原片已有保存版本。本次仍从空白独立记录开始。':'尚未保存人工参考。');draw();locate(0)}
async function reload(){try{const data=await api('/api/samples');entries=data.samples;$('sample').replaceChildren();entries.forEach((x,i)=>{let o=document.createElement('option');o.value=i;o.textContent=x.label;$('sample').append(o)});if(entries.length)choose();else msg('尚无可审核原片。生成完成并建立实际PTS索引后刷新片单。')}catch(e){msg(e.message)}}
$('sample').onchange=choose;$('reload').onclick=()=>location.reload();$('prev').onclick=()=>item&&locate(nearest(vid.currentTime)-1);$('next').onclick=()=>item&&locate(nearest(vid.currentTime)+1);$('frame').oninput=()=>item&&locate(Number($('frame').value));
vid.ontimeupdate=()=>{if(!item)return;let t=Math.min(item.presentation_s.at(-1),vid.currentTime);$('frame').value=nearest(t);$('position').textContent=`第 ${nearest(t)+1} / ${item.frame_count} 帧，PTS ${stamp().toFixed(6)} 秒`;if(!vid.paused&&lastTime!==null&&t>lastTime&&t-lastTime<1.5){let prev=coverage.at(-1);if(prev&&Math.abs(prev[1]-lastTime)<.03)prev[1]=t;else coverage.push([lastTime,t])}lastTime=t};vid.onseeking=()=>lastTime=null;vid.onpause=()=>lastTime=null;
$('markStart').onclick=()=>{if(!item)return;start=stamp();$('start').textContent=start.toFixed(6)+' 秒'};$('markEnd').onclick=()=>{if(!item||start===null){msg('先记录起点。');return}let end=stamp();if(end<=start){msg('终点需要晚于起点。');return}form.phase_intervals.push({phase:$('phase').value,start_s:start,end_s:end,label_mask:true});form.phase_intervals.sort((a,b)=>a.start_s-b.start_s);start=null;$('start').textContent='起点未记';draw()};
$('addRep').onclick=()=>{if(!form)return;form.repetitions.push({rep_id:crypto.randomUUID(),boundaries:Object.fromEntries(phases.map(p=>[p,null])),boundary_masks:Object.fromEntries(phases.map(p=>[p,false])),observable_completion:null,observable_completion_mask:false});draw()};
$('save').onclick=async()=>{if(!item)return;try{if(!$('role').value)throw Error('请选择实际记录来源。');if(!$('reviewer').value.trim())throw Error('请填写实际操作者标识。');form.reviewer_id=$('reviewer').value.trim();form.reviewer_role=$('role').value;form.side_mask=!!$('side').value;form.side=$('side').value||null;form.observable_count_mask=$('countKnown').checked;form.observable_count=form.observable_count_mask&&$('count').value!==''?Number($('count').value):null;form.review.full_video_watched=$('watched').checked;const result=await api('/api/submit',{token:item.token,annotation:form,decision:$('decision').value,reason:$('reason').value,playback_coverage:coverage});msg('已保存新版本。\n'+(result.eligible_for_training?'工程时序参考具备训练资格。':'当前不进入训练：'+result.reasons.join('、')))}catch(e){msg(e.message)}};reload();
</script></html>'''


def make_server(root, port=8190):
    """Create a loopback server; callers own its lifetime and shutdown."""
    store = ReviewStore(root)

    class Handler(BaseHTTPRequestHandler):
        server_version = 'LocalRehabReview'

        def setup(self):
            super().setup()
            self.connection.settimeout(5.)

        def log_message(self, *_):
            pass

        def _origin(self, mutation=False):
            expected = '127.0.0.1:'+str(self.server.server_port)
            if self.headers.get('Host') != expected:
                return False
            origin = self.headers.get('Origin')
            if origin is not None and origin != 'http://'+expected:
                return False
            if mutation and (origin != 'http://'+expected or not secrets.compare_digest(
                    self.headers.get('X-CSRF-Token', '').encode('utf-8'), store.csrf.encode('utf-8'))):
                return False
            return True

        def _headers(self, status, content_type, size, **extra):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(size))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'nonce-"+store.csrf+
                "'; style-src 'nonce-"+store.csrf+"'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            for key, value in extra.items():
                self.send_header(key, str(value))
            self.end_headers()

        def _respond(self, status, value):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self._headers(status, 'application/json; charset=utf-8', len(body))
            self.wfile.write(body)

        def _error(self, exc):
            # Filesystem/JSON diagnostics may contain blinded source filenames.
            # Keep those details out of browser responses and media failures.
            message = str(exc)
            safe = message if re.fullmatch(r'[a-z][a-z0-9_]{0,160}', message) else 'review_record_invalid_refresh_required'
            return self._respond(400, dict(error=safe))

        def _reject_post(self, status, error):
            # On Windows closing a socket with an unread ordinary POST body can
            # reset it before the client receives its explicit rejection.
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if 0 < size <= MAX_REQUEST:
                    self.rfile.read(size)
            except (ValueError, OSError):
                pass
            return self._respond(status, dict(error=error))

        def do_GET(self):
            if not self._origin():
                return self._respond(403, dict(error='loopback_host_and_origin_required'))
            path = urlsplit(self.path)
            if path.query or path.fragment:
                return self._respond(404, dict(error='not_found'))
            try:
                if path.path == '/':
                    body = HTML.replace('__NONCE__', store.csrf).replace('__CSRF__', store.csrf).encode('utf-8')
                    self._headers(200, 'text/html; charset=utf-8', len(body))
                    return self.wfile.write(body)
                if path.path == '/api/samples':
                    return self._respond(200, store.catalog())
                match = re.fullmatch(r'/media/([A-Za-z0-9_-]{20,80})', path.path)
                if match:
                    source = store.media(match.group(1))
                    length = source.stat().st_size
                    start, end, status = 0, length-1, 200
                    requested = self.headers.get('Range')
                    if requested is not None:
                        span = re.fullmatch(r'bytes=(\d+)-(\d*)', requested)
                        if not span:
                            return self._respond(416, dict(error='single_bounded_byte_range_required'))
                        start = int(span.group(1)); end = int(span.group(2)) if span.group(2) else end
                        if not 0 <= start <= end < length:
                            return self._respond(416, dict(error='byte_range_out_of_bounds'))
                        status = 206
                    headers = {'Accept-Ranges': 'bytes'}
                    if status == 206:
                        headers['Content-Range'] = f'bytes {start}-{end}/{length}'
                    self._headers(status, 'video/mp4', end-start+1, **headers)
                    with source.open('rb') as stream:
                        stream.seek(start)
                        remaining = end-start+1
                        while remaining:
                            chunk = stream.read(min(256*1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk); remaining -= len(chunk)
                    return
                self._respond(404, dict(error='not_found'))
            except (ValueError, OSError, KeyError) as exc:
                self._error(exc)

        def do_POST(self):
            if not self._origin(mutation=True):
                return self._reject_post(403, 'loopback_origin_and_csrf_token_required')
            if self.path != '/api/submit':
                return self._reject_post(404, 'not_found')
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                return self._reject_post(415, 'json_request_required')
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_REQUEST:
                    return self._respond(413, dict(error='bounded_request_body_required'))
                def pairs(items):
                    result = {}
                    for key, value in items:
                        if key in result:
                            raise ValueError('duplicate_json_key')
                        result[key] = value
                    return result
                value = json.loads(self.rfile.read(size), object_pairs_hook=pairs,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
                return self._respond(201, store.submit(value))
            except (ValueError, OSError, KeyError, TypeError) as exc:
                self._error(exc)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.review_store = store
    return server


def serve(root, port=8190):
    """Run the local review page until interrupted; no external bind is offered."""
    server = make_server(root, port)
    print('http://127.0.0.1:'+str(server.server_port)+'/', flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local original-video engineering review')
    parser.add_argument('root', type=Path)
    parser.add_argument('--port', type=int, default=8190)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args(argv)
    if args.prepare:
        print(json.dumps(prepare(args.root), ensure_ascii=False, indent=2))
    else:
        serve(args.root, args.port)


if __name__ == '__main__':
    main()
