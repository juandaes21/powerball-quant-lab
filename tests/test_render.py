"""Deployment controls for the Render-hosted free demo."""
from __future__ import annotations
from fastapi.testclient import TestClient
from app import data
from app.server import app


def test_render_read_only_and_limits(monkeypatch):
    monkeypatch.setenv('POWERBALL_READ_ONLY', '1')
    monkeypatch.setenv('RENDER', 'true')
    client=TestClient(app)
    assert client.get('/api/meta').json()['read_only'] is True
    assert client.get('/api/health').json()['draws']==443
    assert client.post('/api/ledger/lock').status_code==403
    assert client.post('/api/update',json={'start_year':2026}).status_code==403
    assert client.post('/api/edge-null',json={'reps':30}).status_code==403
    assert client.post('/api/tests',json={'reps':2500}).status_code==422
    assert client.post('/api/simulate',json={'ticket':[1,2,3,4,5,6,7],'powerball':10,'n':300000}).status_code==422
    assert client.post('/api/simulate',json={'ticket':[1,2,3,4,5,6,7],'powerball':10,'n':100}).status_code==200

def test_storage_seeding_on_persistent_disk(monkeypatch, tmp_path):
    original_data=data.DATA_FILE
    original_dir=data.STORAGE_DIR
    try:
        monkeypatch.setattr(data, 'STORAGE_DIR', str(tmp_path))
        monkeypatch.setattr(data, 'DATA_FILE', tmp_path/'powerball_australia.csv')
        assert not data.DATA_FILE.exists()
        assert len(data.load_draws())==443
        assert data.DATA_FILE.exists()
        data.DATA_FILE.write_text('CUSTOM SAVED DATA',encoding='utf-8')
        # Reseeding must NEVER overwrite state on the attached disk.
        data.ensure_data_file()
        assert data.DATA_FILE.read_text()=='CUSTOM SAVED DATA'
    finally:
        monkeypatch.setattr(data, 'DATA_FILE', original_data)
        monkeypatch.setattr(data, 'STORAGE_DIR', original_dir)
