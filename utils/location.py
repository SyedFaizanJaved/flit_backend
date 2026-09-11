"""The ML extractors' location object -> the one string every location column and form field holds."""


def location_text(value, limit):
    """{'city', 'region', 'country'} -> 'City, Region, Country', or None.

    `/extract_resume` and `/extract_company_profile` return each part independently
    nullable, and a remote role as all three set to 'Remote'. Blanks are dropped and
    repeats collapsed, so that reads as 'Remote' rather than 'Remote, Remote, Remote'.

    A plain string still passes through: `Candidate.resume_data` rows parsed before the
    object shape shipped, and the prose `/parse_cv` shape, both carry one.
    """
    if isinstance(value, dict):
        parts = []
        for key in ('city', 'region', 'country'):
            part = str(value.get(key) or '').strip()
            if part and part.lower() not in {p.lower() for p in parts}:
                parts.append(part)
        value = ', '.join(parts)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip()
    return text or None


if __name__ == '__main__':
    assert location_text({'city': 'New York', 'region': 'NY', 'country': 'USA'}, 200) == 'New York, NY, USA'
    assert location_text({'city': None, 'region': 'Sindh', 'country': 'Pakistan'}, 200) == 'Sindh, Pakistan'
    assert location_text({'city': 'Remote', 'region': 'Remote', 'country': 'Remote'}, 200) == 'Remote'
    assert location_text({'city': 'Singapore', 'region': None, 'country': 'singapore'}, 200) == 'Singapore'
    assert location_text({'city': None, 'region': None, 'country': None}, 200) is None
    assert location_text({}, 200) is None
    assert location_text(None, 200) is None
    assert location_text(['Lahore'], 200) is None, 'contract is never an array'
    assert location_text('  Lahore, Pakistan ', 200) == 'Lahore, Pakistan', 'legacy string'
    assert len(location_text({'city': 'X' * 300, 'country': 'Y'}, 200)) == 200
    print('location OK')
