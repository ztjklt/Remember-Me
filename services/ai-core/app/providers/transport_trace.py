"""Timing-only HTTP instrumentation. Never retain headers, input, or exceptions."""
from time import perf_counter


class TransportTrace:
    def __init__(self, record, started):
        self.record, self.started = record, started
        self.timings = record.setdefault('transport', {})
        self.active = 'client_or_pool'
        self.begins = {}

    def mark(self, key):
        self.timings.setdefault(key, round((perf_counter()-self.started)*1000, 3))

    async def __call__(self, event, info):
        # info may contain credentials or source texts. Intentionally ignore it.
        kind, _, status = event.rpartition('.')
        name = kind.rsplit('.', 1)[-1]
        phases = {'connect_tcp':'connect', 'start_tls':'tls',
                  'send_request_headers':'request_headers', 'send_request_body':'request_body',
                  'receive_response_headers':'response_headers', 'receive_response_body':'response_body'}
        phase = phases.get(name)
        if phase is None: return
        if status == 'started':
            self.active = phase
            self.begins[phase] = perf_counter()
        elif status == 'complete':
            if phase in self.begins:
                self.timings[phase+'_ms'] = round((perf_counter()-self.begins[phase])*1000, 3)
            if phase == 'request_body': self.mark('request_sent_ms')
            if phase == 'response_headers': self.headers()

    def headers(self):
        self.mark('headers_ms')
        self.active = 'response_body'

    def timeout(self):
        self.record['timeout_phase'] = self.active
        if self.active in self.begins:
            self.timings[self.active+'_wait_ms'] = round((perf_counter()-self.begins[self.active])*1000, 3)
