/* NutriChef front end.
   Three jobs: talk to the API, keep a little state, render. The API's language
   (ingredient_id, cost_inr, recipes_allowed) never reaches the screen - it is
   translated in `say` and the render functions below. */

/* Tell the stylesheet JavaScript is alive. Sections that fade in on scroll hide
   themselves only under .js, so if this file never runs the page still reads. */
document.documentElement.classList.add('js');

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (html !== undefined) node.innerHTML = html;
  return node;
};
const esc = (text) => String(text ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ---------------- words ---------------- */

const DIETS = {
  vegetarian: 'Vegetarian (no egg)', eggetarian: 'Vegetarian + egg', vegan: 'Vegan',
  jain: 'Jain', pescatarian: 'Pescatarian', non_vegetarian: 'Everything',
};
const ALLERGENS = {
  milk: 'Milk & dairy', egg: 'Egg', peanut: 'Peanut', tree_nut: 'Tree nuts',
  soy: 'Soy', wheat_gluten: 'Wheat / gluten', fish: 'Fish', crustacean: 'Shellfish',
  sesame: 'Sesame', sulphite: 'Sulphites',
};
const SLOTS = { breakfast: 'Breakfast', lunch: 'Lunch', dinner: 'Dinner', snack: 'Snack' };

const title = (text) => String(text).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
const money = (amount) => {
  const value = Number(amount || 0);
  return '₹' + (value >= 10 || value === 0 ? Math.round(value).toLocaleString('en-IN')
                                           : value.toFixed(1));
};
const weight = (value) => (value >= 1000 ? (value / 1000).toFixed(1) + ' kg'
                                         : Math.round(value) + ' g');

/* ---------------- photographs ----------------
   Free-licence food photography from Pexels, loaded straight from their CDN so
   nothing is committed to the repository. The path of each one was checked by
   hand - most are .jpeg but not all, so they are written out in full rather
   than built from the id. If a photo fails to load the frame keeps its warm
   gradient, so the page never shows a broken image. */

const PHOTOS = {
  thali:   '29148133/pexels-photo-29148133.jpeg',   // vegetarian thali with naan
  paneer:  '28674559/pexels-photo-28674559.jpeg',   // paneer tikka in curry
  idli:    '31199041/pexels-photo-31199041.jpeg',   // idli with sambar and chutney
  chana:   '9287035/pexels-photo-9287035.jpeg',     // chana masala
  dosa:    '32229637/pexels-photo-32229637.png',    // masala dosa on a banana leaf
  spices:  '15777497/pexels-photo-15777497.jpeg',   // spices at a market stall
  boxes:   '5972009/pexels-photo-5972009.jpeg',     // a week of food in boxes
  market:  '37321079/pexels-photo-37321079.jpeg',   // fresh vegetables
  salad:   '23285946/pexels-photo-23285946.jpeg',   // chickpea salad from above
  bowl:    '34227771/pexels-photo-34227771.jpeg',   // tofu and quinoa bowl
  cooking: '3531700/pexels-photo-3531700.jpeg',     // hands cooking with spices
  veg:     '1893563/pexels-photo-1893563.jpeg',     // vegetable bowl with sesame
};

const photoUrl = (key, width) =>
  `https://images.pexels.com/photos/${PHOTOS[key] || PHOTOS.thali}` +
  `?auto=compress&cs=tinysrgb&fit=crop&w=${width || 800}`;

/** The photo of this dish, judged by its name - or null when we have no photo of it.
    A dish only gets a photo that shows that dish: a wrong picture is worse than none. */
const DISH_WORDS = [
  [/paneer/i, 'paneer'],
  [/salad/i, 'salad'],
  [/dosa/i, 'dosa'],
  [/idli|uttapam|sambar|sambhar|medu vada/i, 'idli'],
  [/chana|chole|chickpea (curry|masala)/i, 'chana'],
  [/quinoa|tofu|buddha bowl|grain bowl/i, 'bowl'],
  [/vegetable bowl|veggie bowl|stir[- ]?fr(y|ied) vegetables?/i, 'veg'],
  [/thali/i, 'thali'],
];
const photoFor = (name) => {
  const match = DISH_WORDS.find(([pattern]) => pattern.test(String(name || '')));
  return match ? match[1] : null;
};

/** A dish photo, or nothing at all when we do not have a photo of that dish. */
const dishPhoto = (name, width, cls) => {
  const key = photoFor(name);
  return key ? photoFrame(key, width, cls) : '';
};

/** An empty photo frame. Call mountPhotos on its container to fill it in. */
const photoFrame = (key, width, cls, caption) =>
  `<figure class="ph ${cls || ''}" data-photo="${key}" data-w="${width}">${
    caption ? `<figcaption>${esc(caption)}</figcaption>` : ''}</figure>`;

/** Put a real <img> inside every frame that does not have one yet. */
function mountPhotos(root) {
  (root || document).querySelectorAll('.ph[data-photo]').forEach((frame) => {
    if (frame.querySelector('img')) return;
    const image = new Image();
    image.alt = '';
    // backdrops sit in views that start hidden, and a lazy image in a hidden
    // view does not load until it is shown - too late to look good.
    image.loading = /hero-shot|page-bg|cta-bg/.test(frame.className) ? 'eager' : 'lazy';
    image.decoding = 'async';
    image.onload = () => image.classList.add('on');
    image.onerror = () => {
      // a dish photo that fails is removed; a backdrop keeps its warm gradient
      if (frame.classList.contains('dish')) { frame.remove(); return; }
      frame.classList.add('noimg'); image.remove();
    };
    image.src = photoUrl(frame.dataset.photo, Number(frame.dataset.w) || 800);
    frame.prepend(image);
  });
}

/** Our checks speak in field names. Say the same thing in the person's words. */
const say = (message) => {
  let text = String(message)
    .replace(/(\d+) kcal is above the limit of (\d+)/, '$1 calories — a little over your limit of $2')
    .replace(/not vegetarian: contains/, 'contains')
    .replace(/not vegan: contains/, 'contains')
    .replace(/nutrition confidence is \w+/, 'we could not identify every ingredient confidently')
    .replace(/costs about Rs ([\d.]+) per serving/, 'costs about ₹$1 a serving')
    .replace(/only ([\d.]+) g protein per serving/, 'has $1 g of protein a serving')
    .replace(/contains excluded ingredient: /, 'contains ')
    .replace(/takes about (\d+) minutes/, 'takes about $1 minutes to cook');
  return text.charAt(0).toUpperCase() + text.slice(1);
};

const TROUBLE = {
  unreachable: 'NutriChef is not responding. Please try again in a moment.',
  library: 'Our recipe collection is still being prepared. Please try again shortly.',
  llm: 'Recipe writing is unavailable right now — meal plans still work.',
  busy: 'Our kitchen is busy. Please try again in a minute.',
  auth: 'Please sign in again.',
  generic: 'Something went wrong. Please try again.',
};
const explain = (error) => {
  const text = String(error.message || error).toLowerCase();
  if (text.includes('failed to fetch') || text.includes('networkerror')) return TROUBLE.unreachable;
  if (text.includes('library')) return TROUBLE.library;
  if (text.includes('language model') || text.includes('quota')) return TROUBLE.llm;
  if (text.includes('busy') || text.includes('high demand')) return TROUBLE.busy;
  if (text.includes('sign in')) return TROUBLE.auth;
  if (text.includes('already registered')) return 'That email already has an account — sign in instead.';
  if (text.includes('wrong email')) return 'That email and password do not match.';
  if (text.includes('wrong password')) return 'That password is not right.';
  return text.length && text.length < 110 ? say(error.message || error) : TROUBLE.generic;
};

/* ---------------- state + api ---------------- */

const state = {
  token: localStorage.getItem('nc_token') || null,
  email: localStorage.getItem('nc_email') || null,
  allergies: new Set(), planAllergies: new Set(),
  slots: new Set(['breakfast', 'lunch', 'dinner']),
  recipe: null, plan: null, pantry: [], bought: new Set(),
  saved: null,   // the signed-in person's saved settings, once put into the forms
};

async function call(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.token) headers.Authorization = 'Bearer ' + state.token;
  let response;
  try {
    response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch (error) {
    throw new Error('Failed to fetch');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    if (Array.isArray(detail)) {
      throw new Error(detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; '));
    }
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}

const api = {
  health: () => call('GET', '/health'),
  signup: (email, password) => call('POST', '/api/v1/auth/signup', { email, password }),
  login: (email, password) => call('POST', '/api/v1/auth/login', { email, password }),
  profile: () => call('GET', '/api/v1/users/me/profile'),
  saveProfile: (p) => call('PUT', '/api/v1/users/me/profile', p),
  kitchen: () => call('GET', '/api/v1/users/me/inventory'),
  saveKitchen: (items) => call('PUT', '/api/v1/users/me/inventory', items),
  recipe: (body) => call('POST', '/api/v1/recipes/generate', body),
  plan: (body) => call('POST', '/api/v1/plans/generate', body),
  deleteAccount: (password) => call('DELETE', '/api/v1/users/me', { password }),
  feedback: (recipeId, liked) =>
    call('POST', '/api/v1/users/me/feedback', { recipe_id: recipeId.slice(0, 64), liked }),
};

/* ---------------- shell ---------------- */

const VIEWS = ['home', 'recipe', 'plan', 'kitchen'];

function go(view) {
  VIEWS.forEach((name) => { $('view-' + name).hidden = name !== view; });
  document.querySelectorAll('.nav-links a').forEach((link) =>
    link.classList.toggle('on', link.dataset.go === view));
  $('navLinks').classList.remove('open');
  window.scrollTo({ top: 0, behavior: 'instant' });
  location.hash = view === 'home' ? '' : view;
  if (view === 'kitchen') renderKitchen();
  if (view === 'recipe' || view === 'plan') useSavedSettings();
}

/* ---------------- saved settings in the forms ---------------- */

/** Fill the recipe and plan forms from My kitchen, once per sign-in, and say so. */
async function useSavedSettings() {
  if (!signedIn()) { paintSavedNotes(); return; }
  if (state.saved) { paintSavedNotes(); return; }
  try { state.saved = await api.profile(); } catch (error) { return; }
  const saved = state.saved;
  if (saved.diet) { $('dietSelect').value = saved.diet; $('planDiet').value = saved.diet; }
  (saved.allergies || []).forEach((code) => { state.allergies.add(code); state.planAllergies.add(code); });
  pills($('allergyPills'), ALLERGENS, state.allergies);
  pills($('planAllergyPills'), ALLERGENS, state.planAllergies);
  if (saved.exclude && saved.exclude.length) $('excludeInput').value = saved.exclude.join(', ');
  if (saved.min_protein_g) {
    $('planProtein').value = Math.min(60, saved.min_protein_g);
    $('planProteinOut').textContent = $('planProtein').value + ' g';
  }
  paintSavedNotes();
}

function paintSavedNotes() {
  const saved = signedIn() ? state.saved : null;
  const parts = [];
  if (saved && saved.diet) parts.push(DIETS[saved.diet] || saved.diet);
  if (saved && saved.allergies && saved.allergies.length) {
    parts.push('allergic to ' + saved.allergies.map((code) => ALLERGENS[code] || code).join(', '));
  }
  ['recipeSaved', 'planSaved'].forEach((id) => {
    const note = $(id);
    note.hidden = !parts.length;
    if (!parts.length) return;
    note.innerHTML = `Using your saved settings: <b>${esc(parts.join(' · '))}</b>.
      Saved allergies always apply. <a href="#kitchen" data-go="kitchen">Change them</a>`;
    note.querySelector('a').onclick = (event) => { event.preventDefault(); go('kitchen'); };
  });
}

function toast(message, bad) {
  const node = el('div', 'toast' + (bad ? ' bad' : ''), esc(message));
  $('toasts').append(node);
  setTimeout(() => node.remove(), 4200);
}

function signedIn() { return Boolean(state.token); }

function forgetSignIn() {
  state.token = state.email = null;
  state.saved = null;
  paintSavedNotes();
  localStorage.removeItem('nc_token'); localStorage.removeItem('nc_email');
  paintAccount();
}

function paintAccount() {
  $('who').hidden = !signedIn();
  $('who').textContent = state.email || '';
  $('signInBtn').hidden = signedIn();
  $('signOutBtn').hidden = !signedIn();
}

/* ---------------- pills ---------------- */

function pills(container, options, chosen, onChange) {
  container.innerHTML = '';
  Object.entries(options).forEach(([value, label]) => {
    const pill = el('span', 'pill' + (chosen.has(value) ? ' on' : ''), esc(label));
    pill.onclick = () => {
      chosen.has(value) ? chosen.delete(value) : chosen.add(value);
      pill.classList.toggle('on');
      if (onChange) onChange();
    };
    container.append(pill);
  });
}

function fillDiets(select) {
  select.innerHTML = '<option value="">No preference</option>' +
    Object.entries(DIETS).map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join('');
}

/* ---------------- recipe page ---------------- */

const EXAMPLES = [
  'A high-protein vegetarian dinner under 600 calories',
  'Something with paneer I can cook in 20 minutes',
  'A light egg breakfast, no milk',
  'Comfort food for a cold evening, under ₹80 a serving',
];

/* The home page gallery. Real dishes, real numbers - nothing is generated here,
   these are examples of the kind of thing the checks let through. */
const GALLERY = [
  { photo: 'paneer', tag: 'Dinner', name: 'Paneer tikka masala', note: '498 kcal · 32 g protein · ₹74' },
  { photo: 'chana', tag: 'Lunch', name: 'Chana masala', note: '412 kcal · 19 g protein · ₹38' },
  { photo: 'idli', tag: 'Breakfast', name: 'Idli with sambar', note: '286 kcal · 11 g protein · ₹24' },
  { photo: 'bowl', tag: 'Dinner', name: 'Quinoa and tofu bowl', note: '521 kcal · 27 g protein · ₹96' },
  { photo: 'dosa', tag: 'Breakfast', name: 'Masala dosa', note: '364 kcal · 9 g protein · ₹31' },
  { photo: 'salad', tag: 'Snack', name: 'Sprouted chickpea salad', note: '223 kcal · 12 g protein · ₹27' },
];

function macroBar(protein, carbs, fat) {
  const parts = [['Protein', protein * 4, 'var(--protein)', protein],
                 ['Carbs', carbs * 4, 'var(--carbs)', carbs],
                 ['Fat', fat * 9, 'var(--fat)', fat]];
  const total = parts.reduce((sum, p) => sum + p[1], 0) || 1;
  return `<div class="macro">
    <div class="macro-bar">${parts.map(([, energy, colour]) =>
      `<i style="width:${(energy / total * 100).toFixed(1)}%;background:${colour}"></i>`).join('')}</div>
    <div class="macro-key">${parts.map(([name, energy, colour, grams]) =>
      `<span><em style="background:${colour}"></em>${name} ${Math.round(grams)} g
       (${Math.round(energy / total * 100)}%)</span>`).join('')}</div></div>`;
}

function renderRecipe(result) {
  const box = $('recipeResult');
  const r = result.recipe;
  const n = result.nutrition_per_serving || {};
  box.innerHTML = '';

  const wrap = el('div', 'result');

  if (result.status !== 'ok') {
    wrap.append(el('div', 'notice warn',
      `<strong>We could not meet everything you asked for.</strong> Here is how close we got:
       <ul>${(result.checks.failures || []).map((f) => `<li>${esc(say(f))}</li>`).join('')}</ul>`));
  }

  const grid = el('div', 'recipe-grid');

  const left = el('div', 'card');
  left.innerHTML = dishPhoto(r.title, 900, 'dish dish-photo') +
    `<div class="dish-head"><h2>${esc(r.title)}</h2>
       <p class="sub">Serves ${esc(r.servings)}</p></div>
     <div class="recipe-body">
       <h3>What you need</h3>
       <ul class="ing">${r.ingredients.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>
       <h3 style="margin-top:1.6rem">How to make it</h3>
       <ol class="method">${r.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>
     </div>`;

  const right = el('div', 'card');
  right.style.padding = '1.5rem';
  const marks = [];
  if (result.status === 'ok') marks.push(['Meets everything you asked for', 'good']);
  (r.allergens || []).forEach((a) => marks.push(['Contains ' + (ALLERGENS[a] || a).toLowerCase(), 'warn']));
  if (!(r.allergens || []).length) marks.push(['No common allergens found', 'good']);
  (r.suitable_diets || []).filter((d) => d !== 'non_vegetarian')
    .forEach((d) => marks.push([DIETS[d] || d, 'flat']));

  right.innerHTML = `
    <div class="tiles">
      <div class="tile"><b>${Math.round(n.kcal || 0)}</b><span>Calories</span></div>
      <div class="tile"><b>${Math.round(n.protein_g || 0)} g</b><span>Protein</span></div>
      <div class="tile"><b>${money(result.cost_per_serving_inr)}</b><span>Cost</span></div>
    </div>
    <p class="muted" style="margin:.6rem 0 0">per serving</p>
    <h3 style="margin:1.4rem 0 .2rem">Where the calories come from</h3>
    ${macroBar(n.protein_g || 0, n.carbs_g || 0, n.fat_g || 0)}
    <h3 style="margin:1.4rem 0 .5rem">Good to know</h3>
    <div class="badges">${marks.map(([text, kind]) =>
      `<span class="badge ${kind}">${esc(text)}</span>`).join('')}</div>
    ${(result.checks.warnings || []).map((w) =>
      `<p class="muted">Note: ${esc(say(w))}</p>`).join('')}`;

  if (signedIn()) {
    const row = el('div', 'hero-actions');
    row.style.margin = '1rem 0 0';
    const like = el('button', 'btn outline', 'I would cook this');
    const nope = el('button', 'btn ghost', 'Not for me');
    like.onclick = () => rate(r.title, true);
    nope.onclick = () => rate(r.title, false);
    row.append(like, nope);
    right.append(row);
  }

  grid.append(left, right);
  wrap.append(grid);
  wrap.append(el('p', 'tiny', esc(result.disclaimer)));
  box.append(wrap);
  mountPhotos(box);
}

async function rate(recipeId, liked) {
  try { await api.feedback(recipeId, liked); toast('Thanks — we will remember that.'); }
  catch (error) { toast(explain(error), true); }
}

async function generate() {
  const button = $('generateBtn');
  const request = $('requestBox').value.trim();
  if (request.length < 3) { toast('Tell us what you would like to eat first.', true); return; }

  button.disabled = true;
  $('recipeResult').innerHTML =
    `<div class="result"><div class="cooking"><span class="spinner"></span>
      <div><strong>Writing your recipe…</strong>
      <div class="muted">This usually takes a few seconds.</div></div></div>
     <div class="recipe-grid" style="margin-top:1rem">
      <div class="skeleton" style="height:420px"></div>
      <div class="skeleton" style="height:280px"></div></div>`;
  try {
    state.recipe = await api.recipe({
      request,
      diet: $('dietSelect').value || null,
      allergies: [...state.allergies],
      exclude: $('excludeInput').value.split(',').map((s) => s.trim()).filter(Boolean),
    });
    renderRecipe(state.recipe);
  } catch (error) {
    $('recipeResult').innerHTML =
      `<div class="result"><div class="notice bad">${esc(explain(error))}</div></div>`;
  } finally {
    button.disabled = false;
  }
}

/* ---------------- plan page ---------------- */

function renderPlan(plan) {
  const box = $('planResult');
  const t = plan.totals, s = plan.shopping_summary;
  box.innerHTML = '';
  const wrap = el('div', 'result');

  const summary = el('div', 'panel summary');
  summary.innerHTML = `
    <div class="tiles" style="grid-template-columns:repeat(4,1fr)">
      <div class="tile"><b>${t.meals}</b><span>Meals</span></div>
      <div class="tile"><b>${money(t.total_cost_inr)}</b>
        <span>${plan.within_budget ? 'Inside budget' : 'Over budget'}</span></div>
      <div class="tile"><b>${Math.round(t.avg_kcal_per_day)}</b><span>Calories a day</span></div>
      <div class="tile"><b>${Math.round(t.avg_protein_per_day)} g</b><span>Protein a day</span></div>
    </div>`;
  wrap.append(summary);

  const marks = el('div', 'badges');
  if (plan.protein_target_per_day_g) {
    marks.innerHTML = plan.protein_target_met
      ? '<span class="badge good">Protein goal met every day</span>'
      : '<span class="badge warn">Protein goal not quite reached</span>';
  }
  const skipped = plan.skipped || [];
  const noRecipe = skipped.filter((s) => s.reason === 'no_recipe').length;
  const noMoney = skipped.length - noRecipe;
  if (noRecipe) {
    marks.innerHTML += `<span class="badge warn">${noRecipe} meal${noRecipe > 1 ? 's' : ''} left
      empty — no recipe for it fits your diet, allergies and dislikes</span>`;
  }
  if (noMoney) {
    marks.innerHTML += `<span class="badge warn">${noMoney} meal${noMoney > 1 ? 's' : ''} left
      empty — the budget ran out</span>`;
  }
  const standIns = plan.meals.filter((m) => m.stand_in).length;
  if (standIns) {
    marks.innerHTML += `<span class="badge flat">Few recipes fit some meals, so ${standIns}
      ${standIns > 1 ? 'are' : 'is a'} light dish${standIns > 1 ? 'es' : ''} from another course</span>`;
  }
  const ratings = (plan.personalized || {}).ratings || 0;
  if (ratings) {
    marks.innerHTML += `<span class="badge flat">Tuned to your ${ratings}
      rating${ratings > 1 ? 's' : ''}</span>`;
  }
  if (marks.innerHTML) summary.append(marks);

  const days = [...new Set(plan.meals.map((m) => m.day))].sort((a, b) => a - b);
  const week = el('div', 'week');
  days.forEach((day) => {
    const meals = plan.meals.filter((m) => m.day === day);
    // the day's photo shows one of its own meals (dinner first), or there is none
    const pictured = ['dinner', 'lunch', 'breakfast', 'snack']
      .map((slot) => meals.find((m) => m.slot === slot && photoFor(m.title)))
      .find(Boolean);
    const card = el('div', 'day',
      (pictured ? dishPhoto(pictured.title, 420, 'dish') : '') +
      `<h4>Day ${day}</h4><div class="day-meals">` +
      meals.map((m) =>
        `<div class="meal"><span class="slot">${esc(SLOTS[m.slot] || m.slot)}${
          m.stand_in ? ' <em class="stand-in">· stand-in</em>' : ''}</span>
          <span class="nm">${esc(m.title)}</span>
          <span class="n">${Math.round(m.protein_g || 0)} g · ${money(m.cost_inr)}</span>
          ${signedIn() ? `<span class="rate">
            <button class="rate-btn" data-id="${esc(m.recipe_id)}" data-liked="1"
              title="More like this" aria-label="Like ${esc(m.title)}">&#9829; Like</button>
            <button class="rate-btn" data-id="${esc(m.recipe_id)}" data-liked="0"
              title="Never suggest this again" aria-label="Not for me: ${esc(m.title)}">Not for me</button>
          </span>` : ''}</div>`
      ).join('') + '</div>');
    week.append(card);
  });
  // Likes and dislikes shape the next plan: a "not for me" recipe never comes back.
  week.addEventListener('click', (event) => {
    const button = event.target.closest('.rate-btn');
    if (!button) return;
    rate(button.dataset.id, button.dataset.liked === '1');
    button.closest('.rate').innerHTML = button.dataset.liked === '1'
      ? '<span class="rated">Liked</span>' : '<span class="rated">Won\'t suggest again</span>';
  });
  wrap.append(week);

  const rows = (plan.shopping_list || []).filter((r) => r.to_buy_g > 0)
    .sort((a, b) => (b.cost_inr || 0) - (a.cost_inr || 0));
  const list = el('div', 'panel');
  list.innerHTML = `<h3>Shopping list</h3>
    <p class="muted">${s.items_to_buy} items, about ${money(s.cost_inr)} —
      ${money(s.saved_by_using_what_you_have_inr)} saved by using your kitchen.</p>` +
    (rows.length ? `<table class="list"><thead><tr><th>Ingredient</th><th class="r">Buy</th>
      <th class="r">Already have</th><th class="r">Cost</th></tr></thead><tbody>${
      rows.map((r) => `<tr><td><label class="buy"><input type="checkbox">
        <span>${esc(title(r.ingredient_id))}</span></label></td>
        <td class="r">${weight(r.to_buy_g)}</td>
        <td class="r">${r.at_home_g ? weight(r.at_home_g) : '—'}</td>
        <td class="r">${r.cost_inr == null ? '—' : money(r.cost_inr)}</td></tr>`).join('')
      }</tbody></table>` : '<p class="muted">Nothing to buy — you already have everything.</p>');
  list.querySelectorAll('.buy input').forEach((box_) => {
    box_.onchange = () => box_.closest('tr').classList.toggle('bought', box_.checked);
  });
  wrap.append(list);
  wrap.append(el('p', 'tiny', esc(plan.disclaimer)));
  box.append(wrap);
  mountPhotos(box);
}

async function buildPlan() {
  const button = $('planBtn');
  button.disabled = true;
  $('planResult').innerHTML =
    `<div class="result"><div class="cooking"><span class="spinner"></span>
      <div><strong>Choosing meals that fit…</strong>
      <div class="muted">Picking meals that fit your rules and your budget.</div></div></div></div>`;
  try {
    state.plan = await api.plan({
      days: Number($('planDays').value),
      budget_inr: Number($('planBudget').value),
      slots: [...state.slots],
      min_protein_g: Number($('planProtein').value) || null,
      allergies: [...state.planAllergies],
      diet: $('planDiet').value || null,
    });
    renderPlan(state.plan);
  } catch (error) {
    $('planResult').innerHTML =
      `<div class="result"><div class="notice bad">${esc(explain(error))}</div></div>`;
  } finally {
    button.disabled = false;
  }
}

/* ---------------- kitchen page ---------------- */

async function renderKitchen() {
  const box = $('kitchenBody');
  if (!signedIn()) {
    box.innerHTML = `<div class="empty"><h3>Sign in to save your kitchen</h3>
      <p>Your diet, allergies and pantry follow you everywhere once you do.</p></div>`;
    box.querySelector('.empty').append(
      Object.assign(el('button', 'btn primary', 'Sign in'), { onclick: openAuth }));
    return;
  }

  box.innerHTML = '<div class="skeleton" style="height:320px"></div>';
  let profile, pantry;
  try { [profile, pantry] = await Promise.all([api.profile(), api.kitchen()]); }
  catch (error) { box.innerHTML = `<div class="notice bad">${esc(explain(error))}</div>`; return; }
  state.pantry = pantry;

  const saved = new Set(profile.allergies || []);
  box.innerHTML = `<div class="kitchen-grid">
    <div class="panel"><h3>About you</h3>
      <p class="muted">Saved allergies are added to everything you ask for. A request can add
        more, but never take one away.</p>
      <div style="display:grid;gap:1rem;margin-top:1.2rem">
        <label>I eat <select id="kDiet"></select></label>
        <label>Allergic to <div class="pillbox" id="kAllergies"></div></label>
        <label>Foods I would rather avoid
          <input id="kExclude" type="text" placeholder="whey, mushroom"></label>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:.7rem">
          <label>Protein a meal <input id="kProtein" type="number" min="0" max="300"></label>
          <label>Calories a meal <input id="kKcal" type="number" min="0" max="5000"></label>
          <label>Minutes to cook <input id="kMinutes" type="number" min="0" max="600"></label>
        </div>
        <button class="btn primary" id="kSave">Save preferences</button>
      </div>
    </div>
    <div class="panel"><h3>What is in your kitchen</h3>
      <p class="muted">We use these up first when planning a week, starting with whatever
        expires soonest.</p>
      <div class="pantry" id="pantryList"></div>
      <div class="add-row">
        <label>Ingredient <input id="pName" type="text" placeholder="paneer"></label>
        <label>Grams <input id="pGrams" type="number" min="0" placeholder="400"></label>
        <label>Days left <input id="pDays" type="number" min="0" placeholder="3"></label>
        <button class="btn outline" id="pAdd">Add</button>
      </div>
    </div>
    <div class="panel danger-zone"><h3>Delete my account</h3>
      <p class="muted">This removes your account, your saved preferences, your kitchen and
        your likes for good. It cannot be undone.</p>
      <div class="confirm-row">
        <label>Your password <input id="dPassword" type="password" autocomplete="current-password"></label>
        <button class="btn danger" id="dDelete">Delete my account</button>
      </div>
    </div></div>`;

  fillDiets($('kDiet'));
  $('kDiet').value = profile.diet || '';
  $('kExclude').value = (profile.exclude || []).join(', ');
  $('kProtein').value = profile.min_protein_g || '';
  $('kKcal').value = profile.max_kcal || '';
  $('kMinutes').value = profile.max_cook_minutes || '';
  pills($('kAllergies'), ALLERGENS, saved);

  $('kSave').onclick = async () => {
    try {
      await api.saveProfile({
        diet: $('kDiet').value || null,
        allergies: [...saved],
        exclude: $('kExclude').value.split(',').map((s) => s.trim()).filter(Boolean),
        min_protein_g: Number($('kProtein').value) || null,
        max_kcal: Number($('kKcal').value) || null,
        max_cook_minutes: Number($('kMinutes').value) || null,
      });
      state.saved = null;   // the forms pick up the new settings next time
      toast('Saved. We will use this from now on.');
    } catch (error) { toast(explain(error), true); }
  };

  $('dDelete').onclick = deleteAccount;

  paintPantry();
  $('pAdd').onclick = async () => {
    const name = $('pName').value.trim().toLowerCase().replace(/\s+/g, '_');
    if (!name) return;
    state.pantry.push({
      ingredient_id: name,
      grams: Number($('pGrams').value) || null,
      expires_in_days: $('pDays').value === '' ? null : Number($('pDays').value),
    });
    $('pName').value = $('pGrams').value = $('pDays').value = '';
    await savePantry();
  };
}

async function deleteAccount() {
  const password = $('dPassword').value;
  if (!password) { toast('Type your password first.', true); return; }
  if (!confirm('Delete your account and everything saved with it? This cannot be undone.')) return;
  try {
    await api.deleteAccount(password);
    forgetSignIn();
    go('home');
    toast('Your account and everything saved with it have been deleted.');
  } catch (error) { toast(explain(error), true); }
}

function paintPantry() {
  const list = $('pantryList');
  if (!list) return;
  list.innerHTML = '';
  if (!state.pantry.length) {
    list.innerHTML = '<p class="muted">Nothing saved yet. Add what you already have below.</p>';
    return;
  }
  state.pantry.forEach((item, index) => {
    const soon = item.expires_in_days != null && item.expires_in_days <= 3;
    const node = el('span', 'pantry-item' + (soon ? ' soon' : ''),
      `<b>${esc(title(item.ingredient_id))}</b>
       <span class="muted">${item.grams ? weight(item.grams) : ''}${
         soon ? ` · ${item.expires_in_days}d left` : ''}</span>`);
    const remove = el('button', 'x', '&times;');
    remove.onclick = async () => { state.pantry.splice(index, 1); await savePantry(); };
    node.append(remove);
    list.append(node);
  });
}

async function savePantry() {
  try {
    state.pantry = await api.saveKitchen(state.pantry);
    paintPantry();
    toast('Kitchen updated.');
  } catch (error) { toast(explain(error), true); }
}

/* ---------------- auth ---------------- */

let authMode = 'login';

function openAuth(mode) {
  authMode = mode === 'signup' ? 'signup' : 'login';
  paintAuth();
  $('authModal').hidden = false;
  $('authEmail').focus();
}

function paintAuth() {
  const signup = authMode === 'signup';
  $('authTitle').textContent = signup ? 'Create your account' : 'Welcome back';
  $('authSub').textContent = signup
    ? 'So your allergies and kitchen follow you everywhere.'
    : 'Sign in so your allergies follow you everywhere.';
  $('authSubmit').textContent = signup ? 'Create account' : 'Sign in';
  $('authSwitchText').textContent = signup ? 'Already have an account?' : 'New here?';
  $('authSwitch').textContent = signup ? 'Sign in' : 'Create an account';
  $('authError').hidden = true;
}

async function submitAuth(event) {
  event.preventDefault();
  const email = $('authEmail').value.trim();
  const password = $('authPassword').value;
  try {
    const answer = authMode === 'signup' ? await api.signup(email, password)
                                         : await api.login(email, password);
    state.token = answer.access_token;
    state.email = email;
    localStorage.setItem('nc_token', state.token);
    localStorage.setItem('nc_email', email);
    $('authModal').hidden = true;
    paintAccount();
    toast(authMode === 'signup' ? 'Welcome to NutriChef.' : 'Signed in.');
    if (!$('view-kitchen').hidden) renderKitchen();
    if (!$('view-recipe').hidden || !$('view-plan').hidden) useSavedSettings();
  } catch (error) {
    $('authError').textContent = explain(error);
    $('authError').hidden = false;
  }
}

/* ---------------- start ---------------- */

/** Sections fade up the first time they come into view. */
function watchReveals() {
  const targets = document.querySelectorAll('.reveal');
  if (!('IntersectionObserver' in window)) {
    targets.forEach((node) => node.classList.add('in'));
    return;
  }
  const watcher = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('in');
      watcher.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -12% 0px' });
  targets.forEach((node) => watcher.observe(node));
}

function start() {
  fillDiets($('dietSelect'));
  fillDiets($('planDiet'));
  $('planDiet').value = 'vegetarian';
  pills($('allergyPills'), ALLERGENS, state.allergies);
  pills($('planAllergyPills'), ALLERGENS, state.planAllergies);
  pills($('slotPills'), SLOTS, state.slots);

  $('allergenGrid').innerHTML = Object.values(ALLERGENS)
    .map((name) => `<span>${esc(name)}</span>`).join('');
  $('gallery').innerHTML = GALLERY.map((dish) =>
    `<article class="gallery-card">${photoFrame(dish.photo, 560)}
      <span class="gallery-tag">${esc(dish.tag)}</span>
      <div class="gallery-meta"><b>${esc(dish.name)}</b><span>${esc(dish.note)}</span></div>
     </article>`).join('');
  mountPhotos();
  watchReveals();
  $('quickChips').innerHTML = EXAMPLES
    .map((text) => `<span class="chip">${esc(text)}</span>`).join('');
  $('quickChips').querySelectorAll('.chip').forEach((chip) => {
    chip.onclick = () => { $('requestBox').value = chip.textContent.trim(); $('requestBox').focus(); };
  });
  $('requestBox').value = EXAMPLES[0];

  document.querySelectorAll('[data-go]').forEach((node) => {
    node.onclick = (event) => { event.preventDefault(); go(node.dataset.go); };
  });
  $('hamburger').onclick = () => $('navLinks').classList.toggle('open');
  $('generateBtn').onclick = generate;
  $('planBtn').onclick = buildPlan;
  $('planProtein').oninput = (event) => { $('planProteinOut').textContent = event.target.value + ' g'; };

  $('signInBtn').onclick = () => openAuth('login');
  $('signOutBtn').onclick = () => { forgetSignIn(); go('home'); toast('Signed out.'); };
  $('authClose').onclick = () => { $('authModal').hidden = true; };
  $('authModal').onclick = (event) => {
    if (event.target === $('authModal')) $('authModal').hidden = true;
  };
  $('authSwitch').onclick = (event) => {
    event.preventDefault();
    authMode = authMode === 'signup' ? 'login' : 'signup';
    paintAuth();
  };
  $('authForm').onsubmit = submitAuth;

  addEventListener('scroll', () => $('nav').classList.toggle('scrolled', scrollY > 8));
  paintAccount();
  go(VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home');

  api.health()
    .then((status) => { if (!status.recipes) toast(TROUBLE.library, true); })
    .catch(() => toast(TROUBLE.unreachable, true));
}

document.addEventListener('DOMContentLoaded', start);
