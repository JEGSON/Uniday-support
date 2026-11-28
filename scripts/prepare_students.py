"""Prepare fictional demo identities from UCI course codes; never imports to MongoDB.

Source: Realinho et al. (2021), https://doi.org/10.24432/C5MC89, CC BY 4.0.
Output contains fictional names and IDs; the course distribution derives from
records of real students and must not be presented as wholly synthetic research.
"""
import argparse
import csv
import io
from pathlib import Path
import zipfile

from faker import Faker

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'data/raw/uci-student-success.zip'
DEFAULT_OUTPUT = ROOT / 'data/processed/uci_demo_registry.csv'
PROCESSED_DIR = (ROOT / 'data/processed').resolve()
FIELDS = ('student_id', 'full_name', 'course', 'university_email')
# UCI's documented course codes; fixed mapping prevents source text entering output.
COURSES = {
    '33': 'Biofuel Production Technologies', '171': 'Animation and Multimedia Design',
    '8014': 'Social Service (evening attendance)', '9003': 'Agronomy',
    '9070': 'Communication Design', '9085': 'Veterinary Nursing',
    '9119': 'Informatics Engineering', '9130': 'Equinculture', '9147': 'Management',
    '9238': 'Social Service', '9254': 'Tourism', '9500': 'Nursing', '9556': 'Oral Hygiene',
    '9670': 'Advertising and Marketing Management', '9773': 'Journalism and Communication',
    '9853': 'Basic Education', '9991': 'Management (evening attendance)',
}


def read_course_codes(source):
    """Read only the documented Course column from the supplied CSV or UCI ZIP."""
    if source.suffix.lower() == '.zip':
        with zipfile.ZipFile(source) as archive:
            with archive.open('data.csv') as raw:
                with io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as text:
                    return _courses(text)
    with source.open(encoding='utf-8-sig', newline='') as text:
        return _courses(text)


def _courses(text):
    reader = csv.DictReader(text, delimiter=';')
    if not reader.fieldnames or reader.fieldnames.count('Course') != 1:
        raise ValueError('Expected one Course column in the semicolon-delimited UCI CSV.')
    codes = []
    for row in reader:
        value = row.get('Course')
        code = value.strip() if isinstance(value, str) else ''
        if code not in COURSES:
            raise ValueError('A row contains an unknown or missing course code.')
        codes.append(code)
    if not codes:
        raise ValueError('The input contains no student rows.')
    return codes


def prepare(source, output):
    """Write only demo fields; refuse to replace an existing output or escape data/processed."""
    destination = output.resolve()
    if not destination.is_relative_to(PROCESSED_DIR) or destination == PROCESSED_DIR:
        raise ValueError('Output must be a file inside data/processed.')
    codes = read_course_codes(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fake = Faker('en_GB')
    fake.seed_instance(697)  # Reproducible demo names; they do not represent source students.
    with destination.open('x', encoding='utf-8', newline='') as result:
        writer = csv.DictWriter(result, fieldnames=FIELDS)
        writer.writeheader()
        for index, code in enumerate(codes, 1):
            student_id = f'UCI{index:06d}'
            writer.writerow({'student_id': student_id, 'full_name': fake.name(),
                             'course': COURSES[code],
                             'university_email': f'{student_id.lower()}@students.example.ac.uk'})
    return len(codes)


def main():
    parser = argparse.ArgumentParser(description='Prepare a local fictional UCI-based demo registry.')
    parser.add_argument('--input', type=Path, default=DEFAULT_SOURCE, help='UCI ZIP or semicolon-delimited CSV.')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help='New CSV under data/processed.')
    args = parser.parse_args()
    try:
        count = prepare(args.input, args.output)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, f'Preparation failed: {exc}\n')
    print(f'Prepared {count} fictional demo records in {args.output}. No database changes were made.')


if __name__ == '__main__':
    main()
