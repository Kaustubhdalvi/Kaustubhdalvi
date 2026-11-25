/* Browser-only review. No remote API, accounts, payments or public leaderboard. */
(() => {
  'use strict';
  const windowMs = 12 * 60 * 60 * 1000;
  const database = 'kaustubhdalvi-pips-yard-browser-review-v1';
  const storeName = 'records';
  const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
  let channel;
  try {
    channel = new BroadcastChannel(database);
    channel.onmessage = () => window.dispatchEvent(new Event('pip-yard-review-change'));
  } catch { /* Other tabs also poll the same committed data. */ }

  function response(status, data) {
    return new Response(JSON.stringify(data), {status,
      headers: {'Content-Type':'application/json','Cache-Control':'no-store'}});
  }

  function snapshot(now, latest, event = latest) {
    return {version:1, server_time:new Date(now).toISOString(),
      next_free_at:latest ? new Date(Date.parse(latest.started_at) + windowMs).toISOString() : null,
      event};
  }

  function readClock(state) {
    if (state !== undefined && (!state || !Number.isSafeInteger(state.clock) || !Object.hasOwn(state,'event'))) {
      throw Error('Invalid stored clock');
    }
    if (state?.event && (!Number.isFinite(Date.parse(state.event.started_at)) ||
        !uuid.test(state.event.id) || !['cap','braids'].includes(state.event.visitor) ||
        state.event.duration_seconds !== 60)) throw Error('Invalid stored visit');
    // The device timeline is shared across tabs; persisted time never moves backwards.
    const performanceTime = globalThis.performance?.timeOrigin + globalThis.performance?.now?.();
    return Math.max(state?.clock ?? 0, Date.now(), Number.isFinite(performanceTime) ? Math.floor(performanceTime) : 0);
  }

  function transact(claim, signal) {
    return new Promise((resolve, reject) => {
      let db, tx, result, finished = false;
      const stop = () => finish(Error('Review storage is unavailable'));
      const timer = setTimeout(stop, 5000);
      function finish(error) {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        signal?.removeEventListener('abort', stop);
        if (error && tx) { try {tx.abort();} catch { /* Transaction already completed. */ } }
        db?.close();
        if (error) reject(error); else resolve(result);
      }
      if (signal?.aborted) {stop(); return;}
      signal?.addEventListener('abort', stop, {once:true});
      let opening;
      try { opening = indexedDB.open(database, 1); } catch {stop(); return;}
      opening.onupgradeneeded = () => {
        if (finished) opening.transaction.abort();
        else opening.result.createObjectStore(storeName);
      };
      opening.onerror = opening.onblocked = stop;
      opening.onsuccess = () => {
        db = opening.result;
        if (finished) {db.close(); return;}
        db.onversionchange = () => { db.close(); stop(); };
        try {
          tx = db.transaction(storeName,'readwrite');
          tx.onabort = tx.onerror = stop;
          tx.oncomplete = () => finish();
          const store = tx.objectStore(storeName);
          const get = store.get('yard');
          get.onsuccess = () => {
            try {
              const state = get.result;
              const now = readClock(state);
              let latest = state?.event ?? null;
              const commit = (status, data, fresh = false) => {
                store.put({clock:now,event:latest}, 'yard');
                result = {status,data,fresh};
              };
              if (!claim) {commit(200,snapshot(now,latest)); return;}
              const key = 'attempt:' + claim.key;
              const previous = store.get(key);
              previous.onsuccess = () => {
                try {
                  const prior = previous.result;
                  if (prior !== undefined) {
                    if (!prior || !Object.hasOwn(prior,'event')) throw Error('Invalid stored attempt');
                    if (prior.choice !== claim.choice) {
                      commit(409,{...snapshot(now,latest),error:'This key already belongs to another claim.'});
                    } else {
                      commit(prior.event ? 200 : 409,snapshot(now,latest,prior.event || latest));
                    }
                    return;
                  }
                  const ready = !latest || now >= Date.parse(latest.started_at) + windowMs;
                  const event = ready ? {id:crypto.randomUUID(),started_at:new Date(now).toISOString(),
                    duration_seconds:60,visitor:claim.visitor} : null;
                  store.add({choice:claim.choice,event},key);
                  if (event) latest = event;
                  commit(ready ? 201 : 409,snapshot(now,latest),ready);
                } catch {stop();}
              };
            } catch {stop();}
          };
        } catch {stop();}
      };
    });
  }

  async function request(path, options = {}) {
    const isPost = path === '/api/claim';
    if (!isPost && path !== '/api/state') return response(404,{error:'Unknown review route.'});
    if ((options.method || 'GET') !== (isPost ? 'POST' : 'GET')) return response(405,{error:'Unsupported method.'});
    try {
      let claim;
      if (isPost) {
        const headers = new Headers(options.headers);
        const key = headers.get('Idempotency-Key');
        if (!key || !uuid.test(key)) return response(400,{error:'A UUID v4 key is required.'});
        let choice = 'auto';
        if (options.body != null) {
          if (headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
            return response(415,{error:'Expected application/json.'});
          }
          if (typeof options.body !== 'string' || new TextEncoder().encode(options.body).length>256) {
            return response(413,{error:'Claim body is too large.'});
          }
          let body;
          try {body = JSON.parse(options.body);} catch {return response(400,{error:'Invalid JSON.'});}
          if (!body || typeof body !== 'object' || Array.isArray(body) ||
            Object.keys(body).some(name => name !== 'visitor') ||
            (Object.hasOwn(body,'visitor') && !['cap','braids'].includes(body.visitor))) {
            return response(400,{error:'Unknown visitor or field.'});
          }
          choice = body.visitor || 'auto';
        }
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(key.toLowerCase()));
        const bytes = new Uint8Array(digest);
        const hash = Array.from(bytes,byte=>byte.toString(16).padStart(2,'0')).join('');
        claim = {key:hash,choice,visitor:choice === 'auto' ? ((bytes[0] >> 4) % 2 ? 'braids' : 'cap') : choice};
      }
      const answer = await transact(claim, options.signal);
      if (answer.fresh) { try {channel?.postMessage('visit');} catch { /* Polling remains active. */ } }
      return response(answer.status, answer.data);
    } catch {
      return response(503,{error:'Browser review storage is unavailable.'});
    }
  }
  window.PipYardReview = Object.freeze({request});
})();
