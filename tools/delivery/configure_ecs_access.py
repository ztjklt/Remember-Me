"""ECS root-only demo network change, default preview; never touches SSH/database.

Public HTTPS is a scope change and needs the owner's explicit choice. Preserve
the existing blog's network boundary because it shares port 443. Application
registration/auth/story permissions are not changed. Back up before applying.
"""
import argparse
from datetime import datetime, timezone
import difflib
import json
import os
from pathlib import Path
import re
import subprocess

APP = Path('/etc/nginx/sites-available/remember-me-ip443.conf')
BLOG = Path('/etc/nginx/sites-available/blog.conf')


def validate_firewall(firewall):
    actual = set()
    for line in firewall.splitlines():
        match = re.match(r'^443/tcp\s+ALLOW\s+(\S+)', line)
        if match:
            actual.add(match.group(1))
    if actual != {'120.236.174.183', '183.6.9.111'}:
        raise RuntimeError('Existing HTTPS allowlist drifted; no change applied')


def candidate(app, blog):
    # Only the specific IP vhost and the known named blog are supported.
    if 'server_name 39.108.183.47;' not in app or 'skyspace.cloud' not in blog:
        raise ValueError('Unexpected virtual hosts; inspect instead of editing')
    restricted = re.search(r'    allow 183\.6\.9\.111;\n    allow 127\.0\.0\.1;\n    deny all;\n', app)
    if not restricted:
        raise ValueError('Unexpected App ACL; inspect before opening HTTPS')
    app = app[:restricted.start()] + '    # Account-gated team demo: HTTPS network entry is public.\n' + app[restricted.end():]
    if 'remember-me-preserve-blog-access' in blog:
        raise ValueError('Blog already has managed ACL; inspect saved state')
    # Return at server rewrite phase, so an existing blog redirect cannot bypass
    # the old network boundary before Nginx's later access phase runs.
    geo = ('# remember-me-preserve-blog-access: existing IPv4 HTTPS allowlist\n'
           'geo $remember_team_blog_access {\n    default 0;\n    120.236.174.183 1;\n    183.6.9.111 1;\n    127.0.0.1 1;\n}\n')
    acl = '    if ($remember_team_blog_access = 0) { return 403; }\n'
    lines = blog.splitlines(keepends=True)
    in_tls = False
    inserted = 0
    output = []
    for line in lines:
        if re.match(r'\s*listen\s+443\s+ssl', line):
            in_tls = True
        output.append(line)
        if in_tls and re.match(r'\s*server_name\s+', line):
            output.append(acl)
            inserted += 1
            in_tls = False
    if inserted != 2:
        raise ValueError('Expected two blog HTTPS vhosts; inspect instead of guessing')
    return app, geo + ''.join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-https', action='store_true', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run on ECS as root')
    original = {APP: APP.read_text(), BLOG: BLOG.read_text()}
    app, blog = candidate(original[APP], original[BLOG])
    changes = {APP: app, BLOG: blog}
    for path, value in changes.items():
        print(''.join(difflib.unified_diff(original[path].splitlines(True), value.splitlines(True), fromfile=str(path), tofile=str(path))), end='')
    print('UFW addition: allow IPv4 TCP 443 from 0.0.0.0/0. Ports 22, 80 and database remain unchanged.')
    if not args.apply:
        print('Preview only; nothing changed.')
        return
    # Fail before mutation if the original host rule assumptions have drifted.
    firewall = subprocess.run(['ufw', 'status'], capture_output=True, text=True, check=True).stdout
    validate_firewall(firewall)
    backup = Path('/root/remember-me-deploy') / ('network-before-public-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    for path, value in original.items():
        (backup/path.name).write_text(value)
    (backup/'ufw-before.txt').write_text(firewall)
    try:
        for path, value in changes.items():
            path.write_text(value)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
        subprocess.run(['ufw', 'allow', 'proto', 'tcp', 'from', '0.0.0.0/0', 'to', 'any', 'port', '443', 'comment', 'remember-me-account-gated-demo'], check=True)
    except Exception:
        for path, value in original.items():
            path.write_text(value)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
        raise
    (backup/'applied.json').write_text(json.dumps({'public_app_https':True,'blog_acl_preserved':True,'ssh_unchanged':True,'registration_unchanged':True}))
    print('Applied. Backup:', backup)
    print('Verify App from another network, blog denial, registration closed and authorization separately.')


if __name__ == '__main__':
    main()
