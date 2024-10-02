from unittest import TestCase

from conjure import ImageComponent, AudioComponent, CitationComponent, CompositeComponent


class TestArticle(TestCase):
    """
    Currently just smoke tests.  More specific assertions need to be added
    """

    def test_can_render_html_for_image(self):
        c = ImageComponent('https://example.org', 200)
        result = c.render('html')
        self.assertIsNotNone(result)

    def test_can_render_markdown_for_image(self):
        c = ImageComponent('https://example.org', 200)
        result = c.render('markdown')
        self.assertIsNotNone(result)

    def test_can_render_html_for_sound(self):
        c = AudioComponent('https://example.org', 200)
        result = c.render('html')
        self.assertIsNotNone(result)

    def test_can_render_markdown_for_sound(self):
        c = AudioComponent('https://example.org', 200)
        result = c.render('markdown')
        self.assertIsNotNone(result)

    def test_can_render_html_for_citation(self):
        c = CitationComponent(
            'https://example.org',
            'Hal',
            'https://example.org',
            'Title',
            '2024')
        result = c.render('html')
        self.assertIsNotNone(result)

    def test_can_render_markdown_for_citation(self):
        c = CitationComponent(
            'https://example.org',
            'Hal',
            'https://example.org',
            'Title',
            '2024')
        result = c.render('markdown')
        self.assertIsNotNone(result)

    def test_can_render_html_for_composite_component(self):
        c = ImageComponent('https://example.org', 200)
        c2 = AudioComponent('https://example.org', 200)
        comp = CompositeComponent(
            title='# Here is a title component',
            image=c,
            audio=c2
        )

        result = comp.render('html')
        self.assertIsNotNone(result)

    def test_can_render_markdown_for_composite_component(self):
        c = ImageComponent('https://example.org', 200)
        c2 = AudioComponent('https://example.org', 200)
        comp = CompositeComponent(
            title='# Here is a title component',
            image=c,
            audio=c2
        )

        result = comp.render('html')
        self.assertIsNotNone(result)
