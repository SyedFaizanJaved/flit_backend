"""Turn `/extract_company_profile` output into values the employer wizard can drop into its fields.

Pure functions, no I/O -- the same shape as candidates/resume_mapper.py, and for the same
reason: every failure here is silent. A scraped industry that is not one of the nine the
dropdown offers renders as an empty select the employer never notices, not as an error.

Output keys are the *frontend form's* names (`companyName`, `foundedYear`, `perks`), not
the model's, because the wizard is the consumer. Keys are omitted entirely when there is
no value, so the caller's "only fill what is empty" rule stays a simple presence check.

`location` comes back as the one string the scrape produced ("Irving, TX, USA"). The form
holds ISO country/state codes, and turning names into codes needs the geo dataset the
frontend already ships (`country-state-city`) -- doing it here would mean a new backend
dependency to produce something the consumer can derive itself.
"""

import re
from datetime import date, datetime

from dateutil import parser as dateutil_parser

# Mirrors the INDUSTRY dropdown in pages/employer/create-profile.tsx.
INDUSTRY_CHOICES = {
    'technology': 'Technology', 'design agency': 'Design Agency', 'marketing': 'Marketing',
    'finance': 'Finance', 'healthcare': 'Healthcare', 'education': 'Education',
    'e-commerce': 'E-commerce', 'manufacturing': 'Manufacturing', 'non-profit': 'Non-profit',
}

# A scrape emits whatever the website says. Normalising here rather than relying on the ML
# service means a new phrasing is a one-line addition, not a bug report.
INDUSTRY_SYNONYMS = {
    'it': 'Technology', 'ai': 'Technology', 'tech': 'Technology', 'saas': 'Technology',
    'software': 'Technology', 'software development': 'Technology',
    'software house': 'Technology', 'information technology': 'Technology',
    'artificial intelligence': 'Technology', 'computer software': 'Technology',
    'it services': 'Technology',
    'design': 'Design Agency', 'creative agency': 'Design Agency', 'ux': 'Design Agency',
    'advertising': 'Marketing', 'digital marketing': 'Marketing', 'pr': 'Marketing',
    'fintech': 'Finance', 'banking': 'Finance', 'insurance': 'Finance',
    'financial services': 'Finance',
    'health': 'Healthcare', 'medical': 'Healthcare', 'pharmaceutical': 'Healthcare',
    'pharma': 'Healthcare', 'biotech': 'Healthcare',
    'edtech': 'Education', 'e-learning': 'Education', 'training': 'Education',
    'ecommerce': 'E-commerce', 'e commerce': 'E-commerce', 'retail': 'E-commerce',
    'marketplace': 'E-commerce',
    'industrial': 'Manufacturing', 'engineering': 'Manufacturing',
    'automotive': 'Manufacturing',
    'nonprofit': 'Non-profit', 'non profit': 'Non-profit', 'ngo': 'Non-profit',
    'charity': 'Non-profit',
}

# Company.SIZE_CHOICES as (upper bound, label). The last bucket absorbs everything above
# it, because the model has no larger choice -- a 5000-person company still has to pick one.
SIZE_BUCKETS = [(10, '1-10'), (50, '11-50'), (200, '51-200'), (500, '201-500'),
                (None, '501-1000')]
SIZE_CHOICES = {label for _, label in SIZE_BUCKETS}

WORK_MODE_CHOICES = {'remote', 'hybrid', 'onsite'}
WORK_MODE_SYNONYMS = {
    'on-site': 'onsite', 'on site': 'onsite', 'office': 'onsite', 'in-office': 'onsite',
    'in office': 'onsite', 'work from office': 'onsite',
    'work from home': 'remote', 'wfh': 'remote', 'distributed': 'remote',
    'fully remote': 'remote', 'remote-first': 'remote',
    'flexible': 'hybrid', 'mixed': 'hybrid',
}

# Values of the PLATFORM select in the wizard's Gallery step. Scrapes key social links by
# display name ('Twitter', 'X'), so match case-insensitively and fold the aliases.
SOCIAL_PLATFORMS = {'linkedin', 'twitter', 'instagram', 'facebook', 'youtube', 'github'}
SOCIAL_SYNONYMS = {
    'x': 'twitter', 'x / twitter': 'twitter', 'x (twitter)': 'twitter',
    'fb': 'facebook', 'yt': 'youtube', 'linked in': 'linkedin', 'linkedin.com': 'linkedin',
}

# Frontend validation limits, not display ones: handing back a longer value prefills a
# field that then refuses to submit, which reads as a broken form rather than a long name.
MAX_NAME = 100
MAX_DESCRIPTION = 2000
MAX_URL = 500
MAX_LOCATION = 500
MAX_TAG = 50
MAX_TAGS = 20
MAX_MILESTONES = 20
MAX_MILESTONE_TITLE = 80
MAX_MILESTONE_DESC = 500
MIN_YEAR = 1800

# Tag lists arrive as either a real list or one blob of prose. These are the separators a
# scraped "benefits" paragraph actually uses.
_TAG_SPLIT = re.compile(r'[\n;,•·|]+')


def _text(value, limit=MAX_NAME):
    """Non-empty stripped string truncated to `limit`, or None.

    Pass limit=None for targets with no ceiling.
    """
    if value is None:
        return None
    text = str(value).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip()
    return text or None


def _tags(value):
    """`values` / `culture` / `benefits` -> the chip lists the Details step renders.

    The endpoint returns a list for `values` and a prose string for `culture`/`benefits`,
    so both are handled: one blob becomes the chips it was always a comma-separated
    version of. A list is only re-split per entry, so a value that itself contains a
    comma survives intact.
    """
    items = value if isinstance(value, list) else _TAG_SPLIT.split(str(value or ''))
    tags = []
    for item in items:
        tag = _text(item, MAX_TAG)
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:MAX_TAGS]


def _date(value):
    """Any year-ish value -> the 'YYYY-MM-DD' the wizard's date picker holds, or None.

    `founded_year` comes back in whatever shape the site printed it: a full date, a month
    and year, a bare year, or a sentence containing one. Whatever precision is present is
    kept and the rest defaults to January 1st -- 'June 2015' prefills as 2015-06-01
    instead of throwing the month away.

    Years outside 1800..this year are dropped rather than passed on: the form rejects
    them, so prefilling one hands the employer an error they did not make.
    """
    text = _text(value, None)
    if not text:
        return None
    match = re.search(r'\b(1[89]\d{2}|20\d{2})\b', text)
    if not match:
        return None
    year = int(match.group(1))
    if year < MIN_YEAR or year > date.today().year:
        return None

    # dateutil is already a pinned dependency and already reads every form a site might
    # print -- '2015-06-12', '2015-06', 'June 2015', '12 June 2015', 'June 12, 2015',
    # '06/2015'. `default` supplies whatever the text omits; `fuzzy` lets it ignore the
    # prose around the date. Ambiguous all-numeric forms like 06/07/2015 are read
    # month-first, which is dateutil's default.
    year_only = date(year, 1, 1).isoformat()
    try:
        parsed = dateutil_parser.parse(
            text, default=datetime(year, 1, 1), fuzzy=True
        ).date()
    except (ValueError, OverflowError):
        return year_only

    # The regex year is the one that passed the range check above. If the parse drifted
    # to a different year, or produced a date that has not happened yet, keep the safe
    # value rather than prefilling something the form will reject.
    if parsed.year != year or parsed > date.today():
        return year_only
    return parsed.isoformat()


def _industry(value):
    text = _text(value, MAX_NAME)
    if not text:
        return None
    key = text.lower()
    return INDUSTRY_CHOICES.get(key) or INDUSTRY_SYNONYMS.get(key)


def _size(value):
    """Headcount in any shape -> one of Company.SIZE_CHOICES, or None.

    '51-200' passes through; '250 employees', '10,000+' and 250 get bucketed. The largest
    number wins, so a range picks its upper bound and lands in the same bucket the
    employer would have chosen.
    """
    text = _text(value, MAX_TAG)
    if not text:
        return None
    if text in SIZE_CHOICES:
        return text
    numbers = [int(n.replace(',', '')) for n in re.findall(r'\d[\d,]*', text)]
    if not numbers:
        return None
    count = max(numbers)
    for upper, label in SIZE_BUCKETS:
        if upper is None or count <= upper:
            return label


def _work_mode(value):
    text = _text(value, MAX_TAG)
    if not text:
        return None
    key = text.lower()
    return key if key in WORK_MODE_CHOICES else WORK_MODE_SYNONYMS.get(key)


def _social(value):
    """{'LinkedIn': 'url'} or [{'platform': ..., 'url': ...}] -> the wizard's link rows.

    Platforms outside the select are dropped: the row would render with a blank platform
    label and could not be re-saved.
    """
    if isinstance(value, dict):
        pairs = list(value.items())
    elif isinstance(value, list):
        pairs = [
            (entry.get('platform') or entry.get('name'), entry.get('url'))
            for entry in value if isinstance(entry, dict)
        ]
    else:
        return []

    links, seen = [], set()
    for platform, url in pairs:
        name = _text(platform, MAX_TAG)
        address = _text(url, MAX_URL)
        if not (name and address):
            continue
        key = name.lower()
        key = key if key in SOCIAL_PLATFORMS else SOCIAL_SYNONYMS.get(key)
        if not key or key in seen:
            continue
        seen.add(key)
        links.append({'platform': key, 'url': address})
    return links


def _milestones(entries):
    """History rows -> the Milestones step.

    Both title and date are required by the step's own form, so an entry missing either
    is dropped rather than seeded as a row the employer cannot submit.
    """
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get('title'), MAX_MILESTONE_TITLE)
        year = _date(entry.get('year') or entry.get('date'))
        if not (title and year):
            continue
        out.append({
            'title': title,
            'year': year,
            'description': _text(entry.get('description'), MAX_MILESTONE_DESC) or '',
        })
    return out[:MAX_MILESTONES]


def to_form_values(company_data):
    """Map extracted company data to employer-wizard field values.

    Absent keys mean "nothing found" -- callers fill only fields the employer has left
    empty, so an omitted key and an empty string are meaningfully different.
    """
    data = company_data if isinstance(company_data, dict) else {}
    values = {}

    def put(key, value):
        if value:
            values[key] = value

    put('companyName', _text(data.get('company_name'), MAX_NAME))
    put('description', _text(data.get('description'), MAX_DESCRIPTION))
    put('industry', _industry(data.get('industry')))
    put('size', _size(data.get('size')))
    put('website', _text(data.get('website'), MAX_URL))
    put('logo', _text(data.get('logo'), MAX_URL))
    put('location', _text(data.get('location'), MAX_LOCATION))
    put('foundedYear', _date(data.get('founded_year')))
    put('values', _tags(data.get('values')))
    put('culture', _tags(data.get('culture')))
    put('perks', _tags(data.get('benefits')))
    put('workMode', _work_mode(data.get('work_mode')))
    put('socialLinks', _social(data.get('social_links')))
    put('milestones', _milestones(data.get('milestones')))
    return values


def demo():
    """Self-check over the parts that fail silently: enums, caps, and the null-heavy payload."""
    # The reference response, nulls and all -- this is what the endpoint actually returns.
    v = to_form_values({
        'company_name': 'Nextbridge',
        'description': 'Nextbridge is an IT company specializing in software and AI.',
        'industry': 'Technology', 'size': None, 'website': 'https://nextbridge.com',
        'logo': 'https://nextbridge.com/wp-content/uploads/2025/07/favicon.ico',
        'location': 'Irving, TX, USA',
        'values': ['Change the Future', 'Save Time, Lead the World',
                   'Commitment to excellence'],
        'culture': None, 'benefits': None, 'founded_year': '1993-01-01', 'work_mode': None,
        'social_links': {'Facebook': 'https://www.facebook.com/Nextbridge.pk',
                         'Instagram': 'https://www.instagram.com/nextbridgelife/',
                         'Twitter': 'https://twitter.com/Nextbridge_pk',
                         'LinkedIn': 'https://www.linkedin.com/company/nextbridge/'},
        'milestones': [{'year': '1993-01-01', 'title': 'Company Founded',
                        'description': 'NEXTBRIDGE was founded...'}],
    })
    assert v['companyName'] == 'Nextbridge'
    assert v['industry'] == 'Technology'
    assert v['foundedYear'] == '1993-01-01'
    assert v['location'] == 'Irving, TX, USA'
    # A value containing a comma must survive: the list is already split, so it is not
    # re-split on its own punctuation.
    assert v['values'] == ['Change the Future', 'Save Time, Lead the World',
                           'Commitment to excellence'], v['values']
    assert [l['platform'] for l in v['socialLinks']] == \
        ['facebook', 'instagram', 'twitter', 'linkedin']
    assert v['milestones'][0] == {'year': '1993-01-01', 'title': 'Company Founded',
                                  'description': 'NEXTBRIDGE was founded...'}
    # Nulls must be absent, not empty -- the caller fills only what it finds.
    for absent in ('size', 'culture', 'perks', 'workMode'):
        assert absent not in v, absent

    # Headcount arrives in every shape a website writes it in.
    sizes = ['1-10', '7', '35 people', '51-200', '250 employees', '10,000+', 'a few', None]
    assert [to_form_values({'size': s}).get('size') for s in sizes] == \
        ['1-10', '1-10', '11-50', '51-200', '201-500', '501-1000', None, None]

    # Invalid enums blank the field, never pass through.
    assert 'industry' not in to_form_values({'industry': 'Interdimensional Logistics'})
    assert to_form_values({'industry': 'Software Development'})['industry'] == 'Technology'
    assert 'workMode' not in to_form_values({'work_mode': 'whenever'})
    assert to_form_values({'work_mode': 'On-Site'})['workMode'] == 'onsite'

    # Every shape a website prints a founding date in. Whatever precision is there is
    # kept; what is missing defaults to January 1st.
    founded = {
        '2015-06-12': '2015-06-12',           # full ISO date
        'Founded on 2015-06-12': '2015-06-12',  # ... inside a sentence
        '12 June 2015': '2015-06-12',         # day month year
        'June 12, 2015': '2015-06-12',        # month day year
        '12/06/2015': '2015-12-06',           # all-numeric, read month-first
        'June 2015': '2015-06-01',            # month and year
        'Jun 2015': '2015-06-01',             # abbreviated month
        '06/2015': '2015-06-01',              # numeric month and year
        '2015-06': '2015-06-01',              # ISO year-month
        '2015': '2015-01-01',                 # bare year
        'Founded in 2011': '2011-01-01',      # year inside prose
        'Established March 1993': '1993-03-01',
    }
    for raw, expected in founded.items():
        got = to_form_values({'founded_year': raw}).get('foundedYear')
        assert got == expected, '%r -> %r, expected %r' % (raw, got, expected)

    # Years the form itself rejects must not be prefilled.
    assert 'foundedYear' not in to_form_values({'founded_year': '1650'})
    assert 'foundedYear' not in to_form_values({'founded_year': '2099-01-01'})
    assert 'foundedYear' not in to_form_values({'founded_year': 'established recently'})

    # Prose culture/benefits become the chips the step renders; each chip is capped.
    prose = to_form_values({'culture': 'Ownership, Transparency\nRemote-friendly',
                            'benefits': 'Health insurance; Paid leave; ' + 'X' * 80})
    assert prose['culture'] == ['Ownership', 'Transparency', 'Remote-friendly'], prose['culture']
    assert len(prose['perks'][2]) == MAX_TAG

    # Milestones without a title or a usable date cannot be submitted, so they are dropped.
    assert to_form_values({'milestones': [
        {'title': 'No date'}, {'year': '2010-01-01'},
        {'title': 'Series A', 'year': '2010'},
    ]})['milestones'] == [{'title': 'Series A', 'year': '2010-01-01', 'description': ''}]

    # Unknown platforms would render a blank select; duplicates would render twice.
    assert to_form_values({'social_links': {
        'X': 'https://x.com/a', 'Twitter': 'https://twitter.com/a',
        'Threads': 'https://threads.net/a', 'GitHub': 'https://github.com/a',
    }})['socialLinks'] == [{'platform': 'twitter', 'url': 'https://x.com/a'},
                           {'platform': 'github', 'url': 'https://github.com/a'}]

    # Every capped target: a scraped page can exceed all of them.
    long = 'X' * 3000
    over = to_form_values({'company_name': long, 'description': long, 'location': long,
                           'milestones': [{'title': long, 'year': '2010',
                                           'description': long}]})
    assert len(over['companyName']) == MAX_NAME
    assert len(over['description']) == MAX_DESCRIPTION
    assert len(over['location']) == MAX_LOCATION
    assert len(over['milestones'][0]['title']) == MAX_MILESTONE_TITLE
    assert len(over['milestones'][0]['description']) == MAX_MILESTONE_DESC

    assert to_form_values(None) == {} and to_form_values({}) == {}
    print('company_mapper OK')


if __name__ == '__main__':
    demo()
