"""Inspect real PDF annotations (requires reportlab and pypdf)."""
from io import BytesIO
import unittest

from pypdf import PdfReader

from utils.pdf_generator import generate_pdf_from_cv_data


class ResumeHyperlinkTests(unittest.TestCase):
    def read_resume(self, **data):
        return PdfReader(BytesIO(generate_pdf_from_cv_data({'name': 'Jawad Akhtar', **data})))

    def uris(self, reader):
        links = []
        for page in reader.pages:
            for reference in page.get('/Annots', []):
                annotation = reference.get_object()
                self.assertEqual(annotation['/Subtype'], '/Link')
                self.assertEqual(annotation['/A']['/S'], '/URI')
                x1, y1, x2, y2 = annotation['/Rect']
                self.assertGreater(x2, x1)
                self.assertGreater(y2, y1)
                links.append(annotation['/A']['/URI'])
        return links

    def test_reported_contact_details_have_clickable_destinations(self):
        reader = self.read_resume(
            email='jawad00@yopmail.com',
            online_profiles={'linkedin': 'linkedin.com/in/jawad-akhtar-b710023a9',
                             'github': 'github.com/jd577'},
        )
        self.assertEqual(self.uris(reader), [
            'mailto:jawad00@yopmail.com',
            'https://linkedin.com/in/jawad-akhtar-b710023a9',
            'https://github.com/jd577',
        ])
        text = reader.pages[0].extract_text()
        self.assertIn('jawad00@yopmail.com', text)
        self.assertIn('linkedin.com/in/jawad-akhtar-b710023a9', text)
        self.assertIn('github.com/jd577', text)

    def test_profile_usernames_are_expanded(self):
        reader = self.read_resume(online_profiles={'LinkedIn': 'jawad', 'GitHub': 'jd577'})
        self.assertEqual(self.uris(reader), [
            'https://linkedin.com/in/jawad', 'https://github.com/jd577'])

    def test_absolute_and_protocol_relative_urls(self):
        for url, expected in [
            ('https://github.com/jd577', 'https://github.com/jd577'),
            ('http://example.com/me', 'http://example.com/me'),
            ('//example.com/me', 'https://example.com/me'),
            ('example.com/me', 'https://example.com/me'),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.uris(self.read_resume(online_profiles={'portfolio': url})), [expected])

    def test_special_characters_preserve_text_and_destinations(self):
        url = 'https://example.com/?a=1&b="two"'
        reader = self.read_resume(email='a&b@example.com', location='City <West> & East',
                                  online_profiles={'portfolio': url})
        self.assertEqual(self.uris(reader), ['mailto:a&b@example.com', url])
        self.assertIn('City <West> & East', reader.pages[0].extract_text())

    def test_empty_contacts_do_not_create_links(self):
        reader = self.read_resume(email=' ', online_profiles={'linkedin': None, 'github': ''})
        self.assertEqual(self.uris(reader), [])
        self.assertNotIn('None', reader.pages[0].extract_text())

    def test_wrapped_links_keep_their_destination(self):
        url = 'https://example.com/' + 'long-profile-name-' * 15
        links = self.uris(self.read_resume(online_profiles={'portfolio': url}))
        self.assertGreater(len(links), 1)
        self.assertEqual(set(links), {url})
