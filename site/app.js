const PAGE_SIZE = 12;
const PLATFORM_NAMES = { youtube: 'YouTube', reddit: 'Reddit', facebook: 'Facebook' };
const state = { items: [], source: 'all', platform: 'all', query: '', limit: PAGE_SIZE };
const element = (id) => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat('fr-CA', { day: 'numeric', month: 'short', year: 'numeric' });
const timeFormat = new Intl.DateTimeFormat('fr-CA', { dateStyle: 'medium', timeStyle: 'short' });

function safeUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password) {
    throw new Error('Une publication contient un lien non sécuritaire.');
  }
  return url.href;
}

function normalizeText(value) {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr');
}

function selectSource(sourceId) {
  state.source = sourceId;
  state.limit = PAGE_SIZE;
  document.querySelectorAll('.source-button').forEach((button) => {
    const selected = button.dataset.source === sourceId;
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  render();
}

function makeCard(item) {
  const card = element('card-template').content.cloneNode(true);
  const internalUrl = `./publication.html?source=${encodeURIComponent(item.source_id)}&id=${encodeURIComponent(item.id)}`;
  const imageLink = card.querySelector('.card-image-link');
  imageLink.href = internalUrl;
  imageLink.setAttribute('aria-label', item.title);
  const image = card.querySelector('img');
  if (item.image_url) {
    image.src = item.image_url;
    image.addEventListener('error', () => {
      image.hidden = true;
      imageLink.classList.add('no-image');
    }, { once: true });
  } else {
    image.remove();
    imageLink.classList.add('no-image');
  }
  card.querySelector('.platform-tag').textContent = PLATFORM_NAMES[item.platform] || item.platform;
  const date = card.querySelector('time');
  date.dateTime = item.published_at;
  date.textContent = dateFormat.format(new Date(item.published_at));
  const title = card.querySelector('h3 a');
  title.href = internalUrl;
  title.textContent = item.title;
  card.querySelector('.card-description').textContent = item.description;
  card.querySelector('.card-source').textContent = item.source_name;
  card.querySelector('.read-link').href = internalUrl;
  card.querySelector('.card-official').href = item.url;
  return card;
}

function render() {
  const query = normalizeText(state.query.trim());
  const matches = state.items.filter((item) =>
    (state.source === 'all' || item.source_id === state.source) &&
    (state.platform === 'all' || item.platform === state.platform) &&
    normalizeText(`${item.title} ${item.description} ${item.source_name}`).includes(query)
  );
  const fragment = document.createDocumentFragment();
  matches.slice(0, state.limit).forEach((item) => fragment.append(makeCard(item)));
  element('publications').replaceChildren(fragment);
  element('results').textContent = `${matches.length} publication${matches.length === 1 ? '' : 's'}`;
  element('empty').hidden = matches.length > 0;
  element('load-more').hidden = matches.length <= state.limit;
  if (!state.items.length) {
    element('empty-message').textContent = 'Les publications apparaîtront après une récupération réussie.';
  }
}

function showSources(sources) {
  element('source-count').textContent = sources.length;
  element('all-count').textContent = state.items.length;
  element('sources').replaceChildren();
  const platforms = [...new Set(sources.map((source) => source.platform))];
  platforms.forEach((platform) => {
    const heading = document.createElement('h3');
    heading.className = 'source-platform';
    heading.textContent = PLATFORM_NAMES[platform] || platform;
    element('sources').append(heading);
    sources.filter((source) => source.platform === platform).forEach((source) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'source-button';
      button.dataset.source = source.id;
      button.setAttribute('aria-pressed', 'false');
      const icon = document.createElement('span');
      icon.className = `source-icon ${source.platform}`;
      icon.textContent = source.platform === 'youtube' ? '▶' : source.platform === 'facebook' ? 'f' : 'r/';
      icon.setAttribute('aria-hidden', 'true');
      const name = document.createElement('span');
      name.textContent = source.name;
      const count = document.createElement('span');
      count.className = 'count';
      const itemCount = state.items.filter((item) => item.source_id === source.id).length;
      count.textContent = source.status === 'disabled' ? 'En attente' : itemCount;
      if (source.status === 'disabled') {
        button.title = 'Abonnement enregistré, connexion non activée.';
        button.disabled = itemCount === 0;
      }
      button.append(icon, name, count);
      button.addEventListener('click', () => selectSource(source.id));
      element('sources').append(button);
    });
  });
  platforms.forEach((platform) => {
    const option = document.createElement('option');
    option.value = platform;
    option.textContent = PLATFORM_NAMES[platform] || platform;
    element('platform').append(option);
  });
}

async function loadFeed() {
  try {
    const response = await fetch('./feed.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Le serveur a répondu HTTP ${response.status}.`);
    const feed = await response.json();
    if (feed.version !== 1 || !Array.isArray(feed.items) || !Array.isArray(feed.sources)) {
      throw new Error('Le format du fil est invalide.');
    }
    const generated = new Date(feed.generated_at);
    if (!Number.isFinite(generated.getTime())) throw new Error('La date du fil est invalide.');
    state.items = feed.items.map((item) => {
      if (!Number.isFinite(Date.parse(item.published_at))) throw new Error('Une date de publication est invalide.');
      for (const field of ['title', 'description', 'source_id', 'source_name', 'platform']) {
        if (typeof item[field] !== 'string') throw new Error('Une publication est invalide.');
      }
      return { ...item, url: safeUrl(item.url), image_url: item.image_url ? safeUrl(item.image_url) : null };
    }).sort((a, b) => Date.parse(b.published_at) - Date.parse(a.published_at));
    showSources(feed.sources);
    element('updated').textContent = `Dernière tentative : ${timeFormat.format(generated)}`;
    const warnings = feed.sources.filter((source) => source.status === 'error').map((source) => {
      const lastSuccess = source.last_success_at
        ? ` Dernier succès : ${timeFormat.format(new Date(source.last_success_at))}.`
        : ' Aucune récupération réussie pour le moment.';
      return `${source.name} : récupération en échec; les publications déjà archivées sont conservées.${lastSuccess}`;
    });
    if (Date.now() - generated.getTime() > 4 * 60 * 60 * 1000) {
      warnings.push('Ce fil n’a pas été actualisé depuis plus de 4 heures. La mise à jour automatique peut être retardée ou interrompue.');
    }
    if (warnings.length) {
      element('warning').textContent = warnings.join(' ');
      element('warning').hidden = false;
    }
    render();
  } catch (error) {
    console.error('Unable to load the feed:', error);
    element('results').textContent = 'Fil indisponible';
    element('error').textContent = `Impossible de charger le fil. ${error.message} Réessayez en rechargeant la page.`;
    element('error').hidden = false;
  } finally {
    element('publications').setAttribute('aria-busy', 'false');
  }
}

document.querySelector('[data-source="all"]').addEventListener('click', () => selectSource('all'));
element('search').addEventListener('input', (event) => {
  state.query = event.target.value;
  state.limit = PAGE_SIZE;
  render();
});
element('platform').addEventListener('change', (event) => {
  state.platform = event.target.value;
  state.limit = PAGE_SIZE;
  render();
});
element('load-more').addEventListener('click', () => {
  state.limit += PAGE_SIZE;
  render();
});
loadFeed();
