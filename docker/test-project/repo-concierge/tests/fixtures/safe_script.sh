#!/bin/bash
# Test fixture: safe shell script with no risky patterns

echo "Hello, world!"
pip install -r requirements.txt
pytest tests/
python -m repo_concierge scan .
git status
ls -la
mkdir -p output
cp file1.txt file2.txt
