import unittest
from link_agent import canonical, relevant, product_title, update_record, run


class LinkTests(unittest.TestCase):
    def test_scope(self):
        self.assertTrue(relevant('Pokémon Coffret 30ᵉ Anniversaire Nymphali-ex'))
        self.assertFalse(relevant('Pokémon peluche 30 ans'))
        self.assertFalse(relevant('Pokémon Pack Zarude 2 boosters'))

    def test_menu_does_not_make_product_relevant(self):
        self.assertIsNone(product_title('<nav>Pokémon 30 ans coffret</nav><h1>Pack Zarude</h1>'))

    def test_json_product(self):
        html = '<script type="application/ld+json">{"@type":"Product","name":"Pokémon bundle 30e anniversaire"}</script>'
        self.assertEqual(product_title(html), 'Pokémon bundle 30e anniversaire')

    def test_external_link_rejected(self):
        self.assertIsNone(canonical('https://evil.test/p', 'https://shop.test/', 'shop.test'))
        self.assertIsNone(canonical('https://shop.test@evil.test/', 'https://shop.test/', 'shop.test'))

    def test_archive_requires_time_and_three_checks(self):
        record = {}
        update_record(record, 404, None, '2026-09-01T00:00:00+00:00', 'https://shop.test/p')
        update_record(record, 404, None, '2026-09-01T01:00:00+00:00', 'https://shop.test/p')
        update_record(record, 404, None, '2026-09-01T02:00:00+00:00', 'https://shop.test/p')
        self.assertEqual(record['status'], 'suspect')
        update_record(record, 410, None, '2026-09-03T00:00:00+00:00', 'https://shop.test/p')
        self.assertEqual(record['status'], 'archived')
        update_record(record, 200, 'Pokémon ETB 30 ans', '2026-09-04T00:00:00+00:00', 'https://shop.test/p')
        self.assertEqual(record['status'], 'valid')

    def test_block_does_not_delete(self):
        record = {'status': 'valid'}
        for status in (403, 429, 500, None, 200):
            update_record(record, status, None, '2026-09-03T00:00:00+00:00', 'https://shop.test/p')
            self.assertEqual(record['status'], 'unknown')
            self.assertEqual(record['dead_checks'], 0)

    def test_discovery_and_check(self):
        class FakeClient:
            remaining = 10
            def get(self, url):
                self.remaining -= 1
                body = '<a href="/p/1">Pokémon ETB 30 ans</a>' if url.endswith('/list') else '<h1>Pokémon ETB 30 ans</h1>'
                return 200, url, body
        site = {'id': 'shop', 'host': 'shop.test', 'seeds': ['https://shop.test/list'], 'product_path': '^/p/', 'listing_path': '^/list$'}
        db = {'products': {}}
        changes = run({'sites': [site], 'max_product_checks': 10}, db, FakeClient(), '2026-09-03T00:00:00+00:00')
        self.assertEqual(len(changes), 1)
        self.assertEqual(db['products']['https://shop.test/p/1']['status'], 'valid')
        self.assertFalse(db['products']['https://shop.test/p/1']['stock_local_verified'])
