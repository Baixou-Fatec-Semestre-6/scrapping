import unittest

from parser.amazon_scraper import AmazonScraper, clean_amazon_url


class AmazonParserTest(unittest.TestCase):
    def test_normalizes_amazon_url(self):
        self.assertEqual(
            clean_amazon_url("https://amazon.com.br/gp/product/b09twdysvp?tag=x"),
            "https://www.amazon.com.br/dp/B09TWDYSVP",
        )

    def test_rejects_non_amazon_host(self):
        with self.assertRaises(ValueError):
            clean_amazon_url("https://amazon.com.br.evil.test/dp/B09TWDYSVP")

    def test_parses_product_and_brazilian_price(self):
        html = """
        <meta property="og:image" content="https://img.test/item.jpg">
        <span id="productTitle">Kindle</span>
        <span class="a-price"><span class="a-offscreen">R$ 1.234,56</span></span>
        """
        result = AmazonScraper()._parse_html(
            html, "https://www.amazon.com.br/dp/B09TWDYSVP", "BRL"
        )
        self.assertEqual(result["price"], 1234.56)
        self.assertEqual(result["image_url"], "https://img.test/item.jpg")

    def test_missing_price_is_parse_error(self):
        with self.assertRaisesRegex(Exception, "parse_error"):
            AmazonScraper()._parse_html(
                '<span id="productTitle">Produto</span>',
                "https://www.amazon.com.br/dp/B09TWDYSVP",
                "BRL",
            )

    def test_common_price_formats(self):
        scraper = AmazonScraper()
        for raw, expected in {
            "R$ 999,90": 999.90,
            "R$ 1.234,56": 1234.56,
            "$1,234.56": 1234.56,
            "R$ 1.234": 1234.0,
        }.items():
            with self.subTest(raw=raw):
                self.assertEqual(scraper._clean_and_parse_price(raw), expected)


if __name__ == "__main__":
    unittest.main()
