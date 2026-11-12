/* ============================================================================
 * Mock API — so every async solution actually runs in the browser.
 * Installs a fake `fetch` that honors AbortSignal, adds latency, and can be
 * made to fail on demand. Nothing here is interview material; it exists so
 * the solutions are demonstrably correct rather than merely plausible.
 * ========================================================================== */
export const API = (() => {
    const settings = { latency: 700, failRate: 0, jitter: 400 };

    const EXPERIENCES = [
        'Adopt Me!', 'Brookhaven RP', 'Blox Fruits', 'Tower of Hell', 'Murder Mystery 2',
        'Natural Disaster Survival', 'Jailbreak', 'Arsenal', 'Doors', 'Piggy',
        'Pet Simulator 99', 'Bee Swarm Simulator', 'Theme Park Tycoon 2', 'Meepcity',
        'Work at a Pizza Place', 'Royale High', 'Bloxburg', 'Anime Fighters',
        'Rainbow Friends', 'Evade', 'Sonic Speed Simulator', 'Ninja Legends',
        'Tower Defense Simulator', 'Blade Ball', 'Dress to Impress',
    ].map((name, i) => ({
        id: `exp-${i + 1}`,
        name,
        creator: ['Uplift Games', 'Wolfpaq', 'Gamer Robot', 'YXCeptional', 'Nikilis'][i % 5],
        plays: Math.round(200_000 + Math.abs(Math.sin(i * 2.7)) * 4_800_000),
        rating: Math.round((78 + Math.abs(Math.cos(i * 1.9)) * 21) * 10) / 10,
        updated: Date.UTC(2026, 6, 1 + (i % 28)),
        favorited: i % 4 === 0,
    }));

    const PAYOUTS = Array.from({ length: 43 }, (_, i) => ({
        id: `pay-${i + 1}`,
        creator: [
            'builderman', 'stickmasterluke', 'Sonar Studios', 'RedManta', 'Voldex',
            'Fivestar Games', 'Sky Labs', 'Blue Shift', 'Nova Interactive', 'Pixel Forge',
        ][i % 10] + (i >= 10 ? ` ${Math.floor(i / 10) + 1}` : ''),
        region: ['NA', 'EMEA', 'APAC', 'LATAM'][i % 4],
        robux: Math.round(1_000 + Math.abs(Math.sin(i * 1.3)) * 980_000),
        devex: Math.round((Math.abs(Math.sin(i * 1.3)) * 3430 + 3.5) * 100) / 100,
        date: Date.UTC(2026, 6, 1 + (i % 30)),
        status: ['paid', 'pending', 'paid', 'failed'][i % 4],
    }));

    const wait = ms => new Promise(r => setTimeout(r, ms));

    function respond(body, status = 200) {
        return {
            ok: status >= 200 && status < 300,
            status,
            json: async () => body,
            text: async () => JSON.stringify(body),
        };
    }

    /** Fake fetch: supports AbortSignal, latency, and injected failures. */
    async function fetchMock(url, options = {}) {
        const { signal } = options;
        if (signal?.aborted) throw abortError();

        const delay = settings.latency + Math.random() * settings.jitter;

        await new Promise((resolve, reject) => {
            const timer = setTimeout(resolve, delay);
            if (signal) {
                signal.addEventListener('abort', () => {
                    clearTimeout(timer);
                    reject(abortError());
                }, { once: true });
            }
        });

        if (Math.random() < settings.failRate) return respond({ error: 'Upstream unavailable' }, 503);

        const parsed = new URL(url, 'https://mock.local');
        const path = parsed.pathname;
        const params = parsed.searchParams;
        const method = (options.method || 'GET').toUpperCase();

        // GET /api/experiences?q=&cursor=&limit=
        if (path === '/api/experiences' && method === 'GET') {
            const q = (params.get('q') || '').trim().toLowerCase();
            const limit = Number(params.get('limit') || 8);
            const cursor = Number(params.get('cursor') || 0);
            const matches = q
                ? EXPERIENCES.filter(e => e.name.toLowerCase().includes(q) || e.creator.toLowerCase().includes(q))
                : EXPERIENCES;
            const slice = matches.slice(cursor, cursor + limit);
            return respond({
                items: slice,
                nextCursor: cursor + limit < matches.length ? cursor + limit : null,
                total: matches.length,
            });
        }

        // POST /api/experiences/:id/favorite
        const favMatch = path.match(/^\/api\/experiences\/([^/]+)\/favorite$/);
        if (favMatch && method === 'POST') {
            if (favMatch[1].endsWith('3')) return respond({ error: 'Could not update favorite' }, 500);
            return respond({ id: favMatch[1], ok: true });
        }

        // GET /api/payouts
        if (path === '/api/payouts' && method === 'GET') return respond({ items: PAYOUTS });

        // POST /api/transfers
        if (path === '/api/transfers' && method === 'POST') {
            const body = JSON.parse(options.body || '{}');
            if (String(body.recipient).toLowerCase() === 'taken') {
                return respond({ error: 'That username is already pending a transfer.' }, 409);
            }
            if (Number(body.amount) > 10_000) {
                return respond({ error: 'Amount exceeds your available balance.' }, 422);
            }
            return respond({ id: 'txn-' + Math.round(Math.random() * 1e6), ...body }, 201);
        }

        // POST /api/poll/:option
        if (path.startsWith('/api/poll/') && method === 'POST') return respond({ ok: true });

        return respond({ error: 'Not found' }, 404);
    }

    function abortError() {
        const e = new Error('The operation was aborted.');
        e.name = 'AbortError';
        return e;
    }

    return {
        fetch: fetchMock,
        settings,
        data: { EXPERIENCES, PAYOUTS },
        wait,
        setLatency: ms => { settings.latency = ms; },
        setFailRate: rate => { settings.failRate = rate; },
    };
})();
