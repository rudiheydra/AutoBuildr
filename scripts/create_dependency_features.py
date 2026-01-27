#!/usr/bin/env python3
"""
Script to create dependency validation and guardrail features.

Based on error report: Orchestrator Infinite Loop caused by circular dependencies
in compute_scheduling_scores() BFS algorithm.

Run with: python scripts/create_dependency_features.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import Feature, create_database
# Initialize database

PROJECT_DIR = Path(__file__).resolve().parent.parent
engine, session_maker = create_database(PROJECT_DIR)
session = session_maker()

# Get the starting priority
max_priority_result = session.query(Feature.priority).order_by(Feature.priority.desc()).first()
start_priority = (max_priority_result[0] + 1) if max_priority_result else 1

features_to_create = [
    # Input Validation (4 features)
    {
        'category': 'error-handling',
        'name': 'Core validate_dependency_graph function detects self-references',
        'description': 'The validate_dependency_graph() function should detect when a feature depends on itself (A -> A). Self-references are always invalid and should be flagged for auto-fix.',
        'steps': [
            'Create a test feature with id=1 and dependencies=[1] (self-reference)',
            'Call validate_dependency_graph() with this feature',
            'Verify the result includes self_references list containing feature id 1',
            'Verify the error type is marked as auto_fixable=True'
        ]
    },
    {
        'category': 'error-handling',
        'name': 'Core validate_dependency_graph function detects simple cycles',
        'description': 'The validate_dependency_graph() function should detect simple cycles (A -> B -> A) and return the cycle path. Simple cycles require user action to resolve.',
        'steps': [
            'Create feature A (id=1) with dependencies=[2]',
            'Create feature B (id=2) with dependencies=[1]',
            'Call validate_dependency_graph() with both features',
            'Verify the result includes cycles list with [1, 2] or [2, 1]',
            'Verify the error type is marked as requires_user_action=True'
        ]
    },
    {
        'category': 'error-handling',
        'name': 'Core validate_dependency_graph function detects complex cycles',
        'description': 'The validate_dependency_graph() function should detect complex cycles (A -> B -> C -> A) and return the full cycle path for user review.',
        'steps': [
            'Create feature A (id=1) with dependencies=[2]',
            'Create feature B (id=2) with dependencies=[3]',
            'Create feature C (id=3) with dependencies=[1]',
            'Call validate_dependency_graph() with all three features',
            'Verify the result includes the complete cycle path [1, 2, 3]',
            'Verify missing dependencies to non-existent features are also detected'
        ]
    },
    {
        'category': 'error-handling',
        'name': 'Core validate_dependency_graph function detects missing dependency targets',
        'description': 'The validate_dependency_graph() function should detect when a feature depends on a non-existent feature ID.',
        'steps': [
            'Create feature A (id=1) with dependencies=[999] (non-existent)',
            'Call validate_dependency_graph() with this feature',
            'Verify the result includes missing_targets dict with {1: [999]}',
            'Verify the function returns structured ValidationResult with all issue types'
        ]
    },

    # Graph Algorithm Safety (5 features)
    {
        'category': 'error-handling',
        'name': 'BFS in compute_scheduling_scores uses visited set to prevent re-processing',
        'description': 'The BFS algorithm in compute_scheduling_scores() must use a visited set to prevent infinite loops when cycles exist in the dependency graph.',
        'steps': [
            'Create features with a cycle: A -> B -> C -> A',
            'Call compute_scheduling_scores() with these features',
            'Verify the function returns without hanging',
            'Verify all features have valid scores assigned',
            'Verify the visited set prevents nodes from being processed multiple times'
        ]
    },
    {
        'category': 'error-handling',
        'name': 'Graph algorithms enforce iteration limit based on feature count',
        'description': 'All graph traversal algorithms should enforce an iteration limit of len(features) * 2 to prevent infinite loops even with unexpected graph structures.',
        'steps': [
            'Add iteration counter to compute_scheduling_scores BFS loop',
            'Set MAX_ITERATIONS = len(features) * 2',
            'When limit is exceeded, log error with algorithm name and bail out',
            'Return partial/safe results rather than hanging',
            'Verify the iteration limit is hit before 100ms on a cyclic graph'
        ]
    },
    {
        'category': 'error-handling',
        'name': 'Iteration limit exceeded logs specific algorithm name and context',
        'description': 'When the iteration limit is hit, the error log should include the algorithm name, current iteration count, and feature count for debugging.',
        'steps': [
            'Trigger iteration limit in compute_scheduling_scores with cyclic data',
            'Verify log message includes: algorithm name (BFS/compute_scheduling_scores)',
            'Verify log message includes: iteration count when limit was hit',
            'Verify log message includes: total feature count',
            'Verify log level is ERROR for visibility'
        ]
    },
    {
        'category': 'error-handling',
        'name': 'All graph traversal functions have cycle protection',
        'description': 'Audit all graph traversal functions (resolve_dependencies, _detect_cycles, compute_scheduling_scores, would_create_circular_dependency) to ensure they all have visited sets.',
        'steps': [
            'Review resolve_dependencies() - verify visited tracking in Kahns algorithm',
            'Review _detect_cycles() - verify visited and rec_stack sets',
            'Review compute_scheduling_scores() - add visited set to BFS',
            'Review would_create_circular_dependency() - verify visited set in DFS',
            'Add iteration limits to any function missing them'
        ]
    },
    {
        'category': 'error-handling',
        'name': 'Graph algorithms return partial safe results on bailout',
        'description': 'When iteration limit is hit, graph algorithms should return partial results for nodes processed so far rather than hanging or crashing.',
        'steps': [
            'Create cyclic dependency graph that triggers iteration limit',
            'Call compute_scheduling_scores() on this graph',
            'Verify function returns a dict (not None or exception)',
            'Verify processed nodes have valid scores',
            'Verify unprocessed nodes get default score of 0'
        ]
    },

    # Startup Health Check (4 features)
    {
        'category': 'functional',
        'name': 'Orchestrator runs validate_dependency_graph on startup',
        'description': 'The orchestrator should call validate_dependency_graph() on startup before processing any features, to detect corrupted dependency data.',
        'steps': [
            'Add startup hook in orchestrator initialization',
            'Load all features from database',
            'Call validate_dependency_graph() with loaded features',
            'If issues found, handle according to issue type before proceeding',
            'Log summary of dependency health check results'
        ]
    },
    {
        'category': 'functional',
        'name': 'Startup health check auto-fixes self-references with warning',
        'description': 'On startup, if self-referencing dependencies (A -> A) are detected, they should be automatically removed and a warning logged.',
        'steps': [
            'Insert a feature with self-reference into database',
            'Start the orchestrator',
            'Verify the self-reference is automatically removed from the feature',
            'Verify a WARNING level log is emitted with feature ID and action taken',
            'Verify orchestrator continues to normal operation after fix'
        ]
    },
    {
        'category': 'functional',
        'name': 'Startup health check blocks on cycles and lists cycle path',
        'description': 'On startup, if circular dependencies are detected (not self-references), the orchestrator should block startup and display the cycle path for user resolution.',
        'steps': [
            'Insert features A -> B -> A into database',
            'Attempt to start the orchestrator',
            'Verify startup is blocked with clear error message',
            'Verify error message includes the cycle path: [A, B, A]',
            'Verify error message instructs user to remove one dependency'
        ]
    },
    {
        'category': 'functional',
        'name': 'Startup health check auto-removes orphaned dependency references',
        'description': 'On startup, if features reference non-existent dependency IDs (orphaned refs from deleted features), automatically remove them with a warning.',
        'steps': [
            'Insert a feature with dependencies=[999] where 999 does not exist',
            'Start the orchestrator',
            'Verify the orphaned dependency reference is removed',
            'Verify a WARNING level log is emitted with details',
            'Verify orchestrator continues to normal operation'
        ]
    },

    # Auto-Repair Logic (3 features)
    {
        'category': 'functional',
        'name': 'Auto-repair function removes self-references from features',
        'description': 'Implement repair_self_references() function that removes self-referencing dependencies from all affected features in a single database transaction.',
        'steps': [
            'Create repair_self_references(session) function',
            'Query all features and check for self-references',
            'Remove self-reference from each affected features dependencies list',
            'Commit changes in a single transaction',
            'Return list of repaired feature IDs for logging'
        ]
    },
    {
        'category': 'functional',
        'name': 'Auto-repair function removes orphaned dependency references',
        'description': 'Implement repair_orphaned_dependencies() function that removes references to non-existent feature IDs.',
        'steps': [
            'Create repair_orphaned_dependencies(session) function',
            'Get set of all valid feature IDs',
            'For each feature, filter dependencies to only valid IDs',
            'Update features with orphaned refs in single transaction',
            'Return dict of {feature_id: [removed_orphan_ids]} for logging'
        ]
    },
    {
        'category': 'functional',
        'name': 'Auto-repair logs before and after state for auditability',
        'description': 'All auto-repair operations should log the state before and after the fix for debugging and audit purposes.',
        'steps': [
            'Before removing self-reference, log: Feature {id} has self-reference, removing',
            'After fix, log: Feature {id} dependencies changed from {old} to {new}',
            'Include timestamp in log entries',
            'Use structured logging format for easy parsing',
            'Verify logs appear at INFO level (not just DEBUG)'
        ]
    },

    # Logging/Reporting (2 features)
    {
        'category': 'functional',
        'name': 'Dependency health check produces clear formatted log output',
        'description': 'The startup health check should produce clear, formatted log output summarizing all detected issues and actions taken.',
        'steps': [
            'Create formatted log header: === DEPENDENCY HEALTH CHECK ===',
            'List self-references found and auto-fixed (if any)',
            'List orphaned references found and auto-removed (if any)',
            'List cycles found requiring user action (if any)',
            'End with summary: X issues auto-fixed, Y issues require attention',
            'If no issues: Dependency graph is healthy'
        ]
    },
    {
        'category': 'style',
        'name': 'Optional UI banner shows when dependency issues detected at startup',
        'description': 'When the orchestrator detects dependency issues at startup, an optional warning banner can be shown in the UI with issue count.',
        'steps': [
            'Add dependency_health endpoint to API that returns issue summary',
            'If issues requiring attention exist, return {has_issues: true, count: N}',
            'UI can optionally display banner: Warning: N dependency issues detected - see logs',
            'Banner should be dismissible',
            'Banner style: yellow/orange warning color, not blocking UI'
        ]
    }
]

# Create all features
created_count = 0
for i, f_data in enumerate(features_to_create):
    db_feature = Feature(
        priority=start_priority + i,
        category=f_data['category'],
        name=f_data['name'],
        description=f_data['description'],
        steps=f_data['steps'],
        passes=False,
        in_progress=False,
    )
    session.add(db_feature)
    created_count += 1

session.commit()
session.close()

print(f'Successfully created {created_count} features starting at priority {start_priority}')
