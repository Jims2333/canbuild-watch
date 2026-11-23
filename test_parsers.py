import unittest
from update_prices import parse_tracker, parse_retail, newegg_4070

class MonitorParserTests(unittest.TestCase):
    def test_tracker_price_with_real_shop_link(self):
        html='''<html><body><h1>RTX 5070 Ti</h1><p>CA$1,610</p><h2>Cheapest in stock now</h2><h2>Where to buy now</h2><ul><li>CA$1,610 MSI MLG Edition OC <a href="https://www.memoryexpress.com/Products/MX00135516">Memory Express</a> 4 hours ago</li><li>CA$1,899 GIGABYTE <a href="https://www.canadacomputers.com/en/product.html">Canada Computers</a></li></ul><h2>Price analysis</h2></body></html>'''
        rec=parse_tracker(html,'https://pctechvault.com/market-watch/geforce-rtx-5070-ti/?region=CA')
        self.assertEqual(rec['price'],1610.0)
        self.assertEqual(rec['shop'],'Memory Express')
        self.assertEqual(rec['stock'],'tracker_in_stock')
        self.assertIn('memoryexpress.com',rec['url'])

    def test_tracker_no_stock_fails_closed(self):
        html='<h1>RTX 5070 Ti</h1><h2>Price history</h2>CA$1200<h2>Where to buy now</h2><p>No shops currently selling</p>'
        with self.assertRaises(ValueError):
            parse_tracker(html,'https://pctechvault.com/foo')

    def test_canada_computers_bundle_not_component_price(self):
        html='''<h1>AMD Ryzen 7 9800X3D CPU + ASUS TUF B850-E + T-Force 32GB</h1>
        <div>$1,399.98</div><div>SAVE $349.99</div><h4>This pack contains</h4><p>Reg: $549.99</p><p>Available to Ship</p>'''
        rec=parse_retail(html,'Canada Computers','https://www.canadacomputers.com/abc')
        self.assertEqual(rec['price'],1399.98)
        self.assertEqual(rec['stock'],'in_stock')

    def test_memory_express_not_protection_price(self):
        html='''<h1>GeForce RTX 5070 Ti MLG EDITION OC 16GB</h1>
        <p>2 Year IPR plan - only $160.99</p><p>Only$1,609.99</p>
        <p>Online Store: Out of Stock</p>'''
        rec=parse_retail(html,'Memory Express','https://www.memoryexpress.com/Products/MX00135516')
        self.assertEqual(rec['price'],1609.99)
        self.assertEqual(rec['stock'],'out_of_stock')

    def test_newegg_new_orderable_cards(self):
        def card(title, price, button):
            return f'<div class="item-cell"><a class="item-title" href="https://www.newegg.ca/p/example">{title}</a><li class="price-current">$<strong>{price}</strong><sup>.99</sup> –</li><button>{button}</button></div>'
        html = ''.join([card('Refurbished RTX 4070 Ti SUPER','799','Add to cart'),
                        card('RTX 4070 Ti SUPER','999','Notify me'),
                        card('RTX 4070 Ti SUPER BTF','899','Add to cart'),
                        card('RTX 4070 Ti SUPER 16GB','1,399','Add to cart')])
        self.assertEqual(newegg_4070(html)['price'],1399.99)

    def test_modcom_requires_cad(self):
        html='<h1>Montech AIR 903 Base Black</h1><div>$75.69</div><script>Shopify.currency = {"active":"USD"};</script>'
        with self.assertRaisesRegex(ValueError, 'Canadian-dollar'):
            parse_retail(html,'Modcom','https://www.modcom.ca/products/test')

    def test_split_retail_price(self):
        html='<h1>MSI MLG Edition OC 16GB</h1><span>Only</span><span>$1,609.99</span><p>Online Store: Out of Stock</p>'
        self.assertEqual(parse_retail(html,'Memory Express','https://www.memoryexpress.com/Products/test')['price'],1609.99)

if __name__=='__main__':unittest.main()
