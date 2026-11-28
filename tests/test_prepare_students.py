import csv
import io
from pathlib import Path

import pytest
from scripts import prepare_students


def test_only_registry_fields_and_no_source_values(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_text('Course;Gender;Target\n9119;source-private-marker;Dropout\n9500;another-marker;Graduate\n', encoding='utf-8')
    processed = tmp_path / 'processed'
    monkeypatch.setattr(prepare_students, 'PROCESSED_DIR', processed.resolve())
    output = processed / 'demo.csv'
    assert prepare_students.prepare(source, output) == 2
    with output.open(encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    assert set(rows[0]) == set(prepare_students.FIELDS)
    assert rows[0]['course'] == 'Informatics Engineering'
    assert rows[0]['student_id'] == 'UCI000001'
    assert rows[0]['university_email'] == 'uci000001@students.example.ac.uk'
    assert 'source-private-marker' not in output.read_text()
    with pytest.raises(FileExistsError):
        prepare_students.prepare(source, output)


def test_invalid_course_and_output_path_are_rejected(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    source.write_text('Course;Target\n999999;Dropout\n', encoding='utf-8')
    processed = tmp_path / 'processed'
    monkeypatch.setattr(prepare_students, 'PROCESSED_DIR', processed.resolve())
    with pytest.raises(ValueError, match='unknown'):
        prepare_students.prepare(source, processed / 'out.csv')
    assert not processed.exists()
    with pytest.raises(ValueError, match='inside data/processed'):
        prepare_students.prepare(source, tmp_path / 'outside.csv')
