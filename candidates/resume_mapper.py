"""Turn `/extract_resume` output into values the profile wizard can drop into its fields.

Pure functions, no I/O -- this is the one part of CV prefill worth testing on its own,
because every failure here is silent: a mismatched enum shows up as an empty dropdown
the candidate never notices, not as an error.

Two response shapes are handled. `/extract_resume` returns the structured shape, with
discrete fields per experience/education/achievement. The older `/parse_cv` returns prose
blobs instead; 78 candidates already have that stored in `Candidate.resume_data`, so it is
still mapped for whatever it can yield rather than leaving those rows with nothing.

Output keys are the *frontend form's* names (`institute`, `degreeName`, `isStillGoing`),
not the model's, because the wizard is the consumer. Keys are omitted entirely when there
is no value, so the caller's "only fill what is empty" rule stays a simple presence check.
"""

import re

from utils.location import location_text

# Mirrors Education.DEGREE_CHOICES / DEGREE_LEVELS in the frontend.
DEGREE_CHOICES = {
    'high_school', 'associate', 'bachelor', 'master', 'phd', 'certificate', 'diploma',
}

# The parser emits whatever the CV says. Normalising here rather than relying on the ML
# service means a new abbreviation is a one-line addition, not a bug report.
DEGREE_SYNONYMS = {
    'bs': 'bachelor', 'bsc': 'bachelor', 'b.s.': 'bachelor', 'b.sc': 'bachelor',
    'ba': 'bachelor', 'b.a.': 'bachelor', 'be': 'bachelor', 'btech': 'bachelor',
    'b.tech': 'bachelor', 'bscs': 'bachelor', 'bachelors': 'bachelor',
    "bachelor's": 'bachelor', 'undergraduate': 'bachelor',
    'ms': 'master', 'msc': 'master', 'm.s.': 'master', 'm.sc': 'master',
    'ma': 'master', 'mba': 'master', 'mtech': 'master', 'mphil': 'master',
    'masters': 'master', "master's": 'master', 'postgraduate': 'master',
    'doctorate': 'phd', 'dphil': 'phd', 'ph.d': 'phd', 'ph.d.': 'phd',
    # Upper-secondary qualifications with no separate slot in DEGREE_CHOICES.
    # Pakistani Intermediate/FSc and A-levels are 11th-12th grade, so high_school is
    # the honest bucket -- dropping the row would delete real history the candidate
    # would then have to retype.
    'intermediate': 'high_school', 'fsc': 'high_school', 'f.sc': 'high_school',
    'fa': 'high_school', 'ics': 'high_school', 'icom': 'high_school',
    'a-level': 'high_school', 'a levels': 'high_school', 'a-levels': 'high_school',
    'hssc': 'high_school', 'matric': 'high_school', 'ssc': 'high_school',
    'o-level': 'high_school', 'o levels': 'high_school',
    'associates': 'associate', 'certification': 'certificate',
}

EMPLOYMENT_TYPE_CHOICES = {
    'full-time', 'part-time', 'contract', 'freelance', 'internship',
}
GRADING_SYSTEM_CHOICES = {'gpa', 'gpr', 'grade', 'marks'}
GRADE_CHOICES = {'A', 'B', 'C', 'D', 'E', 'F'}
ACHIEVEMENT_TYPE_CHOICES = {'award', 'certification', 'project', 'publication', 'other'}
SENIORITY_CHOICES = {'junior', 'beginner', 'intermediate', 'mid', 'senior'}

# MAX_SKILLS_COUNT in the frontend. All parsed skills are returned so the candidate can
# curate; only this many start selected.
MAX_SELECTED_SKILLS = 12


# Longest a mapped value may be before it overflows its column. A CV is free text
# written by anyone, so every CharField this module feeds needs a ceiling -- an
# unbounded institution name or job title fails the INSERT the same way a two-character
# grade did, just less often and further from the cause.
MAX_CHARFIELD = 200


# `/extract_resume` returns the candidate's photo cropped out of the CV as a data URI
# under `metadata.extracted_profile_image`. It is offered as the profile picture, so it
# is held to the same types the profile-image upload accepts (ALLOWED_IMAGE_TYPES in the
# frontend) -- a data URI naming anything else would be rejected at save time anyway.
PROFILE_IMAGE_TYPES = {'png', 'jpeg', 'jpg', 'webp'}

# Ceiling on the whole data URI string. A face crop is tens of KB; this is generous
# enough to never reject a real one, and small enough that a runaway payload cannot
# bloat the parse response or the browser holding it.
MAX_PROFILE_IMAGE_CHARS = 5_000_000

_DATA_URI = re.compile(r'^data:image/([a-z0-9.+-]+);base64,(.+)$', re.IGNORECASE | re.DOTALL)


def profile_image_from_metadata(metadata):
    """The CV's extracted photo as a data URI, or None.

    Never raises and never returns something the profile-image upload would reject:
    the caller hands this straight to the client to preview and re-upload, so a
    malformed or oversized value has to become "no photo found", not a broken <img>
    or a failed save two steps later.
    """
    value = (metadata or {}).get('extracted_profile_image') if isinstance(metadata, dict) else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > MAX_PROFILE_IMAGE_CHARS:
        return None
    match = _DATA_URI.match(value)
    if not match or match.group(1).lower() not in PROFILE_IMAGE_TYPES:
        return None
    return value


def _text(value, limit=MAX_CHARFIELD):
    """Non-empty stripped string truncated to `limit`, or None.

    Pass limit=None for TextField targets (bio, descriptions), which have no ceiling.
    """
    if value is None:
        return None
    text = str(value).strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip()
    return text or None


def _choice(value, allowed, synonyms=None):
    """Normalise to a member of `allowed`, or None. Never returns an invalid value.

    An invalid enum must become an empty field the candidate is asked to fill, not a
    value that fails validation on save or renders as a blank-but-set dropdown.
    """
    text = _text(value)
    if not text:
        return None
    key = text.lower()
    # Choice lists here are lowercase except GRADE_CHOICES, which is A-F. Try the value
    # as written, then both case foldings, so 'b' still matches the grade 'B'.
    for form in (text, key, text.upper()):
        if form in allowed:
            return form
    if synonyms and key in synonyms:
        return synonyms[key]
    return None


def _num(value):
    """Numbers arrive as ints/floats but the form's inputs are text."""
    if value is None or value == '':
        return None
    return str(value)


def _is_structured(data):
    """Structured responses carry per-entry fields; prose ones carry `description`."""
    for key in ('experience', 'experiences'):
        entries = data.get(key)
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            return 'company_name' in entries[0] or 'position' in entries[0]
    return bool(data.get('title') or data.get('portfolio_links'))


def _map_experience(entries):
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        company = _text(entry.get('company_name'))
        position = _text(entry.get('position'))
        if not (company or position):
            continue

        employment_type = _choice(entry.get('employment_type'), EMPLOYMENT_TYPE_CHOICES)
        mapped = {
            'company_name': company or '',
            'position': position or '',
            # Left blank on purpose when the CV does not say. Guessing 'full-time' is
            # wrong for contractors and freelancers, and a wrong prefilled value gets
            # scrolled past where an empty required field does not.
            'employment_type': employment_type or '',
            'location': location_text(entry.get('location'), MAX_CHARFIELD) or '',
            'startDate': _text(entry.get('start_date')) or '',
            'endDate': _text(entry.get('end_date')) or '',
            'isCurrent': bool(entry.get('is_current')),
            'description': _text(entry.get('description'), None) or '',
            'achievements': [a for a in (entry.get('achievements') or []) if _text(a)],
            'skills_used': [s for s in (entry.get('skills_used') or []) if _text(s)],
        }
        mapped['needs_review'] = [] if employment_type else ['employment_type']
        out.append(mapped)
    return out


def _map_education(entries):
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        institute = _text(entry.get('institution'))
        if not institute:
            continue

        degree = _choice(entry.get('degree'), DEGREE_CHOICES, DEGREE_SYNONYMS)
        mapped = {
            'institute': institute,
            'degree': degree or '',
            'degreeName': _text(entry.get('field_of_study')) or '',
            'startDate': _text(entry.get('start_date')) or '',
            'endDate': _text(entry.get('end_date')) or '',
            'isStillGoing': bool(entry.get('is_current')),
            'gradingSystem': _choice(entry.get('grading_system'), GRADING_SYSTEM_CHOICES) or '',
            'gpa': _num(entry.get('gpa')) or '',
            # varchar(1) with an A-F choice list: anything else ('A+', 'First Class',
            # a stray GPA) both fails the choices check and overflows the column.
            'grade': _choice(entry.get('grade'), GRADE_CHOICES) or '',
            'totalMarks': _num(entry.get('total_marks')) or '',
            'obtainedMarks': _num(entry.get('obtained_marks')) or '',
            'description': _text(entry.get('description'), None) or '',
        }
        mapped['needs_review'] = [] if degree else ['degree']
        out.append(mapped)
    return out


def _map_achievements(entries):
    """Certifications, awards and publications -> the Achievements tab.

    Achievement.date_achieved is required with no default, so an entry without a date
    cannot be saved and is dropped rather than seeded as a row the candidate cannot
    submit. Unlike `degree`, there is no sensible blank-and-flag here.
    """
    out = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        title = _text(entry.get('title'))
        date_achieved = _text(entry.get('date_achieved'))
        if not (title and date_achieved):
            continue
        out.append({
            'title': title,
            # Anything we do not recognise is genuinely 'other', not a blank -- the
            # field has a catch-all value, so use it instead of leaving work for the
            # candidate.
            'achievement_type': _choice(
                entry.get('achievement_type'), ACHIEVEMENT_TYPE_CHOICES
            ) or 'other',
            'date_achieved': date_achieved,
            'issuer': _text(entry.get('issuer')) or '',
            'description': _text(entry.get('description'), None) or '',
            'url': _text(entry.get('url')) or '',
            'needs_review': [],
        })
    return out


def _prose_skills(raw):
    """Old shape: [{'candidate_skills': 'Languages: A, B, C'}, {...}, ...].

    Each entry is one CV skill line, so it usually carries the section heading the CV
    printed in front of it -- 'Backend: Django REST Framework, Node.js'. Left in place
    that heading becomes part of the first skill of every group, so the candidate ends
    up with a chip reading "Backend: Django REST Framework".
    """
    skills = []
    for entry in raw or []:
        value = _text(entry.get('candidate_skills') if isinstance(entry, dict) else entry)
        if not value:
            continue
        # Strip a leading 'Heading:' but only when it looks like one -- a short run of
        # words before the first colon. Guards against eating something like
        # 'Ratio: 3:1' or a genuine skill containing a colon further in.
        head, sep, rest = value.partition(':')
        if sep and len(head.split()) <= 4 and _text(rest):
            value = rest
        for part in value.split(','):
            name = _text(part)
            if name and name not in skills:
                skills.append(name)
    return skills


def _strip_urls(text):
    """Remove any http(s) URLs from a fragment, returning what is left."""
    return ' '.join(w for w in str(text or '').split() if not w.lower().startswith('http'))


def _prose_contact(contact_summary):
    """Pull location and profile links out of the packed contact line.

    The old shape crams everything into one string, and the order is not fixed:
        'Boston, MA | a@b.com | (777) 123-4567 | LinkedIn'
        '+92 335 1627264 | a@b.com | Lahore, Pakistan https://linkedin.com/in/x'
    So every segment is examined rather than assuming the place comes first, and URLs
    are stripped before deciding whether a segment names a place.
    """
    segments = [s.strip() for s in str(contact_summary or '').split('|') if s.strip()]

    location = None
    for segment in segments:
        candidate = _text(_strip_urls(segment))
        # A place has no '@' and no digits -- that rules out emails and phone numbers,
        # which are the only other things that show up here.
        if candidate and '@' not in candidate and not any(c.isdigit() for c in candidate):
            location = candidate
            break

    known = (('linkedin.com', 'LinkedIn'), ('github.com', 'GitHub'),
             ('gitlab.com', 'GitLab'), ('behance.net', 'Behance'),
             ('dribbble.com', 'Dribbble'), ('stackoverflow.com', 'Stack Overflow'))
    links, seen = [], set()
    for word in str(contact_summary or '').split():
        if not word.lower().startswith('http'):
            continue
        url = word.rstrip('.,;')
        if url in seen:
            continue
        seen.add(url)
        name = next((label for domain, label in known if domain in url.lower()), 'Website')
        links.append({'name': name, 'url': url})

    return location, links


def to_form_values(resume_data):
    """Map parsed CV data to profile-wizard field values.

    Absent keys mean "nothing found" -- callers fill only fields the candidate has left
    empty, so an omitted key and an empty string are meaningfully different.
    """
    data = resume_data if isinstance(resume_data, dict) else {}
    values = {}

    def put(key, value):
        if value:
            values[key] = value

    put('fullName', _text(data.get('full_name')))
    put('bio', _text(data.get('bio') or data.get('summary'), None))
    put('title', _text(data.get('title') or data.get('target_roles')))
    put('passionProjects', _text(data.get('passion_projects'), None))
    put('seniorityLevel', _choice(
        data.get('seniority_level') or data.get('seniority'), SENIORITY_CHOICES
    ))

    if _is_structured(data):
        put('location', location_text(data.get('location'), MAX_CHARFIELD))
        skills = [s for s in (data.get('skills') or []) if _text(s)]
        put('portfolioLinks', [
            {'name': _text(l.get('name')) or 'Link', 'url': _text(l.get('url'))}
            for l in (data.get('portfolio_links') or [])
            if isinstance(l, dict) and _text(l.get('url'))
        ])
        put('experience', _map_experience(data.get('experience') or data.get('experiences')))
        put('education', _map_education(data.get('education')))
        put('achievements', _map_achievements(data.get('achievements')))
    else:
        location, links = _prose_contact(data.get('contact_summary'))
        put('location', location)
        put('portfolioLinks', links)
        skills = _prose_skills(data.get('skills'))
        # The old shape has no `passion_projects`, but `projects.description` carries the
        # same content as one blob -- close enough to seed the field the candidate edits.
        projects = data.get('projects')
        if isinstance(projects, dict):
            put('passionProjects', _text(projects.get('description'), None))
        # Prose experience/education are sentences -- there is nothing to map them onto,
        # so they are surfaced as reference text beside the Background step instead.
        put('reference_text', {
            key: [e.get('description') for e in (data.get(key) or [])
                  if isinstance(e, dict) and e.get('description')]
            for key in ('experiences', 'education')
            if data.get(key)
        })

    if skills:
        # All of them, so the candidate can swap; only the first MAX start selected.
        # A silent truncation here drops whatever the CV happened to list last, which
        # is not the same as least important.
        values['skills'] = {
            'available': skills,
            'selected': skills[:MAX_SELECTED_SKILLS],
        }
    return values


def demo():
    """Self-check over the cases that actually broke: enums, caps, and the old shape."""
    structured = {
        'full_name': 'SYED FAIZAN JAVED',
        'title': 'Full-Stack Software Engineer',
        'bio': 'Full-Stack Software Engineer with 2+ years...',
        'location': {'city': 'Lahore', 'region': 'Punjab', 'country': 'Pakistan'},
        'seniority_level': 'junior',
        'skills': [f'skill{i}' for i in range(29)],
        'portfolio_links': [{'name': 'GitHub', 'url': 'https://github.com/x'},
                            {'name': 'Broken', 'url': ''}],
        'passion_projects': 'Supplement.AI, WeaveSync',
        'education': [
            {'institution': 'NCBA&E', 'degree': 'bs', 'field_of_study': 'Computer Science',
             'start_date': '2021-10-01', 'end_date': '2025-07-01', 'is_current': False,
             'grading_system': 'gpa', 'gpa': 3.7, 'total_marks': 4},
            {'institution': 'Punjab Group', 'degree': 'intermediate',
             'field_of_study': 'Pre-Engineering', 'grading_system': 'marks',
             'total_marks': 1100, 'obtained_marks': 1002},
            {'degree': 'bs'},  # no institution -> dropped
        ],
        'achievements': [
            {'title': 'AWS Certified Solutions Architect', 'achievement_type': 'certification',
             'date_achieved': '2022-01-01', 'issuer': 'AWS'},
            {'title': 'Undated award', 'achievement_type': 'award'},  # no date -> dropped
        ],
        'experience': [
            {'company_name': 'NeuroOceans. Ai', 'position': 'Associate Software Engineer',
             'start_date': '2024-08-01', 'is_current': True,
             'location': {'city': None, 'region': 'Punjab', 'country': 'Pakistan'},
             'achievements': ['Shipped SaaS'], 'skills_used': ['React.js']},
            {'company_name': 'Stackup', 'position': 'Frontend Intern',
             'employment_type': 'internship', 'start_date': '2023-10-01',
             'location': {'city': 'Remote', 'region': 'Remote', 'country': 'Remote'}},
            {'company_name': 'NoPlace', 'position': 'Dev', 'location': None},
        ],
    }
    v = to_form_values(structured)
    assert v['fullName'] == 'SYED FAIZAN JAVED'
    assert v['title'] == 'Full-Stack Software Engineer'
    assert v['seniorityLevel'] == 'junior'
    # /extract_resume returns location as {city, region, country}; the form and the
    # CharField both hold one string.
    assert v['location'] == 'Lahore, Punjab, Pakistan', v['location']
    assert [e['location'] for e in v['experience']] == ['Punjab, Pakistan', 'Remote', '']
    assert 'location' not in to_form_values({'title': 'x', 'location': None})
    assert to_form_values({'title': 'x', 'location': 'Lahore, Pakistan'})['location'] == \
        'Lahore, Pakistan', 'resume_data stored before the object shape is still a string'

    assert len(v['skills']['available']) == 29, 'all skills offered'
    assert len(v['skills']['selected']) == 12, 'only MAX preselected'

    assert len(v['portfolioLinks']) == 1, 'link with no url dropped'

    edu = v['education']
    assert len(edu) == 2, 'row without an institution dropped'
    assert edu[0]['degree'] == 'bachelor', 'bs -> bachelor'
    assert edu[0]['needs_review'] == []
    assert edu[0]['gpa'] == '3.7' and edu[0]['totalMarks'] == '4', 'numbers become strings'
    assert edu[1]['degree'] == 'high_school', 'intermediate -> high_school'

    ach = v['achievements']
    assert len(ach) == 1, 'undated achievement dropped -- date_achieved is required'
    assert ach[0]['achievement_type'] == 'certification'
    assert ach[0]['issuer'] == 'AWS'

    exp = v['experience']
    assert exp[0]['employment_type'] == '', 'missing type stays blank, never guessed'
    assert exp[0]['needs_review'] == ['employment_type']
    assert exp[0]['isCurrent'] is True
    assert exp[1]['employment_type'] == 'internship'
    assert exp[1]['needs_review'] == []

    # Regression: Education.grade is varchar(1) with an A-F list. Anything else both
    # fails the choices check and overflows the column -- it reached the DB as
    # "value too long for type character varying(1)".
    grades = to_form_values({'title': 'x', 'education': [
        {'institution': 'A', 'grade': 'A'},      # valid, uppercase preserved
        {'institution': 'B', 'grade': 'A+'},     # not a choice -> blank
        {'institution': 'C', 'grade': 'First Class'},
        {'institution': 'D', 'grade': '3.70'},
        {'institution': 'E', 'grade': 'b'},      # case-folded to a valid choice
    ]})['education']
    assert [e['grade'] for e in grades] == ['A', '', '', '', 'B'], [e['grade'] for e in grades]

    # Every mapped CharField target is varchar(200); free-text CVs can exceed it.
    long_name = 'X' * 400
    over = to_form_values({'title': 'x', 'full_name': long_name,
                           'education': [{'institution': long_name, 'field_of_study': long_name}],
                           'experience': [{'company_name': long_name, 'position': long_name,
                                           'location': {'city': long_name}}],
                           'achievements': [{'title': long_name, 'issuer': long_name,
                                             'date_achieved': '2020-01-01'}]})
    assert len(over['fullName']) == 200
    assert all(len(over['education'][0][k]) == 200 for k in ('institute', 'degreeName'))
    assert all(len(over['experience'][0][k]) == 200 for k in ('company_name', 'position', 'location'))
    assert all(len(over['achievements'][0][k]) == 200 for k in ('title', 'issuer'))
    # TextField targets are not truncated.
    assert len(to_form_values({'title': 'x', 'bio': long_name})['bio']) == 400

    # Invalid enums must blank the field, never pass through.
    bad = to_form_values({'education': [{'institution': 'X', 'degree': 'wizardry',
                                         'grading_system': 'vibes'}],
                          'experience': [{'company_name': 'Y', 'position': 'Z',
                                          'employment_type': 'permanent'}]})
    assert bad['education'][0]['degree'] == ''
    assert bad['education'][0]['gradingSystem'] == ''
    assert bad['experience'][0]['employment_type'] == ''
    odd = to_form_values({'title': 'x', 'achievements': [
        {'title': 'Thing', 'achievement_type': 'nobel-ish', 'date_achieved': '2020-01-01'}]})
    assert odd['achievements'][0]['achievement_type'] == 'other', 'catch-all, not blank'

    # Old prose shape still yields the fields it can.
    prose = to_form_values({
        'full_name': "James O'Connor",
        'summary': 'Cybersecurity Analyst with 1 year...',
        'seniority': 'Junior',
        'contact_summary': 'Boston, MA | james@email.com | (777) 123-4567 | LinkedIn',
        'skills': [{'candidate_skills': 'SIEM (Splunk), Incident response'}],
        'experiences': [{'description': 'Junior Analyst at a Financial Services Firm...'}],
        'education': [{'description': 'B.Sc. in IT from Northeastern University, 2023.'}],
    })
    assert prose['fullName'] == "James O'Connor"
    assert prose['seniorityLevel'] == 'junior', 'Junior -> junior'
    assert prose['location'] == 'Boston, MA'
    assert prose['skills']['available'] == ['SIEM (Splunk)', 'Incident response']
    assert 'education' not in prose, 'prose education is not form-shaped'
    assert len(prose['reference_text']['experiences']) == 1

    # Real prose payload: the place is third, behind a phone and an email, and has a
    # URL glued to it. Skill lines carry their CV section heading.
    messy = to_form_values({
        'contact_summary': '+92 335 1627264 | faizan@gmail.com | Lahore, Pakistan '
                           'https://linkedin.com/in/x | https://github.com/y',
        'skills': [{'candidate_skills': 'Languages: Python, TypeScript'},
                   {'candidate_skills': 'Backend: Django REST Framework, Node.js'}],
        'projects': {'description': 'Supplement.AI, WeaveSync'},
    })
    assert messy['location'] == 'Lahore, Pakistan', messy.get('location')
    assert messy['skills']['available'] == [
        'Python', 'TypeScript', 'Django REST Framework', 'Node.js',
    ], messy['skills']['available']
    assert [l['name'] for l in messy['portfolioLinks']] == ['LinkedIn', 'GitHub']
    assert messy['passionProjects'] == 'Supplement.AI, WeaveSync'

    # metadata.extracted_profile_image: anything that would not survive the profile
    # image upload has to come back as None, not reach the client as a broken <img>.
    png = 'data:image/png;base64,iVBORw0KGgo='
    assert profile_image_from_metadata({'extracted_profile_image': png}) == png
    assert profile_image_from_metadata(
        {'extracted_profile_image': 'DATA:IMAGE/JPEG;base64,/9j/4AA='}
    ), 'mime and scheme are case-insensitive'
    assert profile_image_from_metadata({}) is None
    assert profile_image_from_metadata(None) is None
    assert profile_image_from_metadata('not a dict') is None
    assert profile_image_from_metadata({'extracted_profile_image': None}) is None
    assert profile_image_from_metadata({'extracted_profile_image': ''}) is None
    assert profile_image_from_metadata({'extracted_profile_image': '   '}) is None
    assert profile_image_from_metadata(
        {'extracted_profile_image': 'https://cdn/photo.png'}
    ) is None, 'a URL is not a data URI -- the client expects to inline it'
    assert profile_image_from_metadata(
        {'extracted_profile_image': 'data:image/svg+xml;base64,PHN2Zz4='}
    ) is None, 'svg is not an accepted profile image type'
    assert profile_image_from_metadata(
        {'extracted_profile_image': 'data:application/pdf;base64,JVBERi0='}
    ) is None
    assert profile_image_from_metadata(
        {'extracted_profile_image': 'data:image/png;base64,'}
    ) is None, 'declared but empty payload'
    assert profile_image_from_metadata(
        {'extracted_profile_image': 'data:image/png;base64,' + 'A' * MAX_PROFILE_IMAGE_CHARS}
    ) is None, 'over the size ceiling'
    assert profile_image_from_metadata({'extracted_profile_image': 12345}) is None

    assert to_form_values(None) == {} and to_form_values({}) == {}
    print('resume_mapper OK')


if __name__ == '__main__':
    demo()
