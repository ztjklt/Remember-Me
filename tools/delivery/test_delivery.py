"""Deterministic guards for the narrowly scoped ECS network migration."""
import unittest
from configure_ecs_access import candidate, validate_firewall


class NetworkChangeTest(unittest.TestCase):
    APP = ('server {\n    listen 443 ssl http2 default_server;\n'
           '    server_name 39.108.183.47;\n'
           '    allow 183.6.9.111;\n    allow 127.0.0.1;\n    deny all;\n'
           '    ssl_certificate /demo.crt;\n    location / { proxy_pass http://127.0.0.1:8877; }\n}\n')
    BLOG = ('server {\n listen 80;\n server_name skyspace.cloud;\n}\n'
            'server {\n listen 443 ssl http2;\n server_name www.skyspace.cloud;\n'
            ' return 301 https://skyspace.cloud$request_uri;\n}\n'
            'server {\n listen 443 ssl http2;\n server_name skyspace.cloud;\n'
            ' ssl_certificate /blog.crt;\n root /var/www/blog;\n}\n')

    def test_only_app_acl_removed_blog_redirect_guarded(self):
        app, blog = candidate(self.APP, self.BLOG)
        self.assertNotIn('deny all', app)
        self.assertIn('ssl_certificate /demo.crt', app)
        self.assertIn('proxy_pass http://127.0.0.1:8877', app)
        self.assertIn('ssl_certificate /blog.crt', blog)
        self.assertEqual(blog.count('if ($remember_team_blog_access = 0)'), 2)
        self.assertLess(blog.index('if ($remember_team_blog_access = 0)'), blog.index('return 301'))
        self.assertIn('default 0;', blog)

    def test_unexpected_vhost_or_acl_rejected(self):
        for app in (self.APP.replace('39.108.183.47', 'example.org'), self.APP.replace('183.6.9.111', '1.2.3.4')):
            with self.assertRaises(ValueError):
                candidate(app, self.BLOG)
        with self.assertRaises(ValueError):
            candidate(self.APP, self.BLOG.replace('listen 443', 'listen 8443'))

    def test_firewall_drift_not_silently_widened(self):
        rules = '443/tcp ALLOW 120.236.174.183\n443/tcp ALLOW 183.6.9.111\n22/tcp ALLOW 100.104.0.0/16\n'
        validate_firewall(rules)
        for altered in (rules.replace('443/tcp ALLOW 183.6.9.111', '80/tcp ALLOW 183.6.9.111'), rules+'443/tcp ALLOW 1.2.3.4\n', rules+'443/tcp ALLOW Anywhere\n'):
            with self.assertRaises(RuntimeError):
                validate_firewall(altered)


if __name__ == '__main__':
    unittest.main()
