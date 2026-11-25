(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const motion = $('motion'), feed = $('feed'), extras = $('extras');
  const video = $('movie'), idle = $('idle'), poster = $('poster');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const minute = 60_000, pollMs = 12_000;
  const pendingSlot = 'pips-yard-browser-review-unconfirmed';
  let state = null, offset = 0, getPending = false, claiming = false, claimRevision = 0;
  let unconfirmed = null, loadFailed = false, availableChecked = 0;
  let timer, pollTimer;
  let animate = !reduced.matches, sceneId = null, blocked = false, pendingPlay = false, attempt = 0;
  try {
    const saved = sessionStorage.getItem(pendingSlot);
    if (/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(saved)) unconfirmed = saved;
  } catch { /* Private mode can disable storage. */ }

  function text(node, value) {
    if (node.textContent !== value) node.textContent = value;
  }
  function notify(value) {
    text($('note'), value);
    $('note').hidden = !value;
  }
  function pendingKey(key) {
    unconfirmed = key;
    try {
      if (key) sessionStorage.setItem(pendingSlot, key);
      else sessionStorage.removeItem(pendingSlot);
    } catch { /* An in-memory key still protects retries in this tab. */ }
  }
  function timestamp(value) {
    if (typeof value !== 'string' || !/(?:Z|[+-]\d\d:\d\d)$/.test(value)) throw Error('Invalid clock');
    const ms = Date.parse(value);
    if (!Number.isFinite(ms)) throw Error('Invalid clock');
    return ms;
  }
  function normalize(data) {
    if (!data || !Object.hasOwn(data, 'next_free_at') || !Object.hasOwn(data, 'event')) throw Error('Invalid yard state');
    const server = timestamp(data.server_time);
    const next = data.next_free_at === null ? 0 : timestamp(data.next_free_at);
    let visit = null;
    if (data.event !== null) {
      const event = data.event;
      if (!event || typeof event.id !== 'string' || !event.id || event.duration_seconds !== 60) throw Error('Invalid visit');
      visit = {id:event.id, start:timestamp(event.started_at), visitor:event.visitor === 'braids' ? 'braids' : 'cap'};
    }
    return {server, next, visit};
  }
  async function request(path, options, codes) {
    const abort = new AbortController(), sent = Date.now();
    const timeout = setTimeout(() => abort.abort(), 8000);
    try {
      const response = await window.PipYardReview.request(path, {cache:'no-store', credentials:'omit', signal:abort.signal, ...options});
      if (!codes.includes(response.status)) throw Error('Yard unavailable');
      const data = normalize(await response.json());
      return {status:response.status, data, offset:data.server - (sent + Date.now()) / 2};
    } finally {
      clearTimeout(timeout);
    }
  }
  function readState() {
    return request('/api/state', {}, [200]);
  }
  function claim(key) {
    return request('/api/claim', {
      method:'POST', headers:{'Content-Type':'application/json','Idempotency-Key':key}, body:'{}'
    }, [200,201,409]);
  }
  function accept(reply) {
    if (!state || reply.data.server >= state.server) {
      state = reply.data;
      offset = reply.offset;
    }
    loadFailed = false;
  }
  function tickTime() { return Date.now() + offset; }
  function visitAt(now) {
    const visit = state && state.visit;
    return visit && visit.start <= now && now < visit.start + minute ? visit : null;
  }
  function showExtras(show) {
    extras.hidden = !show;
    feed.setAttribute('aria-expanded', String(show));
  }
  function countdown(ms) {
    const n = Math.ceil(ms / 1000);
    return [Math.floor(n / 3600), Math.floor(n / 60) % 60, n % 60].map(part => String(part).padStart(2, '0')).join(':');
  }
  function renderBowl(now) {
    const left = state ? Math.max(0, state.next - now) : 0;
    feed.disabled = claiming || (!state && !loadFailed);
    text(feed, claiming ? 'Sending bowl…' : 'Feed & Play');
    const label = loadFailed ? (left ? 'Last known free-bowl countdown' : 'The shared timer is unavailable.')
      : !state ? 'Checking the shared bowl…' : left ? 'Next free bowl' : 'The free bowl is ready.';
    text($('bowl'), label);
    $('clock').hidden = !left;
    if (left) {
      text($('clock'), countdown(left));
      $('clock').dateTime = new Date(state.next).toISOString();
    } else {
      showExtras(false);
      if (state && state.next && state.next !== availableChecked) {
        // Another visitor may have claimed at the boundary.
        availableChecked = state.next;
        if (!document.hidden) refresh();
      }
    }
  }
  function mediaUrl(name) { return name.endsWith('.mp4') ? 'https://kaustubhdalvi.github.io/Kaustubhdalvi/' + name : 'https://raw.githubusercontent.com/Kaustubhdalvi/Kaustubhdalvi/main/assets/' + name; }
  function setImage(img, url) {
    if (img.getAttribute('src') !== url) img.src = url;
  }
  const captions = [
    [0,'A visitor walks past the doghouse.'],
    [5,'The puppies run over to greet their visitor.'],
    [13,'The visitor kneels to feed both puppies.'],
    [22,'The puppies chase the ball while their mother sleeps.'],
    [50,'The visitor waves goodbye.'],
    [55,'The visitor heads home and the puppies return to the grass.']
  ];
  function renderScene(now) {
    const visit = visitAt(now);
    if ((visit && visit.id) !== sceneId) {
      sceneId = visit && visit.id;
      attempt++;
      pendingPlay = false;
      blocked = false;
      video.pause();
    }
    const moving = animate && !document.hidden;
    text(motion, blocked && visit && animate ? 'Retry animation' : animate ? 'Pause motion' : 'Play motion');
    idle.hidden = Boolean(visit);
    poster.hidden = !visit;
    if (!visit) {
      video.hidden = true;
      video.pause();
      setImage(idle, mediaUrl(moving ? 'pip-ball-yard.gif' : 'pip-ball-yard-still.png'));
      text($('scene'), 'The puppies are playing in the grass.');
      return;
    }
    const seconds = (now - visit.start) / 1000;
    const beat = captions.filter(([at]) => at <= seconds).pop();
    text($('scene'), beat[1]);
    const stem = visit.visitor === 'braids' ? 'pip-visitor-braids' : 'pip-visitor';
    setImage(poster, mediaUrl(stem + '-still.png'));
    if (!moving || blocked) {
      video.hidden = true;
      video.pause();
      return;
    }
    video.poster = poster.getAttribute('src');
    video.hidden = false;
    const movie = mediaUrl(stem + '-minute.mp4');
    if (video.getAttribute('src') !== movie) {
      video.src = movie;
      video.load();
    }
    if (video.readyState >= 1 && Number.isFinite(video.duration)) {
      const target = Math.min(seconds, Math.max(0, video.duration - .025));
      if (Math.abs(video.currentTime - target) > .35) {
        try { video.currentTime = target; } catch { /* Metadata may still be loading. */ }
      }
    }
    if (video.paused && !video.ended && !pendingPlay) {
      const epoch = attempt;
      pendingPlay = true;
      video.play().catch(() => {
        if (epoch === attempt && animate && !document.hidden) { blocked = true; draw(); }
      }).finally(() => { if (epoch === attempt) pendingPlay = false; });
    }
  }
  function draw() {
    clearTimeout(timer);
    const now = tickTime();
    renderScene(now);
    renderBowl(now);
    if (document.hidden) return;
    const ends = [state && state.next, state && state.visit && state.visit.start, state && state.visit && state.visit.start + minute];
    const waits = ends.filter(time => time > now).map(time => time - now);
    if (waits.length) timer = setTimeout(draw, Math.max(1, Math.min(...waits, 1000)));
  }
  async function refresh() {
    clearTimeout(pollTimer);
    if (getPending || document.hidden) return;
    getPending = true;
    const revision = claimRevision;
    try {
      const reply = await readState();
      if (claimRevision === revision) accept(reply);
    } catch {
      if (claimRevision === revision) loadFailed = true;
    } finally {
      getPending = false;
      draw();
      if (!document.hidden) pollTimer = setTimeout(refresh, pollMs);
    }
  }
  feed.addEventListener('click', async () => {
    if (claiming) return;
    if (!unconfirmed && state && state.next > tickTime()) {
      notify('');
      showExtras(extras.hidden);
      return;
    }
    claiming = true;
    notify('');
    draw();
    try {
      if (!unconfirmed) pendingKey(crypto.randomUUID());
      const reply = await claim(unconfirmed);
      claimRevision++;
      accept(reply);
      pendingKey(null);
      if (reply.status === 409) {
        showExtras(true);
        notify(state.next > tickTime() ? 'Another visitor filled the free bowl first.' : 'That request was in an earlier feeding window. The free bowl is available again.');
      } else {
        showExtras(false);
        notify(visitAt(tickTime()) ? 'You filled the bowl. Your visit is underway.' : 'Your feeding was accepted.');
        if (reply.status === 200) refresh();
      }
    } catch {
      loadFailed = true;
      notify('We couldn’t confirm the feeding. Press Feed & Play to check the same request.');
    } finally {
      claiming = false;
      draw();
    }
  });
  motion.addEventListener('click', () => {
    attempt++;
    pendingPlay = false;
    if (blocked && animate) { blocked = false; video.removeAttribute('src'); }
    else animate = !animate;
    draw();
  });
  reduced.addEventListener('change', () => { animate = !reduced.matches; draw(); });
  for (const name of ['loadedmetadata','canplay','playing','seeked','ended']) video.addEventListener(name, draw);
  video.addEventListener('error', () => { if (sceneId) { blocked = true; draw(); } });
  document.addEventListener('visibilitychange', () => {
    clearTimeout(pollTimer);
    draw();
    if (!document.hidden) refresh();
  });
  window.addEventListener('pip-yard-review-change', refresh);
  window.addEventListener('online', refresh);
  window.addEventListener('pageshow', event => { if (event.persisted) refresh(); });
  motion.hidden = false;
  feed.setAttribute('aria-expanded', 'false');
  draw();
  refresh();
})();
