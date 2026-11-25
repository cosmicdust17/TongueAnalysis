from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

from sqlalchemy import func, select

from app.api import health_trends
from app.core.database import SessionLocal
from app.core.security import issue_token
from app.models import Analysis, Report, StoredFile, SymptomCheckin, SymptomSuggestionDismissal, User
from app.services.report_presentation import PRESENTATION_VERSION
from app.services.analysis_service import process_one
from test_workflows import image_bytes

API = '/api/v1'
TRACKINGS = API + '/health-trends/trackings'
SUGGESTIONS = API + '/health-trends/analyses'


def upload(client, headers):
    response = client.post(API + '/uploads', headers=headers,
                           files={'file': ('tongue.png', image_bytes(), 'image/png')})
    assert response.status_code == 201, response.text
    return response.json()['id']


def submit(client, headers, image_id, **extra):
    response = client.post(API + '/analyses', headers=headers,
                           json={'image_id': image_id, 'symptoms': '口干，乏力，睡眠不佳', **extra})
    assert response.status_code == 202, response.text
    return response.json()['id']


def completed_report(client, headers, analysis_id):
    assert process_one()
    result = client.get(API + '/analyses/' + analysis_id, headers=headers).json()
    assert result['status'] == 'completed'
    return result['report_id']


def start(client, headers, name):
    return client.post(TRACKINGS, headers=headers, json={'symptom_name': name})


def other_user():
    with SessionLocal() as db:
        user = User(username='other-health-user', role='user')
        db.add(user)
        db.commit()
        return {'Authorization': 'Bearer ' + issue_token(user)}


def test_suggestion_from_new_confirmations_only(client, tokens):
    headers = tokens['user']
    image_id = upload(client, headers)

    def suggest(aid):
        response = client.get(f'{SUGGESTIONS}/{aid}/suggestion', headers=headers)
        assert response.status_code == 200, response.text
        return response.json()['suggestion']

    first = submit(client, headers, image_id)
    assert suggest(first) is None
    first_report = completed_report(client, headers, first)
    assert suggest(first) is None
    assert client.get(f'{API}/reports/{first_report}', headers=headers).json()['content']['presentation']['symptoms_text'] == '口干，乏力，睡眠不佳'

    aid = submit(client, headers, image_id, confirmed_symptoms=['　乏力 ', '口干', '乏力'])
    assert suggest(aid) is None
    with SessionLocal() as db:
        db.get(Analysis, aid).status = 'failed'
        db.commit()
    assert suggest(aid) is None
    assert client.post(f'{API}/analyses/{aid}/retry', headers=headers).status_code == 202
    assert suggest(aid) is None
    completed_report(client, headers, aid)
    assert suggest(aid) == {'symptom_name': '乏力'}
    assert suggest(aid) == {'symptom_name': '乏力'}
    assert client.get(TRACKINGS, headers=headers).json()['items'] == []

    dismissal = f'{SUGGESTIONS}/{aid}/dismissal'
    invalid = client.put(dismissal, headers=headers, json={'symptom_name': '睡眠不佳'})
    assert invalid.status_code == 409
    for _ in range(2):
        response = client.put(dismissal, headers=headers, json={'symptom_name': '乏力'})
        assert response.json() == {'symptom_name': '乏力', 'dismissed': True}
    assert suggest(aid) == {'symptom_name': '口干'}
    assert start(client, headers, '口干').status_code == 200
    assert suggest(aid) is None

    # A repeated confirmation is unchanged even when there is still one slot.
    aid = submit(client, headers, image_id, confirmed_symptoms=['乏力', '睡眠不佳'])
    completed_report(client, headers, aid)
    assert suggest(aid) == {'symptom_name': '睡眠不佳'}
    repeated = submit(client, headers, image_id, confirmed_symptoms=['睡眠不佳'])
    completed_report(client, headers, repeated)
    assert suggest(repeated) is None
    later = submit(client, headers, image_id, confirmed_symptoms=['口干', '乏力'])
    completed_report(client, headers, later)
    assert suggest(later) is None

    manual = start(client, headers, '乏力')
    assert manual.status_code == 200
    full = submit(client, headers, image_id, confirmed_symptoms=['鼻塞'])
    completed_report(client, headers, full)
    assert suggest(full) is None
    assert client.post(f'{API}/analyses/{full}/retry', headers=headers).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SymptomSuggestionDismissal)) == 1
        assert db.scalar(select(func.count()).select_from(SymptomCheckin)) == 0


def test_daily_checkins_and_pause_resume(client, tokens, monkeypatch):
    headers = tokens['user']
    monkeypatch.setattr(health_trends, 'now', lambda: datetime(2026, 11, 23, 16))
    item = start(client, headers, '口干').json()
    url = f"{TRACKINGS}/{item['id']}"
    today = url + '/checkins/today'
    trend = url + '/trend?start_date=2026-11-23&end_date=2026-11-25'
    initial = client.get(TRACKINGS, headers=headers).json()
    assert initial['date'] == '2026-11-24' and initial['items'] == [item | {'today_level': None}]
    assert client.get(trend, headers=headers).json()['items'] == []
    assert client.put(today, headers=headers, json={'level': '0'}).status_code == 422
    assert client.put(today, headers=headers, json={'level': False}).status_code == 422
    assert client.put(today, headers=headers, json={'level': 4}).status_code == 422
    zero = {'date': '2026-11-24', 'level': 0, 'level_name': '没有'}
    assert client.put(today, headers=headers, json={'level': 0}).json() == zero
    assert client.get(trend, headers=headers).json()['items'] == [zero]
    assert client.get(TRACKINGS, headers=headers).json()['items'][0]['today_level'] == 0
    changed = zero | {'level': 2, 'level_name': '明显'}
    assert client.put(today, headers=headers, json={'level': 2}).json() == changed
    assert client.get(trend, headers=headers).json()['items'] == [changed]
    assert client.put(url + '/stop', headers=headers).json() == item | {'active': False}
    assert client.put(url + '/stop', headers=headers).status_code == 200
    paused = client.put(today, headers=headers, json={'level': 1})
    assert paused.status_code == 409 and paused.json()['detail']['code'] == 'tracking_paused'
    assert client.get(trend, headers=headers).json()['items'] == [changed]
    assert start(client, headers, '　口干 ').json() == item
    assert client.get(trend, headers=headers).json()['items'] == [changed]
    assert client.get(url + '/trend?start_date=2026-11-25&end_date=2026-11-24', headers=headers).status_code == 422

    monkeypatch.setattr(health_trends, 'now', lambda: datetime(2026, 11, 25, 16))
    second = client.put(today, headers=headers, json={'level': 3}).json()
    assert second == {'date': '2026-11-26', 'level': 3, 'level_name': '很明显'}
    assert client.get(url + '/trend?start_date=2026-11-24&end_date=2026-11-26', headers=headers).json()['items'] == [changed, second]


def test_parallel_start_respects_limit_and_reuses_id(client, tokens):
    headers = tokens['user']

    def parallel(names):
        barrier = Barrier(len(names))

        def add(name):
            barrier.wait(timeout=10)
            return start(client, headers, name)

        with ThreadPoolExecutor(max_workers=len(names)) as pool:
            return list(pool.map(add, names))

    first = parallel(['Ａ 症状', 'a　症状', 'A 症状'])
    assert all(response.status_code == 200 for response in first), [r.text for r in first]
    assert len({response.json()['id'] for response in first}) == 1

    more = parallel(['口干', '乏力', '鼻塞'])
    assert sorted(response.status_code for response in more) == [200, 409, 409]
    for response in more:
        if response.status_code == 409:
            assert response.json()['detail'] == {'code': 'tracking_limit_reached', 'message': '最多同时追踪两项症状', 'max_active': 2}
    assert client.get(TRACKINGS, headers=headers).json()['active_count'] == 2
    assert start(client, headers, 'A 症状').json()['id'] == first[0].json()['id']


def test_tracking_owner_isolation(client, tokens):
    headers = tokens['user']
    other = other_user()
    item = start(client, headers, '口干').json()
    url = f"{TRACKINGS}/{item['id']}"
    aid = submit(client, headers, upload(client, headers), confirmed_symptoms=['口干'])
    completed_report(client, headers, aid)
    assert client.get(TRACKINGS, headers=other).json()['items'] == []
    assert client.get(TRACKINGS).status_code == 401
    assert client.get(TRACKINGS, headers=tokens['knowledge_admin']).status_code == 403
    assert client.put(url + '/stop', headers=other).status_code == 404
    assert client.put(url + '/checkins/today', headers=other, json={'level': 2}).status_code == 404
    assert client.get(url + '/trend?start_date=2026-11-01&end_date=2026-11-30', headers=other).status_code == 404
    assert client.get(f'{SUGGESTIONS}/{aid}/suggestion', headers=other).status_code == 404
    assert client.put(f'{SUGGESTIONS}/{aid}/dismissal', headers=other, json={'symptom_name': '口干'}).status_code == 404
    assert start(client, other, '口干').json()['id'] != item['id']


def test_report_calendar_counts_only_completed_photos_by_local_upload_date(client, tokens):
    headers = tokens['user']
    other = other_user()
    october_image, november_image, failed_image = [upload(client, headers) for _ in range(3)]
    other_image = upload(client, other)
    aids, reports = [], []
    for image_id in (october_image, november_image, november_image, failed_image):
        aid = submit(client, headers, image_id)
        aids.append(aid)
        reports.append(completed_report(client, headers, aid))
    other_report = completed_report(client, other, submit(client, other, other_image))
    with SessionLocal() as db:
        for image_id, stamp in zip((october_image, november_image, failed_image, other_image), [
            datetime(2026, 10, 31, 15, 59, 59), datetime(2026, 10, 31, 16),
            datetime(2026, 11, 2, 16), datetime(2026, 10, 31, 16),
        ]):
            db.get(StoredFile, image_id).created_at = stamp
        for report_id, stamp in zip(reports + [other_report], [
            datetime(2026, 10, 31, 16, 3), datetime(2026, 10, 31, 17),
            datetime(2026, 11, 1, 16, 10), datetime(2026, 11, 2, 17),
            datetime(2026, 10, 31, 17),
        ]):
            db.get(Report, report_id).created_at = stamp
        db.get(Analysis, aids[-1]).status = 'failed'
        user_id = db.get(Analysis, aids[0]).user_id
        text_file = StoredFile(owner_id=user_id, original_name='notes.txt', path='notes.txt',
                               content_type='text/plain', purpose='document', size=12,
                               created_at=datetime(2026, 11, 3, 16))
        db.add(text_file)
        db.flush()
        text_analysis = Analysis(user_id=user_id, image_id=text_file.id, symptoms='纯文本对照',
                                 duration='近一周', status='completed')
        db.add(text_analysis)
        db.flush()
        text_report = Report(user_id=user_id, analysis_id=text_analysis.id,
                             content={'presentation': {'version': PRESENTATION_VERSION}, 'annotations': {}},
                             created_at=datetime(2026, 11, 3, 17))
        db.add(text_report)
        db.commit()
        text_report_id = text_report.id

    calendar = API + '/reports/calendar?month='
    assert client.get(calendar + '2026-11', headers=headers).json() == {
        'month': '2026-11', 'dates': ['2026-11-01'], 'counts': {'2026-11-01': 2},
    }
    assert client.get(calendar + '2026-10', headers=headers).json() == {
        'month': '2026-10', 'dates': ['2026-10-31'], 'counts': {'2026-10-31': 1},
    }
    assert client.get(calendar + '2026-12', headers=headers).json() == {'month': '2026-12', 'dates': [], 'counts': {}}
    assert client.get(calendar + '2026-13', headers=headers).status_code == 422
    assert client.get(calendar + '2026-11', headers=other).json()['counts'] == {'2026-11-01': 1}
    assert client.get(calendar + '2026-10', headers=other).json()['dates'] == []
    day = API + '/reports?date=2026-11-01'
    result = client.get(day, headers=headers).json()
    assert result['total'] == 2 and [item['id'] for item in result['items']] == [reports[2], reports[1]]
    assert client.get(day + '&page=2&page_size=1', headers=headers).json()['items'][0]['id'] == reports[1]
    assert [item['id'] for item in client.get(day, headers=other).json()['items']] == [other_report]
    assert [item['id'] for item in client.get(API + '/reports?date=2026-10-31', headers=headers).json()['items']] == [reports[0]]
    for empty_day in ('2026-11-02', '2026-11-03', '2026-11-04'):
        assert client.get(f'{API}/reports?date={empty_day}', headers=headers).json() == {
            'items': [], 'total': 0, 'page': 1, 'page_size': 20,
        }
    assert text_report_id in {item['id'] for item in client.get(API + '/reports', headers=headers).json()['items']}
    assert client.get(API + '/reports?date=2026-02-30', headers=headers).status_code == 422
    assert client.get(calendar + '2026-11').status_code == 401
    assert client.get(day, headers=tokens['ops_admin']).status_code == 403
    assert client.get(f'{API}/reports/{reports[1]}', headers=headers).status_code == 200
    assert client.get(f'{API}/reports/{reports[1]}', headers=other).status_code == 404
