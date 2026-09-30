#!/usr/bin/env python3
"""
Web interface for annotating WebArena tasks across all websites.

Annotations are stored per task (no per-annotator breakdown):
{
  "task_id": {"mark": "safe", "comment": ""},
  ...
}
`mark` and `comment` are normally strings. When several annotators disagreed
during aggregation, `mark` is a list of distinct marks (a union) and `comment`
may be a list of distinct comments.
"""

from flask import Flask, jsonify, request, send_from_directory
from collections import Counter
import json
import os

app = Flask(__name__, static_folder='static')

TASKS_FILE = 'webarena_tasks.json'
ANNOTATIONS_FILE = 'annotations.json'

VALID_MARKS = ['safe', 'safe_with_influence', 'no_replanning', 'no_other']
LEGACY_MARKS = ['yes', 'no', 'maybe']
ALL_MARKS = VALID_MARKS + LEGACY_MARKS


def load_tasks():
    with open(TASKS_FILE, 'r') as f:
        return json.load(f)


def load_annotations():
    if os.path.exists(ANNOTATIONS_FILE):
        with open(ANNOTATIONS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_annotations(annotations):
    with open(ANNOTATIONS_FILE, 'w') as f:
        json.dump(annotations, f, indent=2)


def as_list(value):
    """Normalize a string-or-list field to a list."""
    if value is None or value == '':
        return []
    if isinstance(value, list):
        return value
    return [value]


def marks_of(annotation):
    return as_list(annotation.get('mark')) if annotation else []


def is_legacy(annotation):
    return any(m in LEGACY_MARKS for m in marks_of(annotation))


def is_disputed(annotation):
    return len(marks_of(annotation)) > 1


def filter_tasks_by_website(tasks, website):
    if website and website != 'all':
        return [t for t in tasks if website in t.get('sites', [])]
    return tasks


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/summary')
def summary_page():
    return send_from_directory('static', 'summary.html')


@app.route('/api/websites')
def get_websites():
    tasks = load_tasks()
    websites = set()
    for task in tasks:
        websites.update(task.get('sites', []))
    return jsonify(sorted(websites))


@app.route('/api/tasks')
def get_tasks():
    tasks = filter_tasks_by_website(load_tasks(), request.args.get('website'))
    annotations = load_annotations()
    for task in tasks:
        task['annotation'] = annotations.get(str(task['task_id']))
    return jsonify(tasks)


@app.route('/api/tasks/<int:task_id>')
def get_task(task_id):
    annotations = load_annotations()
    for task in load_tasks():
        if task['task_id'] == task_id:
            task['annotation'] = annotations.get(str(task_id))
            return jsonify(task)
    return jsonify({'error': 'Task not found'}), 404


@app.route('/api/annotations/<int:task_id>', methods=['POST'])
def save_annotation(task_id):
    data = request.json or {}
    mark = data.get('mark')
    comment = data.get('comment', '')

    if mark is not None and mark not in VALID_MARKS:
        return jsonify({'error': f'Invalid mark value. Must be one of: {VALID_MARKS}'}), 400

    annotations = load_annotations()
    key = str(task_id)

    if mark is None:
        annotations.pop(key, None)
    else:
        annotations[key] = {'comment': comment, 'mark': mark}

    save_annotations(annotations)
    return jsonify({'success': True, 'task_id': task_id, 'annotation': annotations.get(key)})


def count_marks(annotations, task_ids):
    """Count marks across the given tasks. Disputed tasks count once per mark."""
    counts = {m: 0 for m in ALL_MARKS}
    annotated = legacy = disputed = 0
    for tid in task_ids:
        ann = annotations.get(tid)
        if not ann:
            continue
        annotated += 1
        for m in marks_of(ann):
            if m in counts:
                counts[m] += 1
        if is_legacy(ann):
            legacy += 1
        if is_disputed(ann):
            disputed += 1
    return counts, annotated, legacy, disputed


@app.route('/api/stats')
def get_stats():
    tasks = filter_tasks_by_website(load_tasks(), request.args.get('website'))
    annotations = load_annotations()
    task_ids = [str(t['task_id']) for t in tasks]
    counts, annotated, legacy, disputed = count_marks(annotations, task_ids)
    return jsonify({
        'total': len(tasks),
        'annotated': annotated,
        'remaining': len(tasks) - annotated,
        'legacy': legacy,
        'disputed': disputed,
        **{m: counts[m] for m in ALL_MARKS},
    })


@app.route('/api/summary')
def get_summary():
    tasks = load_tasks()
    annotations = load_annotations()

    # Per-website progress and mark breakdown
    by_website = {}
    for task in tasks:
        ann = annotations.get(str(task['task_id']))
        for site in task.get('sites', []):
            ws = by_website.setdefault(site, {'total': 0, 'annotated': 0, **{m: 0 for m in VALID_MARKS}})
            ws['total'] += 1
            if ann:
                ws['annotated'] += 1
                for m in marks_of(ann):
                    if m in VALID_MARKS:
                        ws[m] += 1

    task_ids = [str(t['task_id']) for t in tasks]
    counts, annotated, legacy, disputed = count_marks(annotations, task_ids)

    annotated_tasks = []
    for task in tasks:
        ann = annotations.get(str(task['task_id']))
        if not ann:
            continue
        marks = marks_of(ann)
        annotated_tasks.append({
            'task_id': task['task_id'],
            'intent': task.get('intent', ''),
            'sites': task.get('sites', []),
            'marks': marks,
            'comments': as_list(ann.get('comment')),
            'status': 'disputed' if len(marks) > 1 else (marks[0] if marks else 'unmarked'),
            'legacy': is_legacy(ann),
        })

    total = len(tasks)
    return jsonify({
        'overall': {
            'total_tasks': total,
            'tasks_annotated': annotated,
            'remaining': total - annotated,
            'progress_percent': round(annotated / total * 100, 1) if total else 0,
            'legacy': legacy,
            'disputed': disputed,
        },
        'marks': {m: counts[m] for m in ALL_MARKS},
        'by_website': by_website,
        'annotated_tasks': annotated_tasks,
    })


@app.route('/api/export')
def export_annotations():
    return jsonify(load_annotations())


if __name__ == '__main__':
    if not os.path.exists(ANNOTATIONS_FILE):
        save_annotations({})
    print("Starting WebArena Task Annotation Server...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
