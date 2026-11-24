import unittest

from build_catalog import parse_category, specs, tier_of


class CatalogueParserTests(unittest.TestCase):
    def test_extracts_product_cards_and_marks_best_same_family_value(self):
        html = '''
        <html><body>
          <article><a href="/en/powered-by-amd/300001/gigabyte-radeon-rx-9070-xt.html" title="GIGABYTE Radeon RX 9070 XT 16GB GDDR6">GIGABYTE Radeon RX 9070 XT 16GB GDDR6</a><div>$1,349.99</div><button>Add to cart</button></article>
          <article><a href="/en/powered-by-amd/300002/asus-radeon-rx-9070-xt.html" title="ASUS Radeon RX 9070 XT 16GB GDDR6">ASUS Radeon RX 9070 XT 16GB GDDR6</a><div>$1,539.99</div><button>Add to cart</button></article>
        </body></html>'''
        parts = parse_category(html, "GPU", "https://www.canadacomputers.com/en/914/graphics-cards?page=1")
        self.assertEqual(len(parts), 2)
        cheaper = parts["cc_gpu_300001"]
        self.assertEqual(cheaper["spec"], ["AMD", 16, "9070 XT"])
        self.assertEqual(cheaper["tier"], "high")
        self.assertTrue(cheaper["value"])
        self.assertFalse(parts["cc_gpu_300002"]["value"])

    def test_storage_and_power_tiers_use_specs(self):
        ssd = specs("SSD", "Samsung 9100 PRO 4TB PCIe Gen5 NVMe SSD")
        psu = specs("PSU", "Corsair RM1000x 1000W 80 Plus Gold")
        self.assertEqual(ssd, [4.0, "Gen5"])
        self.assertEqual(psu, [1000, "Gold"])
        self.assertEqual(tier_of("SSD", "Samsung", ssd, 500), "high")
        self.assertEqual(tier_of("PSU", "Corsair", psu, 200), "high")


if __name__ == "__main__":
    unittest.main()
