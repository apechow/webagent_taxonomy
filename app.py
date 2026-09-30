#!/usr/bin/env python3
"""
Web interface for annotating WebArena tasks across all websites
Supports multiple annotators with agreement analysis
"""

from flask import Flask, jsonify, request, send_from_directory
from collections import Counter
import json
import os

app = Flask(__name__, static_folder='static')

TASKS_FILE = 'webarena_tasks.json'
ANNOTATIONS_FILE = 'annotations.json'

def load_tasks():
    with open(TASKS_FILE, 'r') as f:
        return json.load(f)

VALID_MARKS = ['safe', 'safe_with_influence', 'no_replanning', 'no_other']
LEGACY_MARKS = ['yes', 'no', 'maybe']
ALL_MARKS = VALID_MARKS + LEGACY_MARKS

def is_legacy_mark(mark):
    return mark in LEGACY_MARKS

def load_annotations():
    """
    Annotations structure:
    {
      "task_id": {
        "annotator_name": {"mark": "safe/safe_with_influence/no_replanning/no_other", "comment": "..."},
        ...
      },
      ...
    }
    Legacy marks (yes/no/maybe) are still recognized but flagged for review.
    """
    if os.path.exists(ANNOTATIONS_FILE):
        with open(ANNOTATIONS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_annotations(annotations):
    with open(ANNOTATIONS_FILE, 'w') as f:
        json.dump(annotations, f, indent=2)

def get_annotators(annotations):
    """Get list of all annotators"""
    annotators = set()
    for task_annotations in annotations.values():
        annotators.update(task_annotations.keys())
    return sorted(list(annotators))

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/summary')
def summary_page():
    return send_from_directory('static', 'summary.html')

@app.route('/api/websites')
def get_websites():
    """Get list of all unique websites in the dataset"""
    tasks = load_tasks()
    websites = set()
    for task in tasks:
        for site in task.get('sites', []):
            websites.add(site)
    return jsonify(sorted(list(websites)))

@app.route('/api/annotators')
def get_annotators_endpoint():
    """Get list of all annotators"""
    annotations = load_annotations()
    return jsonify(get_annotators(annotations))

@app.route('/api/tasks')
def get_tasks():
    """Get tasks, optionally filtered by website"""
    tasks = load_tasks()
    annotations = load_annotations()
    
    # Filter by website if specified
    website = request.args.get('website')
    annotator = request.args.get('annotator')
    
    if website and website != 'all':
        tasks = [t for t in tasks if website in t.get('sites', [])]
    
    # Add annotation info to each task
    for task in tasks:
        task_id = str(task['task_id'])
        task['all_annotations'] = annotations.get(task_id, {})
        
        # Get this annotator's annotation if specified
        if annotator and task_id in annotations:
            task['annotation'] = annotations[task_id].get(annotator)
        else:
            task['annotation'] = None
    
    return jsonify(tasks)

@app.route('/api/tasks/<int:task_id>')
def get_task(task_id):
    tasks = load_tasks()
    annotations = load_annotations()
    annotator = request.args.get('annotator')
    
    for task in tasks:
        if task['task_id'] == task_id:
            task_id_str = str(task_id)
            task['all_annotations'] = annotations.get(task_id_str, {})
            
            if annotator and task_id_str in annotations:
                task['annotation'] = annotations[task_id_str].get(annotator)
            else:
                task['annotation'] = None
            return jsonify(task)
    
    return jsonify({'error': 'Task not found'}), 404

@app.route('/api/annotations/<int:task_id>', methods=['POST'])
def save_annotation(task_id):
    data = request.json
    mark = data.get('mark')  # safe/safe_with_influence/no_replanning/no_other
    comment = data.get('comment', '')
    annotator = data.get('annotator')
    
    if not annotator:
        return jsonify({'error': 'Annotator name required'}), 400
    
    if mark not in VALID_MARKS and mark is not None:
        return jsonify({'error': f'Invalid mark value. Must be one of: {VALID_MARKS}'}), 400
    
    annotations = load_annotations()
    task_id_str = str(task_id)
    
    if task_id_str not in annotations:
        annotations[task_id_str] = {}
    
    if mark is None:
        # Remove annotation if mark is None
        annotations[task_id_str].pop(annotator, None)
        if not annotations[task_id_str]:
            del annotations[task_id_str]
    else:
        annotations[task_id_str][annotator] = {
            'mark': mark,
            'comment': comment
        }
    
    save_annotations(annotations)
    return jsonify({
        'success': True, 
        'task_id': task_id, 
        'annotator': annotator,
        'annotation': annotations.get(task_id_str, {}).get(annotator)
    })

@app.route('/api/stats')
def get_stats():
    """Get stats for a specific annotator, optionally filtered by website"""
    tasks = load_tasks()
    annotations = load_annotations()
    
    website = request.args.get('website')
    annotator = request.args.get('annotator')
    
    if website and website != 'all':
        tasks = [t for t in tasks if website in t.get('sites', [])]
    
    task_ids = set(str(t['task_id']) for t in tasks)
    
    # Get stats for specific annotator
    if annotator:
        annotated = 0
        counts = {m: 0 for m in ALL_MARKS}
        legacy_count = 0
        
        for task_id in task_ids:
            if task_id in annotations and annotator in annotations[task_id]:
                annotated += 1
                mark = annotations[task_id][annotator]['mark']
                if mark in counts:
                    counts[mark] += 1
                if is_legacy_mark(mark):
                    legacy_count += 1
        
        return jsonify({
            'total': len(tasks),
            'annotated': annotated,
            'remaining': len(tasks) - annotated,
            'safe': counts.get('safe', 0),
            'safe_with_influence': counts.get('safe_with_influence', 0),
            'no_replanning': counts.get('no_replanning', 0),
            'no_other': counts.get('no_other', 0),
            'legacy': legacy_count,
            # Keep old keys for backward compat
            'yes': counts.get('yes', 0),
            'no': counts.get('no', 0),
            'maybe': counts.get('maybe', 0)
        })
    
    # Overall stats (any annotation)
    annotated = sum(1 for tid in task_ids if tid in annotations)
    return jsonify({
        'total': len(tasks),
        'annotated': annotated,
        'remaining': len(tasks) - annotated
    })

@app.route('/api/summary')
def get_summary():
    """Get comprehensive summary of all annotations across all annotators"""
    tasks = load_tasks()
    annotations = load_annotations()
    
    all_annotators = get_annotators(annotations)
    
    # Build website stats
    website_stats = {}
    for task in tasks:
        task_id = str(task['task_id'])
        for site in task.get('sites', []):
            if site not in website_stats:
                website_stats[site] = {'total': 0, 'annotated': 0}
            website_stats[site]['total'] += 1
            if task_id in annotations:
                website_stats[site]['annotated'] += 1
    
    # Per-annotator stats
    annotator_stats = {}
    for annotator in all_annotators:
        annotator_stats[annotator] = {
            'total_annotated': 0,
            'safe': 0,
            'safe_with_influence': 0,
            'no_replanning': 0,
            'no_other': 0,
            'legacy': 0,
            'yes': 0,
            'no': 0,
            'maybe': 0
        }
        for task_annotations in annotations.values():
            if annotator in task_annotations:
                annotator_stats[annotator]['total_annotated'] += 1
                mark = task_annotations[annotator]['mark']
                if mark in annotator_stats[annotator]:
                    annotator_stats[annotator][mark] += 1
                if is_legacy_mark(mark):
                    annotator_stats[annotator]['legacy'] += 1
    
    # Agreement analysis
    agreement_data = calculate_agreement(tasks, annotations, all_annotators)
    
    # Get all annotated tasks with details
    annotated_tasks = []
    for task in tasks:
        task_id = str(task['task_id'])
        if task_id in annotations:
            task_data = {
                'task_id': task['task_id'],
                'intent': task.get('intent', ''),
                'sites': task.get('sites', []),
                'annotations': annotations[task_id]
            }
            
            # Calculate consensus for this task
            marks = [a['mark'] for a in annotations[task_id].values()]
            if marks:
                mark_counts = Counter(marks)
                most_common = mark_counts.most_common(1)[0]
                task_data['consensus'] = most_common[0] if most_common[1] > len(marks) / 2 else 'disputed'
                task_data['agreement_ratio'] = most_common[1] / len(marks)
            
            annotated_tasks.append(task_data)
    
    # Overall stats
    total_tasks = len(tasks)
    tasks_with_annotations = len(annotations)
    
    return jsonify({
        'overall': {
            'total_tasks': total_tasks,
            'tasks_annotated': tasks_with_annotations,
            'remaining': total_tasks - tasks_with_annotations,
            'progress_percent': round(tasks_with_annotations / total_tasks * 100, 1) if total_tasks > 0 else 0
        },
        'annotators': all_annotators,
        'annotator_stats': annotator_stats,
        'by_website': website_stats,
        'agreement': agreement_data,
        'annotated_tasks': annotated_tasks
    })

def calculate_agreement(tasks, annotations, annotators):
    """Calculate inter-annotator agreement metrics"""
    if len(annotators) < 2:
        return {
            'pairwise': {},
            'overall_agreement': None,
            'fleiss_kappa': None,
            'tasks_with_disagreement': []
        }
    
    # Pairwise agreement
    pairwise = {}
    for i, ann1 in enumerate(annotators):
        for ann2 in annotators[i+1:]:
            agreed = 0
            total = 0
            for task_annotations in annotations.values():
                if ann1 in task_annotations and ann2 in task_annotations:
                    total += 1
                    if task_annotations[ann1]['mark'] == task_annotations[ann2]['mark']:
                        agreed += 1
            
            key = f"{ann1}_vs_{ann2}"
            pairwise[key] = {
                'annotator1': ann1,
                'annotator2': ann2,
                'agreed': agreed,
                'total': total,
                'agreement_percent': round(agreed / total * 100, 1) if total > 0 else None
            }
    
    # Tasks with disagreement
    disagreements = []
    for task in tasks:
        task_id = str(task['task_id'])
        if task_id in annotations and len(annotations[task_id]) >= 2:
            marks = [a['mark'] for a in annotations[task_id].values()]
            if len(set(marks)) > 1:  # Not all the same
                disagreements.append({
                    'task_id': task['task_id'],
                    'intent': task.get('intent', ''),
                    'annotations': annotations[task_id]
                })
    
    # Overall agreement (% of tasks where all annotators agree)
    full_agreement_count = 0
    multi_annotated_count = 0
    for task_annotations in annotations.values():
        if len(task_annotations) >= 2:
            multi_annotated_count += 1
            marks = [a['mark'] for a in task_annotations.values()]
            if len(set(marks)) == 1:
                full_agreement_count += 1
    
    overall = round(full_agreement_count / multi_annotated_count * 100, 1) if multi_annotated_count > 0 else None
    
    return {
        'pairwise': pairwise,
        'overall_agreement': overall,
        'full_agreement_count': full_agreement_count,
        'multi_annotated_count': multi_annotated_count,
        'tasks_with_disagreement': disagreements[:50]  # Limit for performance
    }

@app.route('/api/export')
def export_annotations():
    return jsonify(load_annotations())

if __name__ == '__main__':
    # Initialize empty annotations file if it doesn't exist
    if not os.path.exists(ANNOTATIONS_FILE):
        save_annotations({})
    
    print("Starting WebArena Task Annotation Server...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
