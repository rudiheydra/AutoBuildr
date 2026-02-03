---
description: Sync app_spec.txt with current features in database
---

# PROJECT DIRECTORY

This command **requires** the project directory as an argument via `$ARGUMENTS`.

**Example:** `/sync-spec generations/my-app`

If `$ARGUMENTS` is empty, inform the user they must provide a project path and exit.

---

# GOAL

Synchronize the `app_spec.txt` file with the actual features in the database. This resolves the drift that occurs when using `/expand-project` (which adds features to the database but doesn't update the spec file).

After running this command:
- `<feature_count>` will match the actual number of features in the database
- `<core_features>` will reflect all features grouped by category
- All other sections (tech stack, overview, design system, etc.) will be preserved

---

# YOUR ROLE

You are the **Spec Sync Assistant**. Your job is to:

1. Read the existing `app_spec.txt` to understand its structure
2. Query the features database to get the current feature list
3. Regenerate the `<core_features>` section from the database
4. Update the `<feature_count>` to match reality
5. Write the updated spec file

---

# STEP 1: Read Current Spec

Read the existing specification file:

```
$ARGUMENTS/prompts/app_spec.txt
```

If the file doesn't exist, inform the user:

> "No app_spec.txt found at `$ARGUMENTS/prompts/app_spec.txt`. Please run `/create-spec` first to create an initial specification."

And exit.

---

# STEP 2: Query Features Database

Use the Bash tool to run a Python script that queries the features database and outputs grouped features as JSON.

**Run this command:**

```bash
python3 -c "
import sqlite3
import json
from pathlib import Path
from collections import defaultdict

db_path = Path('$ARGUMENTS') / 'features.db'
if not db_path.exists():
    print(json.dumps({'error': 'Database not found', 'path': str(db_path)}))
    exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all features grouped by category
cursor.execute('''
    SELECT id, category, name, description, passes, in_progress
    FROM features
    ORDER BY category, priority, id
''')

rows = cursor.fetchall()
conn.close()

# Group by category
by_category = defaultdict(list)
for row in rows:
    by_category[row['category']].append({
        'id': row['id'],
        'name': row['name'],
        'description': row['description'],
        'passes': bool(row['passes']),
        'in_progress': bool(row['in_progress'])
    })

# Summary stats
total = len(rows)
passing = sum(1 for r in rows if r['passes'])

print(json.dumps({
    'total': total,
    'passing': passing,
    'pending': total - passing,
    'categories': dict(by_category)
}, indent=2))
"
```

If the database doesn't exist, inform the user:

> "No features.db found. The project doesn't have any features yet. Please run `/create-spec` or `/expand-project` first."

---

# STEP 3: Compare and Report

Present a summary to the user:

> "**Current State:**
>
> - **app_spec.txt says:** [feature_count from spec] features
> - **Database has:** [total from query] features ([passing] passing, [pending] pending)
>
> **Categories in database:**
> - [Category 1]: [count] features
> - [Category 2]: [count] features
> - ...
>
> Would you like me to update app_spec.txt to reflect the database?"

**Wait for user confirmation before proceeding.**

---

# STEP 4: Update app_spec.txt

Once the user confirms, update the spec file:

## 4a. Update `<feature_count>`

Find and replace the existing `<feature_count>` tag:

```xml
<feature_count>[actual total from database]</feature_count>
```

## 4b. Regenerate `<core_features>`

Replace the entire `<core_features>...</core_features>` section with features from the database:

```xml
<core_features>
  <[category_name]>
    - [Feature name 1]
    - [Feature name 2]
    - [Feature name 3]
  </[category_name]>

  <[another_category]>
    - [Feature name 4]
    - [Feature name 5]
  </[another_category]>

  <!-- Repeat for all categories -->
</core_features>
```

**Rules for generating `<core_features>`:**
- Use the category name from the database as the XML tag (convert spaces to underscores, lowercase)
- List each feature by name only (not description)
- Group features under their category
- Order categories alphabetically
- Order features within each category by their database order (priority, then id)

**Example transformation:**

Database has:
```json
{
  "categories": {
    "Authentication": [
      {"name": "User can register with email"},
      {"name": "User can log in"}
    ],
    "UI": [
      {"name": "Dashboard shows user profile"},
      {"name": "Settings page allows theme change"}
    ]
  }
}
```

Becomes:
```xml
<core_features>
  <authentication>
    - User can register with email
    - User can log in
  </authentication>

  <ui>
    - Dashboard shows user profile
    - Settings page allows theme change
  </ui>
</core_features>
```

## 4c. Preserve Everything Else

**DO NOT modify** these sections (preserve them exactly):
- `<project_name>`
- `<overview>`
- `<technology_stack>`
- `<prerequisites>`
- `<security_and_access_control>`
- `<database_schema>`
- `<api_endpoints_summary>`
- `<ui_layout>`
- `<design_system>`
- `<implementation_steps>`
- `<success_criteria>`

---

# STEP 5: Confirm Completion

After updating the file, tell the user:

> "**app_spec.txt has been synced!**
>
> **Changes made:**
> - Updated `<feature_count>` from [old] to [new]
> - Regenerated `<core_features>` with [N] categories and [M] total features
>
> **Categories:**
> - [Category 1]: [count] features
> - [Category 2]: [count] features
> - ...
>
> The spec file now accurately reflects your features database."

---

# EDGE CASES

## Empty Database

If the database has 0 features:

> "The features database is empty (0 features). There's nothing to sync. Did you mean to run `/expand-project` to add features first?"

## No Changes Needed

If the feature count already matches and all categories are the same:

> "**Already in sync!** The app_spec.txt already reflects the database:
> - Feature count: [N]
> - Categories: [list]
>
> No changes needed."

## Missing Sections

If `app_spec.txt` is missing the `<core_features>` section, add it before `</project_specification>`.

If `app_spec.txt` is missing the `<feature_count>` tag, add it after `</prerequisites>`.

---

# IMPORTANT GUIDELINES

1. **Read before writing** - Always read the current spec first to understand its structure
2. **Preserve formatting** - Keep the same indentation style as the original file
3. **Preserve content** - Only modify `<feature_count>` and `<core_features>`, nothing else
4. **Confirm before changes** - Always show the user what will change and get confirmation
5. **Report results** - Always summarize what was changed after completion

---

# BEGIN

Start by checking if the required argument was provided. If not, show usage help:

> "Usage: `/sync-spec <project-path>`
>
> Example: `/sync-spec generations/my-app`
>
> This command syncs your app_spec.txt with the features in your database."

If the argument was provided, read the app_spec.txt file.
