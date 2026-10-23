#!/usr/bin/env python3
"""Portable, dependency-free canonical task views. Python 3.9+."""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

TASK_SCHEMA = 'axioms-task/v1'
FRONTIER_SCHEMA = 'axioms-frontier/v1'
STATUSES = ('planned', 'in-progress', 'blocked', 'done', 'cancelled')
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
REPOSITORY = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
MAX_FILE = 4 * 1024 * 1024
PAGE_SIZE = 100


def reference(value):
    if not isinstance(value, str):
        return False
    parts = value.split('#')
    return bool((len(parts) == 1 and ID.fullmatch(value)) or
                (len(parts) == 2 and REPOSITORY.fullmatch(parts[0]) and ID.fullmatch(parts[1])))


def read_json(path):
    # Symlinked task directories/files must never turn discovery into a file browser.
    if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
        raise ValueError('symlinked work inputs are not supported')
    if path.stat().st_size > MAX_FILE:
        raise ValueError('input exceeds 4 MiB limit')
    data = path.read_bytes()
    return json.loads(data), data


def task_errors(task):
    if not isinstance(task, dict):
        return ['task must be an object']
    errors = []
    if task.get('schema') != TASK_SCHEMA:
        errors.append('schema must be ' + TASK_SCHEMA)
    if not isinstance(task.get('id'), str) or not ID.fullmatch(task['id']):
        errors.append('invalid id')
    for field in ('title', 'outcome'):
        if not isinstance(task.get(field), str) or not task[field].strip():
            errors.append(field + ' must be a nonempty string')
    if task.get('status') not in STATUSES:
        errors.append('invalid status')
    for field in ('depends', 'acceptance', 'evidence'):
        if not isinstance(task.get(field), list):
            errors.append(field + ' must be an array')
    for field in ('acceptance', 'evidence'):
        if isinstance(task.get(field), list) and not all(isinstance(x, str) for x in task[field]):
            errors.append(field + ' must contain strings')
    if isinstance(task.get('depends'), list) and not all(reference(x) for x in task['depends']):
        errors.append('depends contains invalid task reference')
    current = task.get('current')
    if not isinstance(current, dict):
        errors.append('current must be an object')
    else:
        for field in ('summary', 'nextAction'):
            if not isinstance(current.get(field), str):
                errors.append('current.' + field + ' must be a string')
        if not isinstance(current.get('blockers'), list) or not all(isinstance(x, (str, dict)) for x in current.get('blockers', [])):
            errors.append('current.blockers must be an array of strings or objects')
    for field in ('completedAt', 'updatedAt'):
        if field in task and not valid_date(task[field]):
            errors.append(field + ' must be an ISO 8601 timestamp or date')
    return errors


def valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
        return True
    except ValueError:
        return False


def frontier_references(frontier):
    """Parallel is an explicit list of local/cross-repository task references."""
    return [(lane, ref) for lane in ('product', 'maintenance', 'parallel')
            for ref in (frontier.get(lane) if isinstance(frontier.get(lane), list) else []) if isinstance(ref, str) and reference(ref)]


def load_repository(root):
    root = Path(root).resolve()
    result = {'root': root, 'frontier': {}, 'tasks': {}, 'errors': [], 'warnings': [], 'sources': []}
    def error(message):
        result['errors'].append(message)
    try:
        frontier, raw = read_json(root / 'work/frontier.json')
        if not isinstance(frontier, dict):
            raise ValueError('frontier must be an object')
        result['frontier'] = frontier
        result['sources'].append(('work/frontier.json', raw))
        if frontier.get('schema') != FRONTIER_SCHEMA:
            error('frontier schema must be ' + FRONTIER_SCHEMA)
        if not isinstance(frontier.get('repository'), str) or not REPOSITORY.fullmatch(frontier['repository']):
            error('frontier repository must be owner/name')
        if not isinstance(frontier.get('objective'), str) or not frontier['objective'].strip():
            error('frontier objective must be a nonempty string')
        if frontier.get('mode') not in ('product', 'maintenance'):
            error('frontier mode must be product or maintenance')
        if frontier.get('lifecycle', 'active') not in ('active', 'retired'):
            error('frontier lifecycle must be active or retired')
        for lane in ('product', 'maintenance', 'parallel'):
            refs = frontier.get(lane)
            if not isinstance(refs, list) or not all(reference(ref) for ref in refs):
                error('frontier ' + lane + ' must be an array of task references')
            elif len(refs) != len(set(refs)):
                error('frontier ' + lane + ' has duplicate references')
    except (OSError, ValueError) as exc:
        error('work/frontier.json: ' + str(exc))
    directory = root / 'work/tasks'
    if directory.is_symlink():
        error('work/tasks must not be a symlink')
        return result
    for path in sorted(directory.glob('*.json')):
        try:
            task, raw = read_json(path)
            result['sources'].append(('work/tasks/' + path.name, raw))
            errors = task_errors(task)
            for message in errors:
                error(path.name + ': ' + message)
            if errors:
                continue
            if task['id'] in result['tasks']:
                error('duplicate task id ' + task['id'])
                continue
            if path.stem != task['id']:
                error(path.name + ': filename must match task id')
            result['tasks'][task['id']] = {'record': task, 'sourceUpdatedAt': datetime.fromtimestamp(
                path.stat().st_mtime).astimezone().isoformat()}
        except (OSError, ValueError) as exc:
            error(path.name + ': ' + str(exc))
    for task_id, entry in result['tasks'].items():
        for ref in entry['record']['depends']:
            if '#' not in ref and ref not in result['tasks']:
                error(task_id + ': unresolved local dependency ' + ref)
    for lane, ref in frontier_references(result['frontier']):
        if '#' not in ref and ref not in result['tasks']:
            error('frontier ' + lane + ': unresolved local task ' + ref)
    return result


def discover(workspace, explicit=()):
    roots = []
    if workspace:
        for path in sorted(Path(workspace).iterdir()):
            if (not path.name.startswith('.') and path.is_dir() and not path.is_symlink()
                    and (path / '.git').exists() and (path / 'work/frontier.json').is_file()):
                roots.append(path.resolve())
    for path in explicit:
        resolved = Path(path).resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots


def qualify(repository, ref):
    return ref if '#' in ref else repository + '#' + ref


def active_blockers(blockers):
    """Strings and unresolved/unknown dispositions stay active conservatively."""
    return [blocker for blocker in blockers
            if isinstance(blocker, str) or blocker.get('disposition') not in ('resolved', 'superseded')]


def snapshot(roots):
    repositories = [load_repository(root) for root in roots]
    index = {}
    for repo in repositories:
        name = repo['frontier'].get('repository')
        if not isinstance(name, str) or not REPOSITORY.fullmatch(name):
            name = 'invalid/' + hashlib.sha256(str(repo['root']).encode()).hexdigest()[:12]
        repo['name'] = name
        if name in index:
            repo['errors'].append('duplicate repository identity ' + name)
            index[name]['errors'].append('duplicate repository identity ' + name)
        index[name] = repo
    def dependency_state(repo, ref, trail):
        key = qualify(repo['name'], ref)
        if key in trail:
            return {'reference': ref, 'state': 'cycle'}
        if len(trail) > 100:
            return {'reference': ref, 'state': 'depth-limit'}
        name, task_id = key.split('#', 1)
        target = index.get(name)
        if target is None:
            return {'reference': ref, 'state': 'unavailable'}
        entry = target['tasks'].get(task_id)
        if entry is None:
            return {'reference': ref, 'state': 'missing'}
        task = entry['record']
        if task['status'] != 'done':
            return {'reference': ref, 'state': 'open', 'status': task['status']}
        # A done label does not conceal an open transitive prerequisite.
        children = [dependency_state(target, dep, trail | {key}) for dep in task['depends']]
        return {'reference': ref, 'state': 'satisfied' if all(x['state'] == 'satisfied' for x in children) else 'prerequisites-open'}
    for repo in repositories:
        for lane, ref in frontier_references(repo['frontier']):
            if '#' in ref:
                name, task_id = ref.split('#', 1)
                if name not in index:
                    repo['warnings'].append('frontier ' + lane + ': repository unavailable for ' + ref)
                elif task_id not in index[name]['tasks']:
                    repo['errors'].append('frontier ' + lane + ': unresolved task ' + ref)
    queued = {qualify(repo['name'], ref) for repo in repositories
              for _, ref in frontier_references(repo['frontier'])}
    active_queued = {qualify(repo['name'], ref) for repo in repositories
                     if repo['frontier'].get('lifecycle', 'active') == 'active'
                     for _, ref in frontier_references(repo['frontier'])}
    digest = hashlib.sha256()
    for repo in repositories:
        digest.update(str(repo['root']).encode())
        for path, raw in repo['sources']:
            digest.update(path.encode() + b'\0' + raw)
        for task_id, entry in repo['tasks'].items():
            task = entry['record']
            entry['dependencies'] = [dependency_state(repo, ref, {repo['name'] + '#' + task_id}) for ref in task['depends']]
            entry['queued'] = repo['name'] + '#' + task_id in queued
            entry['ready'] = (repo['name'] + '#' + task_id in active_queued and not repo['errors'] and repo['frontier'].get('lifecycle', 'active') == 'active'
                              and task['status'] == 'planned' and not active_blockers(task['current']['blockers'])
                              and all(x['state'] == 'satisfied' for x in entry['dependencies']))
            for dep in entry['dependencies']:
                if dep['state'] in ('unavailable', 'missing', 'cycle', 'prerequisites-open', 'depth-limit'):
                    repo['warnings'].append(task_id + ': dependency ' + dep['reference'] + ' ' + dep['state'])
    return {'identity': digest.hexdigest(), 'repositories': repositories, 'index': index}


def compact_blocker(blocker):
    if isinstance(blocker, str):
        return blocker
    return {key: blocker[key] for key in ('id', 'disposition', 'area', 'observed', 'nextAction') if key in blocker}


def summary(repo, entry):
    task = entry['record']
    return {**{key: task[key] for key in ('id', 'title', 'status', 'outcome')},
            'current': {'summary': task['current']['summary'], 'nextAction': task['current']['nextAction'],
                        'blockers': [compact_blocker(b) for b in task['current']['blockers']]},
            'repository': repo['name'], 'lifecycle': repo['frontier'].get('lifecycle', 'active'),
            'activeBlockerCount': len(active_blockers(task['current']['blockers'])),
            'queued': entry['queued'], 'ready': entry['ready'], 'dependencies': entry['dependencies'],
            'completedAt': task.get('completedAt'), 'updatedAt': task.get('updatedAt'),
            'sourceUpdatedAt': entry['sourceUpdatedAt']}


def overview(state, repository='', status='', search='', offset=0, limit=PAGE_SIZE, scope='queued'):
    rows = []
    repos = []
    order = {}
    for source in state['repositories']:
        for lane in ('product', 'maintenance', 'parallel'):
            refs = source['frontier'].get(lane, [])
            for position, ref in enumerate(refs if isinstance(refs, list) else []):
                if reference(ref):
                    order.setdefault(qualify(source['name'], ref), []).append(
                        {'repository': source['name'], 'lane': lane, 'position': position + 1})
    for repo in state['repositories']:
        repos.append({'repository': repo['name'], 'objective': repo['frontier'].get('objective', ''),
                      'mode': repo['frontier'].get('mode'), 'lifecycle': repo['frontier'].get('lifecycle', 'active'),
                      'errors': repo['errors'], 'warnings': repo['warnings'], 'counts': {
                          value: sum(e['record']['status'] == value and (scope == 'all' or e['queued'])
                                     for e in repo['tasks'].values()) for value in STATUSES}})
        if repository and repository != repo['name']:
            continue
        for entry in repo['tasks'].values():
            row = summary(repo, entry)
            if scope == 'queued' and not row['queued']:
                continue
            row['queue'] = order.get(repo['name'] + '#' + row['id'], [])
            if status and row['status'] != status:
                continue
            if search and search.casefold() not in json.dumps(row, ensure_ascii=False).casefold():
                continue
            rows.append(row)
    def row_order(row):
        group = 0 if row['status'] in ('in-progress', 'blocked') else 1 if row['queue'] and row['status'] == 'planned' else 2
        retired = row['lifecycle'] == 'retired'
        position = min((q['position'] for q in row['queue']), default=10 ** 9)
        stamp = (row['completedAt'] or row['sourceUpdatedAt']) if row['status'] == 'done' else (row['updatedAt'] or row['sourceUpdatedAt'])
        # Reverse timestamp order without depending on lexical timezone offsets.
        try:
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            seconds = parsed.timestamp()
        except (ValueError, OSError):
            seconds = 0
        return (retired, group, row['repository'] if group < 2 else '',
                position if group == 1 else 0, -seconds if group == 2 else 0, row['repository'], row['id'])
    rows.sort(key=row_order)
    return {'identity': state['identity'], 'repositories': repos, 'tasks': rows[offset:offset + limit],
            'total': len(rows), 'offset': offset, 'limit': limit, 'scope': scope}


def task_detail(state, repository, task_id):
    repo = state['index'].get(repository)
    if repo is None or task_id not in repo['tasks']:
        return None
    entry = repo['tasks'][task_id]
    # Deliberately whitelist: project checkpoints/history never enter the payload.
    return {**summary(repo, entry), 'current': {key: entry['record']['current'][key] for key in ('summary', 'nextAction', 'blockers')},
            **{key: entry['record'][key] for key in ('acceptance', 'evidence', 'depends')}}


def now_markdown(state, repo):
    def clean(value):
        return str(value).replace('\n', ' ').replace('\r', ' ')
    lines = ['# Now', '', clean(repo['frontier'].get('objective', '')), '',
             'Generated from work/frontier.json and work/tasks/*.json. Task counts do not establish release acceptance.', '',
             'Mode: ' + str(repo['frontier'].get('mode', 'unknown')) +
             '; lifecycle: ' + repo['frontier'].get('lifecycle', 'active') + '.', '']
    for lane in ('product', 'maintenance', 'parallel'):
        lines.extend(['## ' + lane.capitalize(), ''])
        for position, ref in enumerate(repo['frontier'].get(lane, []) if isinstance(repo['frontier'].get(lane), list) else [], 1):
            if not reference(ref):
                continue
            name, task_id = qualify(repo['name'], ref).split('#', 1)
            detail = task_detail(state, name, task_id)
            if detail is None:
                lines.append(str(position) + '. ' + clean(ref) + ' — unavailable')
            else:
                label = 'ready' if detail['ready'] else 'not ready'
                lines.append(str(position) + '. ' + clean(ref) + ' — ' + clean(detail['title']) + ' [' + detail['status'] + '; ' + label + ']')
                lines.append('   Next: ' + clean(detail['current']['nextAction']))
        lines.append('')
    if repo['errors'] or repo['warnings']:
        lines.extend(['## Input issues', ''])
        lines.extend('- ' + clean(message) for message in repo['errors'] + repo['warnings'])
        lines.append('')
    return '\n'.join(lines).rstrip('\n') + '\n'


HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Project work</title><style>
:root{font:16px system-ui,sans-serif;color:#152438;background:#f3f6fa}body{max-width:1320px;margin:0 auto;padding:24px}h1{margin-bottom:4px}p{line-height:1.5}.sub{color:#43546a}.filters{display:flex;flex-wrap:wrap;gap:16px;margin:24px 0}label{display:grid;gap:6px}input,select,button{font:inherit;padding:10px;border:1px solid #52647b;border-radius:5px;background:white;color:#152438}button{cursor:pointer;text-align:left}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #005fcc;outline-offset:3px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:20px}section{min-width:0}h2{font-size:1.2rem}article{background:white;padding:16px;margin-bottom:12px;border:1px solid #c4cedb;border-radius:6px;overflow-wrap:anywhere}article button{font-weight:650;border:0;padding:0;line-height:1.5;text-decoration:underline}article p{margin:8px 0}.badge{font-size:.88rem;color:#43546a}.issue{border-left:4px solid #a33c00;padding-left:12px}#detail{margin:24px 0;background:white;border:2px solid #52647b;padding:20px;overflow-wrap:anywhere}pre{white-space:pre-wrap;font:inherit}#pager{display:flex;gap:12px;margin:20px 0}a{color:#0055aa}small{line-height:1.5} @media(max-width:450px){body{padding:14px}.filters>*{width:100%}}
</style><header><h1>Project work</h1><p class="sub">Canonical repository tasks · read-only · refreshes every 3 seconds</p><p>Queue order shows intent. “Ready” requires completed dependencies and no active blockers. Completed task counts do not establish release acceptance.</p></header>
<div class="filters"><label>Work scope<select id="scope"><option value="queued">Current queue</option><option value="all">All records</option></select></label><label>Repository<select id="repo"><option value="">All repositories</option></select></label><label>Status<select id="status"><option value="">All statuses</option><option>planned</option><option>in-progress</option><option>blocked</option><option>done</option><option>cancelled</option></select></label><label>Search<input id="search" type="search" placeholder="Task, title, next action"></label></div>
<p id="live" role="status" aria-live="polite">Loading canonical records…</p><div id="issues"></div><div id="detail" hidden tabindex="-1"></div><main class="grid"><section><h2>In progress / blocked</h2><div id="active"></div></section><section><h2>Next in queue</h2><div id="next"></div></section><section><h2>Done / recently updated</h2><div id="recent"></div></section><section><h2>Retired repositories</h2><div id="retired"></div></section></main><div id="pager"><button id="prev">Previous page</button><button id="more">Next page</button></div>
<script>
'use strict';
const $=id=>document.getElementById(id);let identity='',offset=0,selection=null,request=0,lastRendered='',knownRepos='';
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function pretty(value){return typeof value==='string'?value:JSON.stringify(value,null,2);}
function lines(target,title,values){target.append(node('h3',title));if(!values.length)target.append(node('p','None recorded'));values.forEach(v=>target.append(node('pre',pretty(v))));}
async function detail(repo,id,focus=false){const response=await fetch('/api/task?'+new URLSearchParams({repository:repo,id}));if(!response.ok)throw Error('Task unavailable');const task=await response.json();selection={repo,id};const box=$('detail');box.replaceChildren();const close=node('button','Close detail');close.onclick=()=>{box.hidden=true;selection=null;const trigger=[...document.querySelectorAll('article button')].find(n=>n.dataset.key===repo+'#'+id);if(trigger)trigger.focus();};box.append(close,node('h2',task.id+' · '+task.title),node('p',task.repository+' · '+task.status+(task.queued?'':' · Outside current queue')),node('p',task.outcome),node('p',task.current.summary),node('p','Next action: '+task.current.nextAction));lines(box,'Blocker records ('+task.activeBlockerCount+' active)',task.current.blockers);lines(box,'Dependencies',task.dependencies);lines(box,'Acceptance',task.acceptance);lines(box,'Evidence',task.evidence);box.hidden=false;if(focus)box.focus();}
function card(task){const a=node('article');const b=node('button',task.id+' · '+task.title);b.dataset.key=task.repository+'#'+task.id;b.onclick=()=>detail(task.repository,task.id,true).catch(showError);a.append(node('div',task.repository+' · '+task.status+(task.queued?'':' · Outside current queue'),'badge'),b,node('p',task.current.summary),node('p','Next: '+task.current.nextAction));if(task.current.blockers.length)a.append(node('p','Blocker records ('+task.activeBlockerCount+' active): '+task.current.blockers.map(pretty).join('; '),task.activeBlockerCount?'issue':'badge'));if(task.dependencies.some(d=>d.state!=='satisfied'))a.append(node('p','Prerequisites: '+task.dependencies.filter(d=>d.state!=='satisfied').map(d=>d.reference+' ('+d.state+')').join('; ')));if(task.queue.length)a.append(node('p',task.queue.map(q=>q.repository+' '+q.lane+' #'+q.position).join(' · ')+' · '+(task.ready?'Ready':'Not ready')));if(task.status==='done')a.append(node('p',task.completedAt?'Completed: '+task.completedAt:'Completion time unknown · source updated: '+task.sourceUpdatedAt,'badge'));else a.append(node('p',task.updatedAt?'Updated: '+task.updatedAt:'Source updated: '+task.sourceUpdatedAt,'badge'));return a;}
function showError(error){$('live').textContent='Refresh failed: '+error.message+'; showing the previous successful view.';}
async function refresh(){const serial=++request;const params=new URLSearchParams({scope:$('scope').value,repository:$('repo').value,status:$('status').value,search:$('search').value,offset:String(offset)});const response=await fetch('/api/overview?'+params);if(!response.ok)throw Error('Could not load tasks');const data=await response.json();if(serial!==request)return;
const names=data.repositories.map(r=>r.repository);const namesKey=JSON.stringify(names);if(namesKey!==knownRepos){const previous=$('repo').value;while($('repo').options.length>1)$('repo').remove(1);names.forEach(name=>{const option=node('option',name);option.value=name;$('repo').append(option);});$('repo').value=names.includes(previous)?previous:'';knownRepos=namesKey;}
const key=data.identity+'|'+params.toString();if(key===lastRendered)return;const focusedKey=document.activeElement&&document.activeElement.dataset.key;const changed=identity&&identity!==data.identity;identity=data.identity;lastRendered=key;['active','next','recent','retired','issues'].forEach(id=>$(id).replaceChildren());for(const repo of data.repositories){if(repo.errors.length||repo.warnings.length){const issue=node('p',repo.repository+': '+repo.errors.concat(repo.warnings).join('; '),'issue');$('issues').append(issue);}}
const rows=data.tasks;const active=rows.filter(t=>t.lifecycle!=='retired'&&['in-progress','blocked'].includes(t.status));const next=rows.filter(t=>t.lifecycle!=='retired'&&t.queue.length&&!['done','cancelled'].includes(t.status));next.sort((a,b)=>a.repository.localeCompare(b.repository)||(Math.min(...a.queue.map(q=>q.position))-Math.min(...b.queue.map(q=>q.position)))||a.id.localeCompare(b.id));const recent=rows.filter(t=>t.lifecycle!=='retired');recent.sort((a,b)=>{const at=a.status==='done'?(a.completedAt||a.sourceUpdatedAt):(a.updatedAt||a.sourceUpdatedAt),bt=b.status==='done'?(b.completedAt||b.sourceUpdatedAt):(b.updatedAt||b.sourceUpdatedAt);return Date.parse(bt)-Date.parse(at)||a.id.localeCompare(b.id);});const groups={active,next,recent:recent.slice(0,30),retired:rows.filter(t=>t.lifecycle==='retired')};for(const [id,tasks] of Object.entries(groups)){tasks.forEach(task=>$(id).append(card(task)));if(!tasks.length)$(id).append(node('p','No matching tasks'));}$('live').textContent=(changed?'Source changed · ':'')+data.total+' matching tasks · showing '+Math.min(data.total,offset+1)+'–'+Math.min(data.total,offset+data.tasks.length)+' · input '+data.identity.slice(0,12);if(focusedKey){const target=[...document.querySelectorAll('article button')].find(n=>n.dataset.key===focusedKey);if(target)target.focus();}$('prev').disabled=offset===0;$('more').disabled=offset+data.limit>=data.total;if(selection)await detail(selection.repo,selection.id);}
['scope','repo','status','search'].forEach(id=>$(id).addEventListener('input',()=>{offset=0;refresh().catch(showError);}));$('prev').onclick=()=>{offset=Math.max(0,offset-100);refresh().catch(showError);};$('more').onclick=()=>{offset+=100;refresh().catch(showError);};refresh().catch(showError);setInterval(()=>refresh().catch(showError),3000);
</script></html>'''


def make_server(workspace, explicit=(), port=8765):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, code, body, kind='application/json; charset=utf-8'):
            encoded = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(encoded)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            # Reject foreign Host to prevent DNS rebinding; no CORS access.
            if self.headers.get('Host', '').split(':')[0] not in ('127.0.0.1', 'localhost'):
                return self.respond(403, '{"error":"loopback Host required"}')
            parsed = urlsplit(self.path)
            if parsed.path == '/':
                return self.respond(200, HTML, 'text/html; charset=utf-8')
            if parsed.path not in ('/api/overview', '/api/task'):
                return self.respond(404, '{"error":"unknown endpoint"}')
            query = parse_qs(parsed.query)
            def value(name, default=''):
                return query.get(name, [default])[0]
            try:
                state = snapshot(discover(workspace, explicit))
                if parsed.path == '/api/task':
                    if not reference(value('id')) or '#' in value('id'):
                        return self.respond(400, '{"error":"invalid task id"}')
                    payload = task_detail(state, value('repository'), value('id'))
                    if payload is None:
                        return self.respond(404, '{"error":"task not found"}')
                else:
                    offset = max(0, int(value('offset', '0')))
                    limit = min(PAGE_SIZE, max(1, int(value('limit', str(PAGE_SIZE)))))
                    scope = value('scope', 'queued')
                    if scope not in ('queued', 'all'):
                        return self.respond(400, '{"error":"scope must be queued or all"}')
                    payload = overview(state, value('repository'), value('status'), value('search')[:500], offset, limit, scope)
                self.respond(200, json.dumps(payload, ensure_ascii=False))
            except (OSError, ValueError) as exc:
                self.respond(400, json.dumps({'error': str(exc)}))

        def reject_write(self):
            self.respond(405, '{"error":"read-only; use GET or HEAD"}')
        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = reject_write
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'), help='repository root (default: current directory)')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('validate', 'build', 'list', 'show'):
        sub = commands.add_parser(command)
        sub.add_argument('--root', type=Path, default=argparse.SUPPRESS, help='repository root')
        sub.add_argument('--workspace', type=Path, help='resolve cross-repository references in immediate Git projects')
        if command in ('list', 'show'):
            sub.add_argument('--json', action='store_true')
        if command == 'build':
            sub.add_argument('--check', action='store_true', help='read-only check that generated NOW.md is current')
        if command == 'list':
            sub.add_argument('--status', choices=STATUSES)
            sub.add_argument('--scope', choices=('queued', 'all'), default='queued', help='current frontier or all records')
            sub.add_argument('--limit', type=int, default=100)
            sub.add_argument('--offset', type=int, default=0)
        if command == 'show':
            sub.add_argument('id')
    serve = commands.add_parser('serve')
    serve.add_argument('--workspace', type=Path, required=True)
    serve.add_argument('--repo', type=Path, action='append', default=[], help='explicit additional repository (including retired repositories)')
    serve.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    if args.command == 'serve':
        server = make_server(args.workspace, args.repo, args.port)
        print('Read-only project work: http://127.0.0.1:' + str(server.server_port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    state = snapshot(discover(args.workspace, [args.root]))
    repo = next(repo for repo in state['repositories'] if repo['root'] == args.root.resolve())
    if args.command == 'validate':
        print(json.dumps({'repository': repo['name'], 'valid': not repo['errors'], 'errors': repo['errors'], 'warnings': repo['warnings']}, indent=2))
        return int(bool(repo['errors']))
    if args.command == 'build':
        if repo['errors']:
            print('\n'.join(repo['errors']), file=sys.stderr)
            return 1
        target = args.root / 'work/NOW.md'
        content = now_markdown(state, repo)
        fresh = target.exists() and target.read_bytes() == content.encode('utf-8')
        if args.check:
            if not fresh:
                print('work/NOW.md is stale or missing; run build', file=sys.stderr)
                return 1
            print('work/NOW.md current')
            return 0
        if not fresh:
            handle, temporary = tempfile.mkstemp(prefix='.NOW-', dir=str(target.parent))
            try:
                with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as output:
                    output.write(content)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        print('work/NOW.md current')
        return 0
    if args.command == 'show':
        payload = task_detail(state, repo['name'], args.id)
        if payload is None:
            print('Unknown task: ' + args.id, file=sys.stderr)
            return 1
    else:
        payload = overview(state, repo['name'], args.status or '', offset=max(0, args.offset), limit=max(1, min(PAGE_SIZE, args.limit)), scope=args.scope)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.command == 'show':
        print(payload['id'] + ' ' + payload['title'] + ' [' + payload['status'] + ']')
        print(payload['outcome'] + '\n' + payload['current']['summary'] + '\nNext: ' + payload['current']['nextAction'])
        for field in ('dependencies', 'acceptance', 'evidence'):
            print(field.capitalize() + ': ' + json.dumps(payload[field], ensure_ascii=False))
    else:
        for task in payload['tasks']:
            print(task['id'] + ' [' + task['status'] + '] ' + task['title'])
        print(str(payload['total']) + ' matching tasks; offset ' + str(payload['offset']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
