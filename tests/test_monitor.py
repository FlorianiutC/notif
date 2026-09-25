import unittest
from monitor import classify


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
