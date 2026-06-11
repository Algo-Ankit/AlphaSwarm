import os

with open('diff_output.txt', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

changes = {}
current_file = None
for line in lines:
    if line.startswith('diff --git'):
        parts = line.split(' b/')
        if len(parts) > 1:
            current_file = parts[-1].strip()
            changes[current_file] = {'add': 0, 'del': 0}
    elif line.startswith('+') and not line.startswith('+++'):
        if current_file: changes[current_file]['add'] += 1
    elif line.startswith('-') and not line.startswith('---'):
        if current_file: changes[current_file]['del'] += 1

print('--- Diff Summary ---')
for f, cnt in sorted(changes.items()):
    print(f"{f}: +{cnt['add']} -{cnt['del']}")
