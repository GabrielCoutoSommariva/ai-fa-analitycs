import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

const BASE_URL = (__ENV.BASE_URL || 'https://dash.farmaciasassociadas.com.br').replace(/\/$/, '');
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';
const CNPJ = __ENV.CNPJ || '';
const START_DATE = __ENV.START_DATE || '2026-06-01';
const END_DATE = __ENV.END_DATE || '2026-07-01';
const VUS = Number(__ENV.VUS || 10);
const DURATION = __ENV.DURATION || '2m';

const apiErrors = new Rate('api_errors');
const apiLatency = new Trend('api_latency');

export const options = {
  scenarios: {
    dashboard_smoke: {
      executor: 'constant-vus',
      vus: VUS,
      duration: DURATION,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<2000'],
    api_errors: ['rate<0.05'],
    api_latency: ['p(95)<2000'],
  },
};

function params() {
  return {
    headers: {
      Accept: 'application/json',
    },
    redirects: 0,
  };
}

function apiGet(path) {
  const response = http.get(`${BASE_URL}${path}`, params());
  const ok = response.status >= 200 && response.status < 500;
  apiErrors.add(!ok);
  apiLatency.add(response.timings.duration);
  check(response, {
    [`${path} status < 500`]: (res) => res.status < 500,
    [`${path} responds`]: (res) => res.status !== 0,
  });
  return response;
}

function sessionCookie(response) {
  const cookies = response.cookies || {};
  const parts = [];
  for (const [name, entries] of Object.entries(cookies)) {
    if (entries && entries.length > 0) {
      parts.push(`${name}=${entries[0].value}`);
    }
  }
  return parts.join('; ');
}

function query(basePath) {
  const params = [`data_inicio=${START_DATE}`, `data_fim=${END_DATE}`];
  if (CNPJ) {
    params.push(`cnpj=${CNPJ}`);
  }
  return `${basePath}?${params.join('&')}`;
}

export function setup() {
  if (!AUTH_TOKEN) {
    return { authenticated: false };
  }

  const response = http.get(`${BASE_URL}/api/auth/session?token=${encodeURIComponent(AUTH_TOKEN)}`, params());
  check(response, {
    'auth session accepted': (res) => res.status === 200,
  });

  return { authenticated: response.status === 200, cookie: sessionCookie(response) };
}

export default function (state) {
  group('public health', () => {
    const response = http.get(`${BASE_URL}/api/health`, params());
    check(response, {
      'health 200': (res) => res.status === 200,
    });
  });

  if (!state.authenticated) {
    sleep(1);
    return;
  }

  const authenticatedParams = params();
  authenticatedParams.headers.Cookie = state.cookie;

  group('authenticated dashboard api', () => {
    const paths = [
      query('/api/metrics/summary'),
      query('/api/metrics/summary-matriz'),
      query('/api/metrics/operacional-summary'),
      query('/api/metrics/operacional-summary-matriz'),
      `${query('/api/metrics/faturamento-tendencia')}&granularidade=auto`,
    ];

    for (const path of paths) {
      const response = http.get(`${BASE_URL}${path}`, authenticatedParams);
      const ok = response.status >= 200 && response.status < 500;
      apiErrors.add(!ok);
      apiLatency.add(response.timings.duration);
      check(response, {
        [`${path} authenticated status < 500`]: (res) => res.status < 500,
        [`${path} authenticated 2xx`]: (res) => res.status >= 200 && res.status < 300,
      });
    }
  });

  sleep(1);
}
