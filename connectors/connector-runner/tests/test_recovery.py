import httpx
import pytest

from connector.adapters.echo import EchoAdapter
from connector.config import ServerConfig, save_credentials
from connector.ledger import Ledger
from connector.tokens import TokenManager
from connector.ws import ConnectorSession
from connector.ws import ActiveRun


async def test_persisted_access_token_is_refreshed_before_use():
    async def handle(request):
        assert request.url.path == '/v1/connectors/access-tokens'
        return httpx.Response(200, json={'request_id': 'r', 'data': {'access_token': 'fresh', 'expires_in': 900}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        tokens = TokenManager({'access_token': 'expired', 'refresh_credential': 'valid', 'expires_in': 900}, 'http://server', http)
        assert await tokens.get_access_token() == 'fresh'


async def test_completed_output_is_queried_then_replayed_after_disconnect(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.sqlite3')
    ledger.upsert('execution', run_id='run', status='completion_pending', chunks=['hello'], final_text='hello', attempt_no=1, fencing_token=1)
    sent = []
    class Socket:
        async def send(self, raw):
            import json
            sent.append(json.loads(raw))
    async with httpx.AsyncClient() as http:
        session = ConnectorSession(config=ServerConfig('http://server', tmp_path / 'creds', tmp_path / 'ledger.sqlite3'), token_manager=None, ledger=ledger, adapter=EchoAdapter(), http=http, adapter_kind='echo', connector_id='connector')
        session._ws = Socket()
        await session._resume_unfinished()
        await session._handle_frame({'type': 'run.status', 'execution_id': 'execution', 'state': 'running', 'attempt_no': 1, 'fencing_token': 1, 'may_continue': True, 'next_chunk_index': 0})
        assert [frame['type'] for frame in sent] == ['run.query', 'run.delta', 'run.completed', 'run.query']
        assert sent[-2]['final_text'] == 'hello'
        assert ledger.get('execution').status == 'completion_pending'
        await session._handle_frame({'type': 'run.status', 'execution_id': 'execution', 'state': 'succeeded', 'may_continue': False})
        assert ledger.get('execution').status == 'succeeded'
    ledger.close()


async def test_lost_completion_frame_remains_durable_and_recoverable(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.sqlite3')
    ledger.upsert('execution', run_id='run', status='accepted', attempt_no=1, fencing_token=1)
    class Socket:
        async def send(self, raw):
            import json
            if json.loads(raw)['type'] == 'run.completed':
                raise ConnectionError('connection dropped')
    async with httpx.AsyncClient() as http:
        session = ConnectorSession(config=ServerConfig('http://server', tmp_path / 'creds', tmp_path / 'ledger.sqlite3'), token_manager=None, ledger=ledger, adapter=EchoAdapter(), http=http, adapter_kind='echo', connector_id='connector')
        session._ws = Socket()
        await session._execute_run(ActiveRun(execution_id='execution', run_id='run', attempt_no=1, fencing_token=1, context=[{'text': 'ok'}]))
        record = ledger.get('execution')
        assert record.status == 'completion_pending'
        assert record.final_text == 'ok'
        assert [row.execution_id for row in ledger.list_unfinished()] == ['execution']
    ledger.close()


async def test_recovery_does_not_resend_chunks_server_already_received(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.sqlite3')
    ledger.upsert('execution', run_id='run', status='completion_pending', chunks=['a', 'b'], final_text='ab', attempt_no=1, fencing_token=1)
    sent = []
    class Socket:
        async def send(self, raw):
            import json
            sent.append(json.loads(raw))
    async with httpx.AsyncClient() as http:
        session = ConnectorSession(config=ServerConfig('http://server', tmp_path / 'creds', tmp_path / 'ledger.sqlite3'), token_manager=None, ledger=ledger, adapter=EchoAdapter(), http=http, adapter_kind='echo', connector_id='connector')
        session._ws = Socket()
        await session._handle_frame({'type': 'run.status', 'execution_id': 'execution', 'state': 'running', 'attempt_no': 1, 'fencing_token': 1, 'may_continue': True, 'next_chunk_index': 2})
        assert [frame['type'] for frame in sent] == ['run.completed', 'run.query']
    ledger.close()


async def test_cancel_after_restart_preserves_execution_fence(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.sqlite3')
    ledger.upsert('execution', run_id='run', status='running', attempt_no=2, fencing_token=9)
    sent = []
    class Socket:
        async def send(self, raw):
            import json
            sent.append(json.loads(raw))
    async with httpx.AsyncClient() as http:
        session = ConnectorSession(config=ServerConfig('http://server', tmp_path / 'creds', tmp_path / 'ledger.sqlite3'), token_manager=None, ledger=ledger, adapter=EchoAdapter(), http=http, adapter_kind='echo', connector_id='connector')
        session._ws = Socket()
        await session._handle_cancel({'type': 'run.cancel', 'run_id': 'run', 'execution_id': 'execution'})
        assert sent[0]['attempt_no'] == 2
        assert str(sent[0]['fencing_token']) == '9'
    ledger.close()


def test_run_config_uses_paired_server_when_no_override(tmp_path, monkeypatch):
    monkeypatch.delenv('AICHAT_SERVER_URL', raising=False)
    monkeypatch.delenv('AICHAT_CONNECTOR_SERVER', raising=False)
    path = tmp_path / 'credentials.json'
    save_credentials(path, {'server_base_url': 'https://paired.example/'})
    config = ServerConfig.load(credentials_path=path)
    assert config.server_base_url == 'https://paired.example'
    assert ServerConfig.load('https://override.example', path).server_base_url == 'https://override.example'


async def test_output_limit_is_applied_before_chunk_is_persisted_or_sent(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.sqlite3')
    ledger.upsert('execution', run_id='run', status='accepted', attempt_no=1, fencing_token=1)
    sent = []
    class Adapter:
        async def run(self, context, system_prompt):
            yield 'ab'
            yield '你好c'
    class Socket:
        async def send(self, raw):
            import json
            sent.append(json.loads(raw))
    async with httpx.AsyncClient() as http:
        session = ConnectorSession(config=ServerConfig('http://server', tmp_path / 'creds', tmp_path / 'ledger.sqlite3'), token_manager=None, ledger=ledger, adapter=Adapter(), http=http, adapter_kind='echo', connector_id='connector')
        session._ws = Socket()
        await session._execute_run(ActiveRun(execution_id='execution', run_id='run', attempt_no=1, fencing_token=1, policy={'max_output_bytes': 5}))
        deltas = [frame for frame in sent if frame['type'] == 'run.delta']
        assert ''.join(frame['text'] for frame in deltas) == 'ab'
        assert ledger.get('execution').chunks == ['ab']
        assert ledger.get('execution').final_text is None
        assert next(frame for frame in sent if frame['type'] == 'run.failed')['error_code'] == 'OUTPUT_LIMIT'
        assert not any(frame['type'] == 'run.completed' for frame in sent)
    ledger.close()


async def test_adapter_exception_body_is_not_published_in_run_error(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.sqlite3')
    ledger.upsert('execution', run_id='run', status='accepted', attempt_no=1, fencing_token=1)
    sent = []
    class Adapter:
        async def run(self, context, system_prompt):
            raise RuntimeError('upstream private response secret-token')
            yield ''
    class Socket:
        async def send(self, raw):
            import json
            sent.append(json.loads(raw))
    async with httpx.AsyncClient() as http:
        session = ConnectorSession(config=ServerConfig('http://server', tmp_path / 'creds', tmp_path / 'ledger.sqlite3'), token_manager=None, ledger=ledger, adapter=Adapter(), http=http, adapter_kind='openai', connector_id='connector')
        session._ws = Socket()
        await session._execute_run(ActiveRun(execution_id='execution', run_id='run', attempt_no=1, fencing_token=1))
        failure = next(frame for frame in sent if frame['type'] == 'run.failed')
        assert failure['error_code'] == 'ADAPTER_ERROR'
        assert 'secret-token' not in failure['message']
        assert 'upstream private response' not in failure['message']
    ledger.close()
