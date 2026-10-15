"""Read-only, pinned Git comparison. No imports or execution from either branch.

Routes are declarations, not proof of deployed availability or wire compatibility.
Outputs contain paths, field names and migration IDs, never environment/config values.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path


def git(repo, *args):
    return subprocess.check_output(
        ['git', '-C', str(repo), *args], encoding='utf-8', errors='strict'
    ).strip()


def literal(node, constants):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = literal(node.left, constants), literal(node.right, constants)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    if isinstance(node, (ast.Tuple, ast.List)):
        return [literal(item, constants) for item in node.elts]
    return None


def inspect_python(source, path):
    tree = ast.parse(source, filename=path)
    constants, prefixes, routes, models = {}, {}, [], {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            value = literal(node.value, constants)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value
                    call = node.value
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'APIRouter':
                        prefixes[target.id] = next(
                            (literal(k.value, constants) for k in call.keywords if k.arg == 'prefix'), ''
                        )
    # Resolve route expressions after all module constants (PREFIX may follow router).
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
                    continue
                fn = decorator.func
                if not isinstance(fn.value, ast.Name) or fn.value.id not in prefixes:
                    continue
                if fn.attr not in {'get', 'post', 'put', 'patch', 'delete', 'websocket'}:
                    continue
                suffix = literal(decorator.args[0], constants) if decorator.args else None
                prefix = prefixes[fn.value.id]
                resolved = isinstance(prefix, str) and isinstance(suffix, str)
                routes.append({'method': fn.attr.upper(), 'path': prefix + suffix if resolved else None,
                               'expression': ast.unparse(decorator.args[0]) if decorator.args else '',
                               'file': path, 'line': decorator.lineno})
        if isinstance(node, ast.ClassDef) and any(ast.unparse(b) == 'BaseModel' for b in node.bases):
            fields = {n.target.id: ast.unparse(n.annotation) for n in node.body
                      if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
            models[node.name] = fields
    migration = None
    if isinstance(constants.get('revision'), str):
        migration = {'revision': constants['revision'], 'down_revision': constants.get('down_revision'), 'file': path}
    return {'routes': routes, 'models': models, 'migration': migration}


def snapshot(repo, ref):
    sha = git(repo, 'rev-parse', '--verify', ref + '^{commit}')
    files = git(repo, 'ls-tree', '-r', '--name-only', sha).splitlines()
    routes, models, migrations = [], {}, []
    for path in files:
        if not path.endswith('.py') or not path.startswith(('services/backend/app/api/', 'services/backend/migrations/versions/')):
            continue
        parsed = inspect_python(git(repo, 'show', sha + ':' + path), path)
        routes.extend(parsed['routes'])
        models.update({path + ':' + name: fields for name, fields in parsed['models'].items()})
        if parsed['migration']:
            migrations.append(parsed['migration'])
    parents = {p for m in migrations for p in (m['down_revision'] if isinstance(m['down_revision'], list) else [m['down_revision']]) if p}
    swift = [p for p in files if p.startswith('apps/ios/') and p.endswith('.swift')]
    return {'ref': ref, 'sha': sha, 'routes': routes, 'request_model_declarations': models,
            'migrations': migrations, 'migration_heads': sorted(m['revision'] for m in migrations if m['revision'] not in parents),
            'ios_swift_files': swift,
            'ios_last_commit': git(repo, 'log', '-1', '--format=%H %aI %s', sha, '--', 'apps/ios'),
            'ios_tree': git(repo, 'rev-parse', sha + ':apps/ios')}


def compare(left, right):
    def keys(s):
        return {r['method'] + ' ' + r['path'] for r in s['routes'] if r['path'] is not None}
    a, b = keys(left), keys(right)
    models_a, models_b = left['request_model_declarations'], right['request_model_declarations']
    differences = {k: {'android': models_a[k], 'ios_backend': models_b[k]} for k in sorted(models_a.keys() & models_b.keys()) if models_a[k] != models_b[k]}
    common_migrations = {m['revision'] for m in left['migrations']} & {m['revision'] for m in right['migrations']}
    return {'declared_routes_only_android': sorted(a-b), 'declared_routes_only_ios_backend': sorted(b-a),
            'shared_route_count_not_compatibility': len(a & b), 'changed_request_models': differences,
            'shared_migration_revisions': sorted(common_migrations),
            'ios_client_tree_identical': left['ios_tree'] == right['ios_tree']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--android', required=True)
    parser.add_argument('--ios-backend', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    left, right = snapshot(args.repo, args.android), snapshot(args.repo, args.ios_backend)
    result = {'scope': 'Static declarations at pinned commits; not device, deploy, schema-equivalence or semantic validation.',
              'android': left, 'ios_backend': right, 'comparison': compare(left, right)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'android_sha': left['sha'], 'ios_backend_sha': right['sha'],
                      'ios_client_tree_identical': result['comparison']['ios_client_tree_identical'],
                      'migration_heads': [left['migration_heads'], right['migration_heads']],
                      'changed_request_models': list(result['comparison']['changed_request_models'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
