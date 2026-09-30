import unittest
from unittest.mock import patch
from monitor import classify, observe, notify


class StockTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "product": "ETB 30e Anniversaire", "store": "Lomme",
            "product_selector": "h1", "scope_selector": "#local", "stock_selector": ".stock",
            "labels": {"available": ["Disponible"], "unavailable": ["Indisponible"], "preorder": ["Précommande"]},
        }

    def page(self, label, store="Lomme"):
        return f'<h1>ETB 30e Anniversaire</h1><p>En stock en ligne</p><div id="local">{store}<span class="stock">{label}</span></div>'

    def test_local_out_of_stock_beats_online_stock(self):
        self.assertEqual(classify(self.page("Indisponible"), self.source)[0], "unavailable")

    def test_wrong_store_is_unknown(self):
        self.assertEqual(classify(self.page("Disponible", "Paris"), self.source)[0], "unknown")

    def test_unknown_label_does_not_alert(self):
        self.assertEqual(classify(self.page("Disponible sous 15 jours"), self.source)[0], "unknown")

    def test_product_redirect_is_unknown(self):
        self.assertEqual(classify('<h1>Cartes Pokémon</h1>', self.source)[0], "unknown")

    def test_confirmed_local_stock(self):
        self.assertEqual(classify(self.page("Disponible"), self.source)[0], "available")

    def test_ambiguous_stock(self):
        self.assertEqual(classify(self.page("Disponible").replace('</div>', '<span class="stock">Indisponible</span></div>'), self.source)[0], "unknown")

    @patch('monitor.notify')
    def test_new_stock_alerts_once_and_restock_alerts_again(self, push):
        self.source['url'] = 'https://example.org/product'
        current, _, _ = observe(self.source, self.page('Disponible'), {})
        observe(self.source, self.page('Disponible'), current)
        self.assertEqual(push.call_count, 1)
        unavailable, _, _ = observe(self.source, self.page('Indisponible'), current)
        observe(self.source, self.page('Disponible'), unavailable)
        self.assertEqual(push.call_count, 2)

    @patch('monitor.notify')
    def test_unknown_and_preorder_do_not_alert(self, push):
        self.source['url'] = 'https://example.org/product'
        previous = {'status': 'available'}
        current, status, _ = observe(self.source, '<h1>Erreur réseau</h1>', previous)
        self.assertEqual(current, previous)
        self.assertEqual(status, 'unknown')
        observe(self.source, self.page('Précommande'), previous)
        push.assert_not_called()

    @patch('monitor.notify')
    def test_price_change_alerts_only_when_available(self, push):
        self.source.update(url='https://example.org/product', price_selector='.price')
        def page(price, status='Disponible'):
            return self.page(status).replace('</div>', f'<span class="price">{price}</span></div>')
        current, _, _ = observe(self.source, page('29,99 €'), {})
        current, _, _ = observe(self.source, page('24,99 €'), current)
        current, _, _ = observe(self.source, page('24,99 €'), current)
        observe(self.source, page('19,99 €', 'Indisponible'), current)
        self.assertEqual(push.call_count, 2)

    @patch('monitor.notify', side_effect=OSError('Service unavailable'))
    def test_failed_push_leaves_previous_state_untouched(self, push):
        self.source['url'] = 'https://example.org/product'
        previous = {'status': 'unavailable'}
        with self.assertRaises(OSError):
            observe(self.source, self.page('Disponible'), previous)
        self.assertEqual(previous, {'status': 'unavailable'})

    @patch.dict('os.environ', {'NTFY_TOPIC': 'test-' + 'a' * 32})
    @patch('monitor.urlopen')
    def test_demo_push_is_explicitly_fake(self, send):
        import json
        notify({'product': 'Coffret de test', 'store': 'Magasin fictif', 'url': 'https://example.org/'}, test=True)
        payload = json.loads(send.call_args.args[0].data)
        self.assertIn('TEST', payload['title'])
        self.assertIn('STOCK FICTIF', payload['message'])
