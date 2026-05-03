"""Integration test for import-csv API endpoint."""
import requests

B = 'http://localhost:8000'
s = requests.Session()
s.post(B + '/api/auth/login', json={'email': 'user@test.com', 'password': 'test123456'})
projs = s.get(B + '/api/projects').json()
pid = projs[0]['id']

# create experiment
r = s.post(B + '/api/projects/' + str(pid) + '/experiments', json={'name': 'CsvImportTest', 'status': 'running'})
eid = r.json()['experiment_id']
print('exp:', eid)

# ── 1. Standard epoch CSV ──
csv1 = b'epoch,train_loss,val_loss,psnr,ssim\n1,0.18,0.15,24.3,0.81\n2,0.15,0.13,25.0,0.83\n3,0.12,0.11,26.5,0.86\n'
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('metrics.csv', csv1, 'text/csv')})
fid = r.json()['file']['id']
print('file:', fid)

r = s.post(B + '/api/experiments/' + str(eid) + '/import-csv', json={'file_id': fid, 'overwrite': False})
d = r.json()
print('import:', d['ok'], d['imported_records_count'], 'records')
print('names:', d['metric_names'])
print('epoch:', d['epoch_min'], '-', d['epoch_max'])
assert d['imported_records_count'] == 12  # 4 metrics x 3 rows

# ── 2. Dedup (no overwrite) ──
r = s.post(B + '/api/experiments/' + str(eid) + '/import-csv', json={'file_id': fid, 'overwrite': False})
d = r.json()
print('dup import:', d['imported_records_count'], 'new')
assert d['imported_records_count'] == 0

# ── 3. Overwrite ──
r = s.post(B + '/api/experiments/' + str(eid) + '/import-csv', json={'file_id': fid, 'overwrite': True})
d = r.json()
print('overwrite:', d['imported_records_count'], 'records')
assert d['imported_records_count'] == 12

# ── 4. Step CSV ──
csv2 = b'step,loss,accuracy\n100,0.23,0.88\n200,0.19,0.90\n'
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('step.csv', csv2, 'text/csv')})
fid2 = r.json()['file']['id']
r = s.post(B + '/api/experiments/' + str(eid) + '/import-csv', json={'file_id': fid2, 'overwrite': False})
d = r.json()
print('step csv:', d['imported_records_count'], d['step_min'], '-', d['step_max'])
assert d['step_min'] == 100 and d['step_max'] == 200

# ── 5. Time CSV ──
csv3 = b'time,temperature,pressure\n0,25.1,101.3\n10,26.2,101.1\n'
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('time.csv', csv3, 'text/csv')})
fid3 = r.json()['file']['id']
r = s.post(B + '/api/experiments/' + str(eid) + '/import-csv', json={'file_id': fid3, 'overwrite': False})
d = r.json()
print('time csv:', d['imported_records_count'], 'time:', d['time_min'], '-', d['time_max'])
assert d['time_min'] == 0.0 and d['time_max'] == 10.0

# ── 6. Non-csv file rejected ──
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('train.log', b'epoch: 1', 'text/plain')})
log_fid = r.json()['file']['id']
r = s.post(B + '/api/experiments/' + str(eid) + '/import-csv', json={'file_id': log_fid, 'overwrite': False})
print('bad ext:', r.status_code, r.json()['ok'])
assert r.status_code == 400

# ── 7. Detail page renders ──
r = s.get(B + '/experiments/' + str(eid))
print('detail page:', r.status_code)
assert r.status_code == 200

print('\nAll API tests passed!')
