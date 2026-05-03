"""Integration test for parse-log API endpoint."""
import requests

B = 'http://localhost:8000'
s = requests.Session()
s.post(B + '/api/auth/login', json={'email': 'user@test.com', 'password': 'test123456'})
projs = s.get(B + '/api/projects').json()
pid = projs[0]['id']

# create experiment
r = s.post(B + '/api/projects/' + str(pid) + '/experiments', json={'name': 'ParseTest', 'status': 'running'})
eid = r.json()['experiment_id']
print('exp:', eid)

# upload a log file
log = (
    b'Epoch: 1 | train_loss: 0.1823 | val_loss: 0.1542 | psnr: 24.31 | ssim: 0.812\n'
    b'Epoch: 2 | train_loss: 0.1518 | val_loss: 0.1329 | psnr: 25.02 | ssim: 0.834\n'
    b'Epoch: 3 | train_loss: 0.1200 | val_loss: 0.1100 | psnr: 26.50 | ssim: 0.860\n'
)
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('train.log', log, 'text/plain')})
fid = r.json()['file']['id']
print('file:', fid)

# parse
r = s.post(B + '/api/experiments/' + str(eid) + '/parse-log', json={'file_id': fid, 'overwrite': False})
d = r.json()
print('parse:', d['ok'], d['parsed_records_count'], 'metrics')
print('names:', d['metric_names'])
print('epoch:', d['epoch_min'], '-', d['epoch_max'])
print('lines:', d['line_count'], 'parsed:', d['parsed_line_count'], 'skipped:', d['skipped_line_count'])

# parse again without overwrite (should be 0 new)
r = s.post(B + '/api/experiments/' + str(eid) + '/parse-log', json={'file_id': fid, 'overwrite': False})
d = r.json()
print('dup parse:', d['parsed_records_count'], 'new')

# parse with overwrite
r = s.post(B + '/api/experiments/' + str(eid) + '/parse-log', json={'file_id': fid, 'overwrite': True})
d = r.json()
print('overwrite:', d['parsed_records_count'], 'metrics')

# upload CSV file
csv_data = b'epoch,train_loss,val_loss,psnr\n1,0.5,0.4,20.0\n2,0.3,0.2,22.0\n'
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('metrics.csv', csv_data, 'text/csv')})
fid2 = r.json()['file']['id']
r = s.post(B + '/api/experiments/' + str(eid) + '/parse-log', json={'file_id': fid2, 'overwrite': False})
d = r.json()
print('csv parse:', d['parsed_records_count'], d['metric_names'])

# upload tqdm log
tqdm_log = (
    b'Epoch 1/10: 100%|' + b'\xe2\x96\x88' * 10 + b'| 100/100 [01:23<00:00, loss=0.123, lr=2e-4, psnr=28.31]\n'
    b'Epoch 2/10: 100%|' + b'\xe2\x96\x88' * 10 + b'| 100/100 [01:20<00:00, loss=0.098, lr=2e-4, psnr=30.12]\n'
)
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('tqdm.log', tqdm_log, 'text/plain')})
fid3 = r.json()['file']['id']
r = s.post(B + '/api/experiments/' + str(eid) + '/parse-log', json={'file_id': fid3, 'overwrite': False})
d = r.json()
print('tqdm parse:', d['parsed_records_count'], d['metric_names'])

# upload JSON lines
jl = b'{"epoch":1,"loss":0.5,"acc":0.8}\n{"epoch":2,"loss":0.3,"acc":0.9}\n'
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('jsonl.log', jl, 'text/plain')})
fid4 = r.json()['file']['id']
r = s.post(B + '/api/experiments/' + str(eid) + '/parse-log', json={'file_id': fid4, 'overwrite': False})
d = r.json()
print('jsonl parse:', d['parsed_records_count'], d['metric_names'])

# detail page
r = s.get(B + '/experiments/' + str(eid))
print('detail page:', r.status_code)

# bad file type
r = s.post(B + '/api/experiments/' + str(eid) + '/upload', files={'file': ('img.png', b'PNG', 'image/png')})
img_fid = r.json()['file']['id']
r = s.post(B + '/api/experiments/' + str(eid) + '/parse-log', json={'file_id': img_fid, 'overwrite': False})
print('bad type:', r.status_code, r.json()['ok'])
