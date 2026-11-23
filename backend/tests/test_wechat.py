from io import BytesIO
import logging
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select, func
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import User
from test_workflows import API, complete


@pytest.fixture
def exchange(monkeypatch):
    monkeypatch.setattr(settings(), 'wechat_appid', 'test-app')
    monkeypatch.setattr(settings(), 'wechat_secret', 'test-secret')
    state = {'data': {'openid': 'test-wechat-owner', 'session_key': 'test-session'}}
    async def get(client, url, **kwargs):
        if 'error' in state:
            raise state['error']
        return httpx.Response(200, json=state['data'], request=httpx.Request('GET', url))
    with patch.object(httpx.AsyncClient, 'get', get):
        yield state


def login(client):
    return client.post(API + '/auth/wechat', json={'code': 'test-only-placeholder'})


def test_wechat_first_login_logout_relogin_history(client, tokens, exchange, caplog):
    caplog.set_level(logging.INFO)
    first = login(client)
    assert first.status_code == 200
    body = first.json()
    uid = body['user']['id']
    assert body['user']['role'] == 'user' and uid != client.get(API + '/users/me', headers=tokens['user']).json()['id']
    assert 'session_key' not in body and 'openid' not in body['user']
    headers = {'Authorization': 'Bearer ' + body['access_token']}
    rid, _, _ = complete(client, headers)
    assert client.post(API + '/auth/logout', headers=headers).status_code == 200
    assert client.get(API + '/users/me', headers=headers).status_code == 401
    again = login(client)
    assert again.status_code == 200 and again.json()['user']['id'] == uid
    new_headers = {'Authorization': 'Bearer ' + again.json()['access_token']}
    assert client.get(API + '/reports/' + rid, headers=new_headers).status_code == 200
    assert client.get(API + '/reports', headers=new_headers).json()['total'] == 1
    assert client.get(API + '/reports', headers=tokens['user']).json()['total'] == 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.openid == 'test-wechat-owner')) == 1
    for value in ['test-secret', 'test-session', 'test-only-placeholder', body['access_token']]:
        assert value not in caplog.text


@pytest.mark.parametrize('error,status', [(40029,401),(40163,401),(40013,503),(40125,503),(40164,503),(45011,429),(-1,503),(40226,403)])
def test_wechat_error_messages(client, exchange, error, status):
    exchange['data'] = {'errcode': error, 'errmsg': 'upstream details must not be forwarded'}
    response = login(client)
    assert response.status_code == status
    assert 'upstream details' not in response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize('data', [[], None, {}, {'openid': 123}])
def test_wechat_malformed_response(client, exchange, data):
    exchange['data'] = data
    assert login(client).status_code == 503


def test_wechat_missing_config_and_network(client, exchange, monkeypatch):
    exchange['error'] = httpx.ConnectError('upstream confidential details')
    response = login(client)
    assert response.status_code == 503 and 'confidential' not in response.text
    monkeypatch.setattr(settings(), 'wechat_secret', '')
    assert login(client).status_code == 503


def test_wechat_disabled_user(client, exchange):
    assert login(client).status_code == 200
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.openid == 'test-wechat-owner'))
        user.active = False
        db.commit()
    assert login(client).status_code == 403
